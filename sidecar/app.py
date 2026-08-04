#!/usr/bin/env python3
"""NC Tower host agent.

The service intentionally uses only the Python standard library and the
Docker CLI. Read/write operations are constrained by environment-configured
allowlists, and every mutating operation is audited.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from chassis_fan import ChassisFanController
from inventory import (
    SmartTrendSampler,
    collect_hardware,
    collect_kernel_log,
    collect_posture,
    collect_storage,
    collect_temperatures,
    extend_network_depth,
    smart_history_read,
    smart_history_summarize,
)
from parity import (
    CAPABILITIES,
    SIDECAR_VERSION,
    DEV_RE,
    MODEL_RE,
    PKG_RE,
    apply_recreate_overrides,
    audit_tail,
    backup_path_contained,
    host_network_payload,
    ollama_delete,
    ollama_get,
    parse_smart_attributes,
    validate_container_name,
)


def _env(name: str, default: str, *aliases: str) -> str:
    for key in (name, *aliases):
        if key in os.environ:
            return os.environ[key]
    return default


def _csv_env(name: str, default: str, *aliases: str) -> list[str]:
    return [item.strip() for item in _env(name, default, *aliases).split(",") if item.strip()]


TOKEN = _env("NC_TOWER_SIDECAR_TOKEN", "")
OPS_ROOT = Path(_env("OPS_ROOT", "/ops", "NC_TOWER_OPS_ROOT"))
FAN_HELPER = _env("FAN_HELPER", "/usr/local/bin/gpu-fan-helper.py", "NC_TOWER_FAN_HELPER")
NVIDIA_SMI = _env("NVIDIA_SMI", "/usr/bin/nvidia-smi", "NC_TOWER_NVIDIA_SMI")
SMARTCTL = _env("SMARTCTL", "/usr/sbin/smartctl", "NC_TOWER_SMARTCTL")
DOCKER = _env("DOCKER", "/usr/bin/docker", "NC_TOWER_DOCKER")
BACKUP_SCRIPT = _env(
    "BACKUP_SCRIPT",
    "/ops/bin/webmin/backup-enhanced.sh",
    "NC_TOWER_BACKUP_SCRIPT",
)
AUDIT_LOG = Path(_env("AUDIT_LOG", "/ops/log/nc-tower-sidecar.audit.log", "NC_TOWER_AUDIT_LOG"))
BIND = _env("NC_TOWER_BIND", "0.0.0.0", "BIND")
PORT = int(_env("NC_TOWER_PORT", "18765", "PORT"))
_HOST_PROC_ENV = _env("HOST_PROC", "", "NC_TOWER_HOST_PROC")
HOST_PROC = (
    Path(_HOST_PROC_ENV)
    if _HOST_PROC_ENV
    else (Path("/hostproc") if Path("/hostproc").is_dir() else Path("/proc"))
)

COMPOSE_DIRS = _csv_env(
    "COMPOSE_DIRS",
    "",
    "NC_TOWER_COMPOSE_DIRS",
)
DISK_PATHS = _csv_env(
    "DISK_PATHS",
    "/",
    "NC_TOWER_DISK_PATHS",
)
CONTAINER_ALLOW = _csv_env(
    "CONTAINER_ALLOW",
    "gcs_*,mavlink_gateway,gcs_sitl,gcs_simcam,gcs_adsb*",
    "NC_TOWER_CONTAINER_ALLOW",
)
CONTAINER_DENY = _csv_env(
    "CONTAINER_DENY",
    "nc_tower_sidecar,cloud_*,portainer,wg-easy,talk_*,*openclaw*",
    "NC_TOWER_CONTAINER_DENY",
)
CONTAINER_LOG_ALLOW = _csv_env(
    "CONTAINER_LOG_ALLOW", "", "NC_TOWER_CONTAINER_LOG_ALLOW"
) or list(CONTAINER_ALLOW)
SYSTEMD_ALLOW = _csv_env(
    "SYSTEMD_ALLOW",
    "docker.service,openclaw-gateway.service,fancontrol.service,cron.service,ssh.service",
    "NC_TOWER_SYSTEMD_ALLOW",
)
# User-bus units (linger / --user). Matched by exact unit name.
SYSTEMD_USER_UNITS = set(
    _csv_env(
        "SYSTEMD_USER_UNITS",
        "openclaw-gateway.service",
        "NC_TOWER_SYSTEMD_USER_UNITS",
    )
)
SYSTEMD_USER = os.environ.get("SYSTEMD_USER") or os.environ.get("NC_TOWER_SYSTEMD_USER") or "vdroners"
IMAGE_PULL_ALLOW = _csv_env(
    "IMAGE_PULL_ALLOW",
    "veterandroners/*,ghcr.io/vdroners/*",
    "NC_TOWER_IMAGE_PULL_ALLOW",
)
HOST_FAN_HELPER = _env(
    "HOST_FAN_HELPER",
    "/usr/share/webmin/fan-control/gpu-fan-helper.py",
    "NC_TOWER_HOST_FAN_HELPER",
)
OLLAMA_URL = _env("OLLAMA_URL", "http://10.0.0.84:11434", "NC_TOWER_OLLAMA_URL")
BACKUP_DIR = Path(_env("BACKUP_DIR", "/media/4TB/backups", "NC_TOWER_BACKUP_DIR"))
DOCKER_CLEANUP_SCRIPT = _env(
    "DOCKER_CLEANUP_SCRIPT",
    "/ops/bin/webmin/docker-cleanup.sh",
    "NC_TOWER_DOCKER_CLEANUP_SCRIPT",
)

_AUDIT_LOCK = threading.Lock()
_PUBLIC_IP_CACHE: dict[str, Any] = {}
_CHASSIS: ChassisFanController | None = None
_SMART_SAMPLER: SmartTrendSampler | None = None
_META_RE = re.compile(r"[;|&$`]")
_SAFE_EVENT_SINCE_RE = re.compile(r"^[0-9]{1,7}(?:s|m|h|d)?$")
_FORBIDDEN_EXEC = {
    "bash",
    "sh",
    "dash",
    "zsh",
    "ash",
    "rm",
    "rmdir",
    "mkfs",
    "dd",
    "reboot",
    "shutdown",
    "poweroff",
    "halt",
    "kill",
    "pkill",
    "killall",
    "mount",
    "umount",
    "iptables",
    "nft",
    "docker",
    "systemctl",
}


def audit(message: str) -> None:
    line = f"[audit] {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {message}"
    print(line, flush=True)
    with _AUDIT_LOCK:
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
        except OSError as exc:
            print(f"[audit-error] {exc}", flush=True)


def _which(name: str) -> str | None:
    if "/" in name:
        return name if Path(name).is_file() and os.access(name, os.X_OK) else None
    for directory in os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin").split(":"):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _docker_bin() -> str:
    return _which(DOCKER) or _which("docker") or DOCKER


def _run(
    argv: list[str],
    timeout: int = 30,
    *,
    check: bool = False,
    max_output: int = 200_000,
    env: dict[str, str] | None = None,
    keep: str = "tail",
) -> dict[str, Any]:
    """Run argv and capture output.

    `keep` selects which end survives truncation. Logs want the tail; listings
    that put the most important rows first (ps --sort) must keep the head, or
    the header row and top entries are silently discarded.
    """

    def clip(text: str | None) -> str:
        text = text or ""
        return text[:max_output] if keep == "head" else text[-max_output:]

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
            env=env,
        )
        result = {
            "exit": proc.returncode,
            "stdout": clip(proc.stdout),
            "stderr": clip(proc.stderr),
        }
        if check and proc.returncode:
            result["error"] = "command_failed"
        return result
    except subprocess.TimeoutExpired as exc:
        return {
            "exit": None,
            "error": "timeout",
            "stdout": clip(exc.stdout) if isinstance(exc.stdout, str) else "",
            "stderr": clip(exc.stderr) if isinstance(exc.stderr, str) else "",
        }
    except OSError as exc:
        return {"exit": None, "error": str(exc), "stdout": "", "stderr": ""}


def _json_lines(text: str) -> list[Any]:
    rows: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"raw": line})
    return rows


def _docker_json(args: list[str], timeout: int = 30) -> list[Any] | dict[str, Any]:
    result = _run([_docker_bin(), *args], timeout=timeout)
    if result["exit"] != 0:
        raise RuntimeError(result["stderr"] or result.get("error") or "docker command failed")
    text = result["stdout"].strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _json_lines(text)


def _proc_file(name: str) -> Path:
    return HOST_PROC / name.lstrip("/")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _number(value: str) -> int | float | str | None:
    value = value.strip()
    if value in {"", "N/A", "[N/A]", "Not Supported"}:
        return None
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def _statvfs(path: str) -> dict[str, Any]:
    try:
        st = os.statvfs(path)
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        used = total - free
        return {
            "path": path,
            "total_b": total,
            "used_b": used,
            "free_b": free,
            "used_pct": round(used * 100 / total, 1) if total else 0.0,
        }
    except OSError as exc:
        return {"path": path, "error": str(exc)}


def _cpu_times() -> tuple[int, int]:
    line = _read_text(_proc_file("stat")).splitlines()
    fields = line[0].split()[1:] if line and line[0].startswith("cpu ") else []
    values = [int(v) for v in fields if v.isdigit()]
    idle = sum(values[3:5]) if len(values) >= 5 else (values[3] if len(values) > 3 else 0)
    return sum(values), idle


def _cpu_pct() -> float | None:
    total1, idle1 = _cpu_times()
    time.sleep(0.12)
    total2, idle2 = _cpu_times()
    delta = total2 - total1
    return round(100.0 * (delta - (idle2 - idle1)) / delta, 1) if delta > 0 else None


def _package_temperature() -> float | None:
    """Prefer x86_pkg_temp / Tctl; skip zero/nonsense readings."""
    candidates: list[tuple[int, float]] = []
    for base in Path("/sys/class/hwmon").glob("hwmon*"):
        name = _read_text(base / "name").strip().lower()
        for source in sorted(base.glob("temp*_input")):
            label = _read_text(source.with_name(source.name.replace("_input", "_label"))).strip().lower()
            blob = f"{name} {label}"
            try:
                raw = float(_read_text(source).strip())
            except ValueError:
                continue
            celsius = raw / 1000.0 if raw > 500 else raw
            if celsius <= 0 or celsius > 125:
                continue
            priority = 99
            if "x86_pkg_temp" in label or "package id" in label or label == "tctl":
                priority = 0
            elif "package" in blob or "tctl" in blob:
                priority = 1
            elif "coretemp" in name or "k10temp" in name:
                priority = 2
            elif "cpu" in blob:
                priority = 3
            else:
                continue
            candidates.append((priority, round(celsius, 1)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _interfaces() -> list[dict[str, Any]]:
    ip = _which("ip")
    if ip:
        result = _run([ip, "-j", "addr"], timeout=8)
        if result["exit"] == 0:
            try:
                data = json.loads(result["stdout"])
                return [
                    {
                        "name": row.get("ifname"),
                        "state": row.get("operstate"),
                        "mtu": row.get("mtu"),
                        "addresses": [
                            {
                                "family": addr.get("family"),
                                "address": addr.get("local"),
                                "prefixlen": addr.get("prefixlen"),
                                "scope": addr.get("scope"),
                            }
                            for addr in row.get("addr_info", [])
                        ],
                    }
                    for row in data
                ]
            except (json.JSONDecodeError, TypeError):
                pass
    rows = []
    for iface in sorted(Path("/sys/class/net").glob("*")):
        rows.append(
            {
                "name": iface.name,
                "state": _read_text(iface / "operstate").strip(),
                "mtu": _number(_read_text(iface / "mtu")),
                "mac": _read_text(iface / "address").strip(),
                "addresses": [],
            }
        )
    return rows


def _unhealthy_containers() -> list[dict[str, str]]:
    result = _run(
        [_docker_bin(), "ps", "--filter", "health=unhealthy", "--format", "{{.Names}}\t{{.Status}}"],
        timeout=12,
    )
    if result["exit"] != 0:
        return []
    return [
        {"name": parts[0], "status": parts[1] if len(parts) > 1 else ""}
        for line in result["stdout"].splitlines()
        if (parts := line.split("\t", 1))
    ]


def host_summary() -> dict[str, Any]:
    mem: dict[str, str] = {}
    for line in _read_text(_proc_file("meminfo")).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            mem[key] = value.strip()
    load = _read_text(_proc_file("loadavg")).split()[:3]
    uptime = _read_text(_proc_file("uptime")).split()
    return {
        "loadavg": [_number(v) for v in load],
        "mem_total": mem.get("MemTotal"),
        "mem_available": mem.get("MemAvailable"),
        "swap_total": mem.get("SwapTotal"),
        "swap_free": mem.get("SwapFree"),
        "uptime_s": _number(uptime[0]) if uptime else None,
        "disks": [_statvfs(path) for path in DISK_PATHS],
        "cpu_pct": _cpu_pct(),
        "package_temp_c": _package_temperature(),
        "ifaces": _interfaces(),
        "unhealthy_containers": _unhealthy_containers(),
        "ts": time.time(),
    }


def host_gpu() -> dict[str, Any]:
    smi = _which(NVIDIA_SMI) or _which("nvidia-smi")
    if not smi:
        return {"unavailable": True, "reason": "nvidia-smi_missing", "gpus": [], "processes": []}
    fields = (
        "index,uuid,name,utilization.gpu,memory.used,memory.total,"
        "temperature.gpu,fan.speed,power.draw,power.limit"
    )
    result = _run([smi, f"--query-gpu={fields}", "--format=csv,noheader,nounits"], timeout=12)
    if result["exit"] != 0:
        return {"unavailable": True, "reason": result["stderr"], "gpus": [], "processes": []}
    gpus = []
    keys = [
        "index",
        "uuid",
        "name",
        "util_pct",
        "mem_used_mib",
        "mem_total_mib",
        "temp_c",
        "fan_pct",
        "power_draw_w",
        "power_limit_w",
    ]
    for line in result["stdout"].splitlines():
        values = [v.strip() for v in line.split(",")]
        if len(values) == len(keys):
            gpus.append(dict(zip(keys, (_number(v) for v in values))))
    process_result = _run(
        [
            smi,
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        timeout=10,
    )
    processes = []
    if process_result["exit"] == 0:
        for line in process_result["stdout"].splitlines():
            values = [v.strip() for v in line.split(",", 3)]
            if len(values) == 4:
                processes.append(
                    {
                        "gpu_uuid": values[0],
                        "pid": _number(values[1]),
                        "process_name": values[2],
                        "used_memory_mib": _number(values[3]),
                    }
                )
    if not processes:
        pmon = _run([smi, "pmon", "-c", "1"], timeout=10)
        if pmon["exit"] == 0:
            for line in pmon["stdout"].splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    parts = line.split()
                    if len(parts) >= 8 and parts[1] != "-":
                        processes.append(
                            {
                                "gpu_index": _number(parts[0]),
                                "pid": _number(parts[1]),
                                "type": parts[2],
                                "sm_pct": _number(parts[3]),
                                "mem_pct": _number(parts[4]),
                                "process_name": parts[-1],
                            }
                        )
    return {"unavailable": False, "gpus": gpus, "processes": processes, "ts": time.time()}


def _mount_rows() -> list[dict[str, Any]]:
    rows = []
    text = _read_text(_proc_file("mounts"))
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        device, mountpoint, fstype, options = parts[:4]
        mountpoint = mountpoint.replace("\\040", " ").replace("\\011", "\t")
        rows.append(
            {
                "device": device.replace("\\040", " "),
                "mountpoint": mountpoint,
                "fstype": fstype,
                "options": options.split(","),
            }
        )
    return rows


def host_mounts() -> dict[str, Any]:
    mounts = _mount_rows()
    by_path = {row["mountpoint"]: row for row in mounts}
    interesting = []
    for path in DISK_PATHS:
        usage = _statvfs(path)
        best = max(
            (
                row
                for row in mounts
                if path == row["mountpoint"] or path.startswith(row["mountpoint"].rstrip("/") + "/")
            ),
            key=lambda row: len(row["mountpoint"]),
            default=None,
        )
        interesting.append({**usage, "mount": best})
    return {"mounts": mounts, "interesting": interesting, "ts": time.time()}


def host_smart() -> dict[str, Any]:
    ctl = _which(SMARTCTL) or _which("smartctl")
    mounts = host_mounts()["interesting"]
    # Carry an explicit reachability flag and a flat fstype — the UI shows these
    # as OK/down and cannot infer either from a bare statvfs row.
    nas_mounts = [
        {
            **row,
            "ok": "error" not in row and row.get("mount") is not None,
            "fstype": (row.get("mount") or {}).get("fstype"),
        }
        for row in mounts
        if row["path"].startswith(("/media/raid", "/mnt", "/nas"))
    ]
    if not ctl:
        return {
            "unavailable": True,
            "reason": "smartctl_missing",
            "disks": [],
            "nas_mounts": nas_mounts,
        }
    scan = _run([ctl, "--scan-open"], timeout=15)
    if scan["exit"] not in (0, 2):
        scan = _run([ctl, "--scan"], timeout=15)
    disks = []
    for line in scan["stdout"].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        device = parts[0]
        extra = parts[1 : parts.index("#")] if "#" in parts else parts[1:]
        detail = _run([ctl, "-a", *extra, device], timeout=25, max_output=100_000)
        text = detail["stdout"] + "\n" + detail["stderr"]
        health = "UNKNOWN"
        if re.search(r"(overall-health.*PASSED|SMART Health Status:\s*OK)", text, re.I):
            health = "PASS"
        elif re.search(r"(overall-health.*FAILED|SMART Health Status:\s*(?!OK)\S+)", text, re.I):
            health = "FAIL"

        def match(patterns: list[str]) -> str | None:
            for pattern in patterns:
                found = re.search(pattern, text, re.I | re.M)
                if found:
                    return found.group(1).strip()
            return None

        # ATA attribute rows put the raw value last: "  9 Power_On_Hours … -   60404".
        # Patterns stay anchored to a single line — `\s` spans newlines, so an
        # unanchored trailing `(\d+)` picks up the *next* attribute's ID instead.
        temp = match(
            [
                r"^\s*\d+\s+Temperature_Celsius\b.*?-\s+(\d+)",
                r"^\s*\d+\s+Airflow_Temperature_Cel\b.*?-\s+(\d+)",
                r"^Temperature:\s+(\d+)\s+Celsius",
                r"^Current Drive Temperature:\s+(\d+)",
                r"^Current Temperature:\s+(\d+)",
            ]
        )
        hours = match(
            [
                # raw value is the last column; some drives write "9184h+00m+00.000s"
                r"^\s*\d+\s+Power_On_Hours\b[^\n]*?[-\s](\d+)(?:h\+\S*)?\s*$",
                r"^Power On Hours:\s+([\d,]+)",
                r"^Accumulated power on time, hours:minutes\s+(\d+):",
            ]
        )
        disks.append(
            {
                "device": device,
                "health": health,
                "model": match(
                    [
                        r"Device Model:\s*(.+)",
                        r"Model Number:\s*(.+)",
                        r"Product:\s*(.+)",
                    ]
                ),
                "temp_c": _number(temp or ""),
                "power_on_hours": _number((hours or "").replace(",", "")),
                "smartctl_exit": detail["exit"],
            }
        )
    return {"unavailable": False, "disks": disks, "nas_mounts": nas_mounts, "ts": time.time()}


def _fan_helper() -> str | None:
    return _which(FAN_HELPER) or _which("gpu-fan-helper.py")


def _fan_cmd(*args: str) -> list[str] | None:
    """Prefer host python+helper via nsenter (has pynvml); fall back to container python."""
    nsenter = _nsenter_bin()
    if nsenter and Path("/proc/1/ns/mnt").exists():
        return [
            nsenter,
            "--mount=/proc/1/ns/mnt",
            "--",
            "/usr/bin/python3",
            HOST_FAN_HELPER,
            *args,
        ]
    helper = _fan_helper()
    if not helper:
        return None
    return ["python3", helper, *args]


def host_fan_get() -> dict[str, Any]:
    cmd = _fan_cmd("status")
    if not cmd:
        return {"unavailable": True, "reason": "fan_helper_missing"}
    result = _run(cmd, timeout=15)
    if result["exit"] != 0:
        return {"unavailable": True, "reason": result["stderr"] or result.get("error")}
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError:
        payload = {"raw": result["stdout"].strip()}
    return {"unavailable": False, "status": payload, "ts": time.time()}


def host_fan_set(body: dict[str, Any]) -> dict[str, Any]:
    op = str(body.get("op") or "")
    if op == "set-auto":
        args: list[str] = ["set-auto"]
    elif op in {"set-all-speeds", "set-speed"}:
        try:
            speed = int(body.get("speed"))
            fan = int(body.get("fan", -1))
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_fan_or_speed", "http": 400}
        if not 20 <= speed <= 100:
            return {"ok": False, "error": "speed_must_be_20_to_100", "http": 400}
        args = [op, str(speed)] if op == "set-all-speeds" else [op, str(fan), str(speed)]
        if op == "set-speed" and fan < 0:
            return {"ok": False, "error": "fan_index_required", "http": 400}
    else:
        return {"ok": False, "error": "invalid_op", "http": 400}
    cmd = _fan_cmd(*args)
    if not cmd:
        return {"ok": False, "error": "fan_helper_missing", "http": 503}
    result = _run(cmd, timeout=20)
    audit(f"fan op={op} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "op": op, **result}


def host_chassis_fan() -> dict[str, Any]:
    return _chassis().status()


def host_chassis_fan_set(body: dict[str, Any]) -> dict[str, Any]:
    return _chassis().mutate(body)


def host_chassis_fan_history(minutes: int = 60) -> dict[str, Any]:
    return _chassis().history(minutes)


def _chassis() -> ChassisFanController:
    global _CHASSIS
    if _CHASSIS is None:
        _CHASSIS = ChassisFanController(
            OPS_ROOT,
            read_text=_read_text,
            number=_number,
            run=_run,
            nsenter_bin=_nsenter_bin,
            audit=audit,
            fan_set=host_fan_set,
            gpu_status=host_gpu,
        )
    return _CHASSIS


def host_packages() -> dict[str, Any]:
    nsenter = _nsenter_bin()
    if nsenter:
        result = _run(
            [nsenter, "--mount=/proc/1/ns/mnt", "--", "/usr/bin/apt", "list", "--upgradable"],
            timeout=60,
            max_output=150_000,
        )
        held_result = _run(
            [nsenter, "--mount=/proc/1/ns/mnt", "--", "/usr/bin/apt-mark", "showhold"],
            timeout=30,
        )
    else:
        apt = _which("apt")
        if not apt:
            return {"unavailable": True, "reason": "apt_missing", "packages": []}
        result = _run([apt, "list", "--upgradable"], timeout=60, max_output=150_000)
        held_result = _run([_which("apt-mark") or "apt-mark", "showhold"], timeout=30)
    held = {
        line.strip()
        for line in (held_result.get("stdout") or "").splitlines()
        if line.strip()
    }
    packages = []
    for line in result["stdout"].splitlines():
        if not line or line.startswith("Listing"):
            continue
        match = re.match(r"([^/]+)/(\S+)\s+(\S+)\s+(\S+)(?:\s+\[upgradable from: (.+)\])?", line)
        packages.append(
            {
                "name": match.group(1),
                "suite": match.group(2),
                "new_version": match.group(3),
                "arch": match.group(4),
                "old_version": match.group(5),
                "held": match.group(1) in held,
            }
            if match
            else {"raw": line}
        )
    return {
        "unavailable": result["exit"] != 0,
        "packages": packages,
        "held": sorted(held),
        "exit": result["exit"],
        "error": result["stderr"] or result.get("error"),
        "ts": time.time(),
    }


def host_package_hold(body: dict[str, Any]) -> dict[str, Any]:
    package = str(body.get("package") or "")
    hold = bool(body.get("hold", True))
    if not PKG_RE.fullmatch(package):
        return {"ok": False, "error": "invalid_package", "http": 400}
    # Only allow hold/unhold for packages that appear in upgradable or held lists.
    inventory = host_packages()
    known = {p.get("name") for p in inventory.get("packages") or [] if isinstance(p, dict)}
    known.update(inventory.get("held") or [])
    if package not in known:
        # Also accept exact installed name via dpkg -s
        nsenter = _nsenter_bin()
        check = (
            _run([nsenter, "--mount=/proc/1/ns/mnt", "--", "/usr/bin/dpkg-query", "-W", "-f=${Package}", package], timeout=10)
            if nsenter
            else _run(["dpkg-query", "-W", "-f=${Package}", package], timeout=10)
        )
        if (check.get("stdout") or "").strip() != package:
            return {"ok": False, "error": "package_not_installed", "http": 404}
    action = "hold" if hold else "unhold"
    nsenter = _nsenter_bin()
    argv = (
        [nsenter, "--mount=/proc/1/ns/mnt", "--", "/usr/bin/apt-mark", action, package]
        if nsenter
        else ["apt-mark", action, package]
    )
    result = _run(argv, timeout=30)
    audit(f"package {action} package={package} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "package": package, "hold": hold, **result}


def host_processes() -> dict[str, Any]:
    """Top processes by CPU.

    Fixed `-o` columns instead of parsing the `ps aux` header: on a busy host
    the output exceeds the truncation cap, and keeping the head is what makes
    the highest-CPU rows (the point of this view) survive.
    """
    args = ["-eo", "pid,user:24,pcpu,pmem,rss,comm,args", "--sort=-pcpu", "--no-headers"]
    nsenter = _nsenter_bin()
    if nsenter:
        result = _run(
            [nsenter, "--mount=/proc/1/ns/mnt", "--", "/bin/ps", *args],
            timeout=10,
            max_output=100_000,
            keep="head",
        )
    else:
        ps = _which("ps")
        if not ps:
            return {"unavailable": True, "reason": "ps_missing", "processes": []}
        result = _run([ps, *args], timeout=10, max_output=100_000, keep="head")
    processes = []
    for line in result["stdout"].splitlines()[:25]:
        values = line.split(None, 6)
        if len(values) < 7:
            continue
        processes.append(
            {
                "pid": _number(values[0]),
                "user": values[1],
                "cpu": _number(values[2]),
                "mem": _number(values[3]),
                "rss_kb": _number(values[4]),
                "name": values[5],
                "command": values[6],
            }
        )
    return {"unavailable": result["exit"] != 0, "processes": processes, "ts": time.time()}


def _nsenter_bin() -> str | None:
    path = _which("nsenter") or "/usr/bin/nsenter"
    return path if Path(path).is_file() else None


def _systemctl_argv(*args: str, unit: str | None = None) -> list[str] | None:
    """Run host systemctl via mount-namespace enter.

    Container systemctl sees /.dockerenv and refuses ("Running in chroot")
    even with pid: host and /run mounted. Host binary under host mount ns works.
    """
    nsenter = _nsenter_bin()
    if not nsenter:
        return None
    host_systemctl = "/bin/systemctl"
    cmd = [nsenter, "--mount=/proc/1/ns/mnt", "--", host_systemctl]
    if unit and unit in SYSTEMD_USER_UNITS:
        cmd += [f"--machine={SYSTEMD_USER}@", "--user"]
    cmd.extend(args)
    return cmd


def host_systemd() -> dict[str, Any]:
    if not _nsenter_bin():
        return {"unavailable": True, "reason": "nsenter_missing", "units": []}
    units = []
    for unit in SYSTEMD_ALLOW:
        active_cmd = _systemctl_argv("is-active", unit, unit=unit)
        enabled_cmd = _systemctl_argv("is-enabled", unit, unit=unit)
        if not active_cmd or not enabled_cmd:
            continue
        active = _run(active_cmd, timeout=8)
        enabled = _run(enabled_cmd, timeout=8)
        units.append(
            {
                "unit": unit,
                "active": active["stdout"].strip() or "unknown",
                "enabled": enabled["stdout"].strip() or "unknown",
                "restartable": True,
                "user": unit in SYSTEMD_USER_UNITS,
            }
        )
    return {"unavailable": False, "units": units, "items": units, "ts": time.time()}


def host_cron() -> dict[str, Any]:
    root_lines: list[str] = []
    error = None
    nsenter = _nsenter_bin()
    if nsenter:
        result = _run(
            [nsenter, "--mount=/proc/1/ns/mnt", "--", "/usr/bin/crontab", "-l", "-u", "root"],
            timeout=8,
        )
    else:
        crontab = _which("crontab")
        result = _run([crontab, "-l", "-u", "root"], timeout=8) if crontab else {"exit": 127, "stdout": "", "stderr": "crontab_missing"}
    if result["exit"] == 0:
        root_lines = [
            line for line in result["stdout"].splitlines() if line.strip() and not line.lstrip().startswith("#")
        ]
    elif "no crontab" not in (result.get("stderr") or "").lower():
        error = (result.get("stderr") or "").strip() or None
    cron_d = []
    # Prefer host cron.d via nsenter listing when available
    if nsenter:
        listing = _run(
            [nsenter, "--mount=/proc/1/ns/mnt", "--", "/bin/ls", "-1", "/etc/cron.d"],
            timeout=8,
        )
        if listing["exit"] == 0:
            cron_d = sorted(
                name for name in listing["stdout"].splitlines() if name and not name.startswith(".")
            )
    if not cron_d:
        cron_dir = Path("/etc/cron.d")
        if cron_dir.is_dir():
            cron_d = sorted(p.name for p in cron_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    return {
        "root_crontab": root_lines,
        "root_crontab_raw": result["stdout"] if result["exit"] == 0 else "",
        "cron_d_files": cron_d,
        "error": error,
        "ts": time.time(),
    }


def host_cron_save(body: dict[str, Any]) -> dict[str, Any]:
    """Replace the root crontab after a backup + syntax sanity check."""
    text = body.get("crontab")
    if not isinstance(text, str):
        return {"ok": False, "error": "crontab_must_be_string", "http": 400}
    if len(text) > 200_000:
        return {"ok": False, "error": "crontab_too_large", "http": 400}
    # Reject shell metacharacters outside comments — crontab lines are schedule + command.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if any(tok in stripped for tok in ("\x00",)):
            return {"ok": False, "error": "unsafe_crontab", "http": 400}
    backup_dir = OPS_ROOT / "state" / "cron-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    current = host_cron()
    backup_path = backup_dir / f"root-{stamp}.crontab"
    try:
        backup_path.write_text(current.get("root_crontab_raw") or "", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"backup_failed:{exc}", "http": 500}
    nsenter = _nsenter_bin()
    # Pipe new crontab into crontab -
    if nsenter:
        proc = subprocess.run(
            [nsenter, "--mount=/proc/1/ns/mnt", "--", "/usr/bin/crontab", "-", "-u", "root"],
            input=text,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            check=False,
        )
    else:
        crontab = _which("crontab")
        if not crontab:
            return {"ok": False, "error": "crontab_missing", "http": 503}
        proc = subprocess.run(
            [crontab, "-", "-u", "root"],
            input=text,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            check=False,
        )
    audit(f"cron save exit={proc.returncode} backup={backup_path.name}")
    return {
        "ok": proc.returncode == 0,
        "backup": str(backup_path),
        "exit": proc.returncode,
        "stderr": (proc.stderr or "")[-2000:],
        "stdout": (proc.stdout or "")[-2000:],
    }


def _name_matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _name_denied(name: str) -> bool:
    return _name_matches(name, CONTAINER_DENY)


def _name_allowed(name: str) -> bool:
    return not _name_denied(name) and _name_matches(name, CONTAINER_ALLOW)


def _name_log_allowed(name: str) -> bool:
    return not _name_denied(name) and _name_matches(name, CONTAINER_LOG_ALLOW)


def containers() -> dict[str, Any]:
    stats: dict[str, dict[str, str]] = {}
    stat_result = _run(
        [_docker_bin(), "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"],
        timeout=25,
    )
    for line in stat_result["stdout"].splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            stats[parts[0]] = {"cpu": parts[1], "mem": parts[2]}
    result = _run([_docker_bin(), "ps", "-a", "--format", "{{json .}}"], timeout=25)
    if result["exit"] != 0:
        return {"ok": False, "error": result["stderr"], "containers": [], "counts": {}}
    rows = []
    counts = {"running": 0, "exited": 0, "paused": 0, "other": 0, "total": 0}
    for item in _json_lines(result["stdout"]):
        if not isinstance(item, dict):
            continue
        name = str(item.get("Names") or item.get("Name") or "").lstrip("/").split(",")[0]
        state = str(item.get("State") or item.get("Status") or "unknown").lower()
        status = "running" if "running" in state else "exited" if "exited" in state else "paused" if "paused" in state else "other"
        counts[status] += 1
        counts["total"] += 1
        labels = item.get("Labels") or ""
        label_map = {}
        if isinstance(labels, str):
            label_map = dict(part.split("=", 1) for part in labels.split(",") if "=" in part)
        elif isinstance(labels, dict):
            label_map = labels
        rows.append(
            {
                "name": name,
                "id": str(item.get("ID") or item.get("Id") or "")[:12],
                "status": status,
                "status_raw": item.get("Status"),
                "image": item.get("Image"),
                "project": label_map.get("com.docker.compose.project", ""),
                "service": label_map.get("com.docker.compose.service", ""),
                "ports": item.get("Ports") or "",
                "cpu": stats.get(name, {}).get("cpu", ""),
                "mem": stats.get(name, {}).get("mem", ""),
                "mutable": _name_allowed(name),
                "loggable": _name_log_allowed(name),
            }
        )
    return {"ok": True, "containers": rows, "counts": counts, "ts": time.time()}


def container_logs(name: str, tail: int, since: str | None) -> dict[str, Any]:
    if not _name_log_allowed(name):
        return {"ok": False, "error": "forbidden", "http": 403}
    args = ["logs", "--timestamps", "--tail", str(max(1, min(tail, 2000)))]
    if since:
        if not re.fullmatch(r"[0-9T:+._Z-]{1,40}|[0-9]{1,7}[smhd]", since):
            return {"ok": False, "error": "invalid_since", "http": 400}
        args += ["--since", since]
    result = _run([_docker_bin(), *args, name], timeout=45, max_output=500_000)
    return {
        "ok": result["exit"] == 0,
        "name": name,
        "logs": result["stdout"] + result["stderr"],
        "exit": result["exit"],
    }


def _redact_inspect(value: Any) -> Any:
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            if key == "Env" and isinstance(child, list):
                output[key] = [f"{entry.split('=', 1)[0]}=***" for entry in child]
            else:
                output[key] = _redact_inspect(child)
        return output
    if isinstance(value, list):
        return [_redact_inspect(child) for child in value]
    return value


def container_inspect(name: str) -> dict[str, Any]:
    if not _name_log_allowed(name):
        return {"ok": False, "error": "forbidden", "http": 403}
    result = _run([_docker_bin(), "inspect", name], timeout=20)
    if result["exit"] != 0:
        return {"ok": False, "error": result["stderr"], "http": 404}
    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_docker_json", "http": 502}
    return {"ok": True, "name": name, "inspect": _redact_inspect(data)}


def container_action(name: str, action: str) -> dict[str, Any]:
    if action not in {"start", "stop", "restart", "kill"}:
        return {"ok": False, "error": "invalid_action", "http": 400}
    if not _name_allowed(name):
        audit(f"container {action} name={name} denied")
        return {"ok": False, "error": "forbidden", "http": 403}
    result = _run([_docker_bin(), action, name], timeout=75)
    audit(f"container {action} name={name} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "name": name, "action": action, **result}


def _inspect_container_raw(name: str) -> tuple[dict[str, Any] | None, str | None]:
    result = _run([_docker_bin(), "inspect", name], timeout=20)
    if result["exit"] != 0:
        return None, result["stderr"] or "inspect_failed"
    try:
        rows = json.loads(result["stdout"])
        return rows[0], None
    except (json.JSONDecodeError, IndexError, TypeError):
        return None, "invalid_inspect_json"


def _compose_recreate_from_labels(inspect: dict[str, Any]) -> dict[str, Any] | None:
    labels = inspect.get("Config", {}).get("Labels") or {}
    service = labels.get("com.docker.compose.service")
    working = labels.get("com.docker.compose.project.working_dir")
    files = labels.get("com.docker.compose.project.config_files")
    if not service or not files:
        return None
    config = files.split(",")[0]
    resolved = _resolve_compose_file(config)
    if resolved is None:
        return None
    cmd = [_docker_bin(), "compose", "-f", str(resolved), "up", "-d", "--force-recreate", service]
    result = _run(cmd, timeout=240)
    return {"method": "compose", "file": str(resolved), "service": service, **result}


def _reconstruct_run_args(name: str, inspect: dict[str, Any]) -> list[str]:
    config = inspect.get("Config") or {}
    host = inspect.get("HostConfig") or {}
    args = [_docker_bin(), "run", "-d", "--name", name]
    restart = (host.get("RestartPolicy") or {}).get("Name")
    if restart and restart != "no":
        maximum = (host.get("RestartPolicy") or {}).get("MaximumRetryCount", 0)
        policy = f"{restart}:{maximum}" if restart == "on-failure" and maximum else restart
        args += ["--restart", policy]
    if host.get("Privileged"):
        args.append("--privileged")
    network = host.get("NetworkMode")
    if network and network not in {"default", "bridge"}:
        args += ["--network", network]
    for env_value in config.get("Env") or []:
        args += ["-e", env_value]
    for mount in inspect.get("Mounts") or []:
        source, destination = mount.get("Source"), mount.get("Destination")
        if source and destination:
            spec = f"{source}:{destination}"
            if not mount.get("RW", True):
                spec += ":ro"
            args += ["-v", spec]
    for container_port, bindings in (host.get("PortBindings") or {}).items():
        for binding in bindings or []:
            host_port = binding.get("HostPort")
            if not host_port:
                continue
            host_ip = binding.get("HostIp")
            published = f"{host_ip}:{host_port}:{container_port}" if host_ip else f"{host_port}:{container_port}"
            args += ["-p", published]
    for device in host.get("Devices") or []:
        source, destination = device.get("PathOnHost"), device.get("PathInContainer")
        if source and destination:
            args += ["--device", f"{source}:{destination}:{device.get('CgroupPermissions', 'rwm')}"]
    if config.get("User"):
        args += ["--user", str(config["User"])]
    if config.get("WorkingDir"):
        args += ["--workdir", str(config["WorkingDir"])]
    entrypoint = config.get("Entrypoint")
    if isinstance(entrypoint, list) and entrypoint:
        args += ["--entrypoint", entrypoint[0]]
    elif isinstance(entrypoint, str) and entrypoint:
        args += ["--entrypoint", entrypoint]
    args.append(str(config.get("Image") or inspect.get("Image")))
    if isinstance(entrypoint, list) and len(entrypoint) > 1:
        args.extend(str(value) for value in entrypoint[1:])
    command = config.get("Cmd")
    if isinstance(command, list):
        args.extend(str(value) for value in command)
    elif isinstance(command, str):
        args.extend(shlex.split(command))
    return args


def container_recreate(name: str, pull: bool = False, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if not _name_allowed(name):
        audit(f"container recreate name={name} denied")
        return {"ok": False, "error": "forbidden", "http": 403}
    inspect, error = _inspect_container_raw(name)
    if inspect is None:
        return {"ok": False, "error": error, "http": 404}
    image = str((inspect.get("Config") or {}).get("Image") or "")
    if pull:
        if not _image_allowed(image):
            return {"ok": False, "error": "image_pull_forbidden", "http": 403}
        pulled = _run([_docker_bin(), "pull", image], timeout=600)
        if pulled["exit"] != 0:
            return {"ok": False, "error": "pull_failed", "pull": pulled}
    overrides = overrides or {}
    has_overrides = any(
        overrides.get(key) not in (None, "", [], {})
        for key in ("env_set", "env_unset", "memory", "cpus", "restart_policy")
    )
    if not has_overrides:
        compose_result = _compose_recreate_from_labels(inspect)
        if compose_result is not None:
            audit(f"container recreate name={name} method=compose exit={compose_result['exit']}")
            return {"ok": compose_result["exit"] == 0, "name": name, **compose_result}
    run_args = _reconstruct_run_args(name, inspect)
    if has_overrides:
        run_args, oerr = apply_recreate_overrides(run_args, overrides)
        if oerr or run_args is None:
            return {"ok": False, "error": oerr, "http": 400}
    stop = _run([_docker_bin(), "stop", name], timeout=75)
    if stop["exit"] != 0:
        audit(f"container recreate name={name} stop_failed")
        return {"ok": False, "error": "stop_failed", "detail": stop}
    remove = _run([_docker_bin(), "rm", name], timeout=30)
    if remove["exit"] != 0:
        audit(f"container recreate name={name} remove_failed")
        return {"ok": False, "error": "remove_failed", "detail": remove}
    created = _run(run_args, timeout=120)
    audit(f"container recreate name={name} method=reconstructed exit={created['exit']} overrides={has_overrides}")
    return {
        "ok": created["exit"] == 0,
        "name": name,
        "method": "reconstructed",
        "warning": "compose metadata unavailable; recreated from inspect subset"
        if not has_overrides
        else "recreated with operator overrides",
        **created,
    }


def container_rename(name: str, new_name: str) -> dict[str, Any]:
    if not _name_allowed(name):
        audit(f"container rename name={name} denied")
        return {"ok": False, "error": "forbidden", "http": 403}
    if not validate_container_name(new_name):
        return {"ok": False, "error": "invalid_new_name", "http": 400}
    if not _name_allowed(new_name):
        return {"ok": False, "error": "new_name_forbidden", "http": 403}
    result = _run([_docker_bin(), "rename", name, new_name], timeout=30)
    audit(f"container rename {name}->{new_name} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "name": name, "new_name": new_name, **result}


def container_stats(name: str) -> dict[str, Any]:
    if not _name_allowed(name) and not _name_log_allowed(name):
        # Allow stats for allowlisted containers; deny list still wins.
        if _name_denied(name) or not _name_matches(name, CONTAINER_ALLOW + CONTAINER_LOG_ALLOW):
            return {"ok": False, "error": "forbidden", "http": 403}
    result = _run(
        [
            _docker_bin(),
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            name,
        ],
        timeout=20,
    )
    if result["exit"] != 0:
        return {"ok": False, "error": result["stderr"] or "stats_failed", **result}
    rows = _json_lines(result["stdout"])
    row = rows[0] if rows else {}
    return {"ok": True, "name": name, "stats": row, "ts": time.time()}


def docker_image_remove(body: dict[str, Any]) -> dict[str, Any]:
    ref = str(body.get("ref") or body.get("image") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,254}", ref):
        return {"ok": False, "error": "invalid_ref", "http": 400}
    # Find containers referencing this image (running or stopped).
    listing = _run(
        [_docker_bin(), "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.ImageID}}"],
        timeout=30,
        max_output=500_000,
        keep="head",
    )
    blockers = []
    for line in (listing.get("stdout") or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        image_name, image_id = parts[2], parts[3]
        if ref == image_name or ref in image_id or image_id.endswith(ref) or ref.endswith(image_id):
            blockers.append({"id": parts[0], "name": parts[1], "image": image_name})
        elif ref.split(":")[0] == image_name.split(":")[0] and ":" in ref and ref == image_name:
            blockers.append({"id": parts[0], "name": parts[1], "image": image_name})
    if blockers:
        return {
            "ok": False,
            "error": "image_in_use",
            "http": 409,
            "containers": blockers,
        }
    result = _run([_docker_bin(), "rmi", ref], timeout=120)
    audit(f"image remove ref={ref} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "ref": ref, **result}


def container_exec(name: str, body: dict[str, Any]) -> dict[str, Any]:
    if not _name_allowed(name):
        audit(f"container exec name={name} denied")
        return {"ok": False, "error": "forbidden", "http": 403}
    command = body.get("cmd")
    if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
        return {"ok": False, "error": "cmd_must_be_nonempty_argv_list", "http": 400}
    if any(not arg or _META_RE.search(arg) for arg in command):
        return {"ok": False, "error": "unsafe_argument", "http": 400}
    if Path(command[0]).name.lower() in _FORBIDDEN_EXEC:
        return {"ok": False, "error": "forbidden_command", "http": 403}
    try:
        timeout = max(1, min(int(body.get("timeout", 30)), 60))
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_timeout", "http": 400}
    result = _run([_docker_bin(), "exec", name, *command], timeout=timeout, max_output=200_000)
    audit(f"container exec name={name} cmd={command[0]} argc={len(command)} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "name": name, "cmd": command, **result}


def _compose_files_under(root: Path) -> list[Path]:
    candidates = []
    for name in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
        if (root / name).is_file():
            candidates.append(root / name)
    compose_dir = root / "compose"
    if compose_dir.is_dir():
        for pattern in ("docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml"):
            candidates.extend(compose_dir.glob(pattern))
    seen = set()
    output = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            output.append(resolved)
    return sorted(output)


def _resolve_compose_file(file_path: str) -> Path | None:
    try:
        target = Path(file_path).resolve(strict=True)
    except OSError:
        return None
    if not target.is_file():
        return None
    for directory in COMPOSE_DIRS:
        try:
            target.relative_to(Path(directory).resolve(strict=True))
            return target
        except (OSError, ValueError):
            continue
    return None


def _yaml_service_names(path: Path, limit: int = 40) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    services: list[str] = []
    in_services = False
    for line in text.splitlines()[:500]:
        if re.match(r"^services:\s*$", line):
            in_services = True
            continue
        if in_services:
            if re.match(r"^[^\s#]", line) and not line.startswith("services"):
                break
            m = re.match(r"^  ([A-Za-z0-9._-]+):\s*$", line)
            if m:
                services.append(m.group(1))
                if len(services) >= limit:
                    break
    return services


def _file_preview(path: Path, lines: int = 40) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:lines])
    except OSError:
        return ""


def _running_compose_projects() -> set[str]:
    projects: set[str] = set()
    result = _run([_docker_bin(), "ps", "--format", "{{json .}}"], timeout=20)
    for row in _json_lines(result["stdout"]):
        labels = row.get("Labels") or ""
        if isinstance(labels, str):
            for part in labels.split(","):
                if part.startswith("com.docker.compose.project="):
                    projects.add(part.split("=", 1)[1])
        elif isinstance(labels, dict):
            p = labels.get("com.docker.compose.project")
            if p:
                projects.add(p)
    return projects


def stacks() -> dict[str, Any]:
    """Flat stack rows for Ops UI: one entry per compose file (dir/file/services/…)."""
    running = _running_compose_projects()
    units: list[dict[str, Any]] = []
    for directory in COMPOSE_DIRS:
        root = Path(directory)
        if not root.is_dir():
            units.append(
                {
                    "dir": directory,
                    "exists": False,
                    "file": None,
                    "project_hint": "",
                    "running_hint": False,
                    "services": [],
                    "preview": "",
                    "risky": False,
                }
            )
            continue
        files = _compose_files_under(root)
        if not files:
            units.append(
                {
                    "dir": directory,
                    "exists": True,
                    "file": None,
                    "project_hint": "",
                    "running_hint": False,
                    "services": [],
                    "preview": "",
                    "risky": False,
                }
            )
            continue
        for compose_file in files:
            stem = compose_file.stem.replace("docker-compose.", "").replace("compose.", "")
            project_hint = stem if stem not in ("yml", "yaml", "") else root.name
            proj_candidates = {root.name, project_hint, compose_file.parent.name}
            name_l = str(compose_file).lower()
            risky = bool(re.search(r"sim|gazebo|sitl", name_l))
            units.append(
                {
                    "dir": directory,
                    "exists": True,
                    "file": str(compose_file),
                    "project_hint": project_hint,
                    "running_hint": bool(proj_candidates & running),
                    "services": _yaml_service_names(compose_file),
                    "preview": _file_preview(compose_file),
                    "risky": risky,
                }
            )
    return {"stacks": units, "ts": time.time()}


def stacks_mutate(action: str, body: dict[str, Any]) -> dict[str, Any]:
    commands = {
        "up": ["up", "-d"],
        "down": ["down"],
        "restart": ["restart"],
        "pull": ["pull"],
        "rebuild": ["up", "-d", "--build"],
    }
    if action not in commands:
        return {"ok": False, "error": "invalid_action", "http": 400}
    compose_file = _resolve_compose_file(str(body.get("file") or ""))
    if compose_file is None:
        audit(f"stack {action} file={body.get('file')} denied")
        return {"ok": False, "error": "forbidden_or_missing_file", "http": 403}
    service = body.get("service")
    argv = [_docker_bin(), "compose", "-f", str(compose_file), *commands[action]]
    if service:
        if not isinstance(service, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", service):
            return {"ok": False, "error": "invalid_service", "http": 400}
        argv.append(service)
    result = _run(argv, timeout=600 if action in {"pull", "rebuild"} else 180)
    audit(f"stack {action} file={compose_file} service={service or '*'} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "action": action, "file": str(compose_file), **result}


def docker_info() -> dict[str, Any]:
    result = _run([_docker_bin(), "info", "--format", "{{json .}}"], timeout=25)
    if result["exit"] != 0:
        return {"ok": False, "error": result["stderr"]}
    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_docker_json"}
    keys = (
        "ID",
        "Name",
        "ServerVersion",
        "OperatingSystem",
        "OSType",
        "Architecture",
        "NCPU",
        "MemTotal",
        "DockerRootDir",
        "Driver",
        "CgroupDriver",
        "CgroupVersion",
        "Containers",
        "ContainersRunning",
        "ContainersPaused",
        "ContainersStopped",
        "Images",
        "KernelVersion",
    )
    return {"ok": True, "info": {key: data.get(key) for key in keys}, "ts": time.time()}


def docker_df() -> dict[str, Any]:
    result = _run([_docker_bin(), "system", "df", "--format", "{{json .}}"], timeout=60)
    if result["exit"] == 0:
        return {"ok": True, "rows": _json_lines(result["stdout"]), "ts": time.time()}
    fallback = _run([_docker_bin(), "system", "df"], timeout=60)
    return {
        "ok": fallback["exit"] == 0,
        "rows": [],
        "raw": fallback["stdout"],
        "error": fallback["stderr"],
        "ts": time.time(),
    }


def docker_events(since: str, include_probes: bool = False) -> dict[str, Any]:
    """Recent Docker events, healthcheck probes excluded by default.

    Every container with a healthcheck emits exec_create/exec_start/exec_die on
    each probe. On this host that is 100% of the last hundred events, so the
    lifecycle events worth seeing — start, die, pull, health_status — were
    evicted by the cap before anyone could read them. Filter first, cap after.
    """
    if not _SAFE_EVENT_SINCE_RE.fullmatch(since):
        return {"ok": False, "error": "since_must_be_duration", "http": 400}
    until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = _run(
        [_docker_bin(), "events", "--since", since, "--until", until, "--format", "{{json .}}"],
        timeout=35,
        max_output=2_000_000,
    )
    parsed = _json_lines(result["stdout"])
    probes = 0
    rows = []
    for row in parsed:
        action = str(row.get("Action") or row.get("action") or "") if isinstance(row, dict) else ""
        if action.startswith("exec_"):
            probes += 1
            if not include_probes:
                continue
        rows.append(row)
    return {
        "ok": result["exit"] == 0,
        "events": rows[-200:],
        "since": since,
        "until": until,
        "total": len(parsed),
        "probes_hidden": 0 if include_probes else probes,
        "ts": time.time(),
    }


def docker_images() -> dict[str, Any]:
    result = _run([_docker_bin(), "images", "--format", "{{json .}}"], timeout=30)
    return {
        "ok": result["exit"] == 0,
        "images": _json_lines(result["stdout"]),
        "error": result["stderr"] or result.get("error"),
        "ts": time.time(),
    }


def _safe_docker_object_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", name))


def docker_volumes(inspect_name: str | None) -> dict[str, Any]:
    result = _run([_docker_bin(), "volume", "ls", "--format", "{{json .}}"], timeout=25)
    payload: dict[str, Any] = {
        "ok": result["exit"] == 0,
        "volumes": _json_lines(result["stdout"]),
        "error": result["stderr"] or result.get("error"),
        "ts": time.time(),
    }
    if inspect_name:
        if not _safe_docker_object_name(inspect_name):
            return {"ok": False, "error": "invalid_name", "http": 400}
        inspected = _run([_docker_bin(), "volume", "inspect", inspect_name], timeout=20)
        try:
            payload["inspect"] = json.loads(inspected["stdout"]) if inspected["exit"] == 0 else None
        except json.JSONDecodeError:
            payload["inspect"] = None
        payload["inspect_error"] = inspected["stderr"] or inspected.get("error")
    return payload


def docker_networks(inspect_name: str | None) -> dict[str, Any]:
    result = _run([_docker_bin(), "network", "ls", "--format", "{{json .}}"], timeout=25)
    payload: dict[str, Any] = {
        "ok": result["exit"] == 0,
        "networks": _json_lines(result["stdout"]),
        "error": result["stderr"] or result.get("error"),
        "ts": time.time(),
    }
    if inspect_name:
        if not _safe_docker_object_name(inspect_name):
            return {"ok": False, "error": "invalid_name", "http": 400}
        inspected = _run([_docker_bin(), "network", "inspect", inspect_name], timeout=20)
        try:
            data = json.loads(inspected["stdout"]) if inspected["exit"] == 0 else None
            payload["inspect"] = _redact_inspect(data)
        except json.JSONDecodeError:
            payload["inspect"] = None
        payload["inspect_error"] = inspected["stderr"] or inspected.get("error")
    return payload


def _image_allowed(image: str) -> bool:
    return bool(image) and _name_matches(image, IMAGE_PULL_ALLOW)


def docker_image_pull(body: dict[str, Any]) -> dict[str, Any]:
    image = body.get("image")
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,254}", image):
        return {"ok": False, "error": "invalid_image", "http": 400}
    if not _image_allowed(image):
        audit(f"image pull image={image} denied")
        return {"ok": False, "error": "forbidden", "http": 403}
    result = _run([_docker_bin(), "pull", image], timeout=600, max_output=300_000)
    audit(f"image pull image={image} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "image": image, **result}


def host_systemd_restart(body: dict[str, Any]) -> dict[str, Any]:
    unit = body.get("unit")
    if not isinstance(unit, str) or unit not in SYSTEMD_ALLOW:
        audit(f"systemd restart unit={unit} denied")
        return {"ok": False, "error": "forbidden", "http": 403}
    cmd = _systemctl_argv("restart", unit, unit=unit)
    if not cmd:
        return {"ok": False, "error": "nsenter_missing", "http": 503}
    result = _run(cmd, timeout=90)
    audit(f"systemd restart unit={unit} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "unit": unit, **result}


# --------------------------------------------------------------------------
# Job runner
# --------------------------------------------------------------------------
#
# Long operations used to run inside one synchronous HTTP request, behind a
# 130 s PHP proxy timeout: the browser gave up while the work carried on, so the
# UI reported failure for operations that had succeeded.
#
# Worse, `apt upgrade` on this host would restart dockerd — every pending update
# is docker-ce — which kills the sidecar container *mid-request*. So jobs are
# handed to the host's systemd and their state lives on disk under /ops/jobs,
# visible to both sides. A job therefore survives the sidecar dying, which is
# exactly what an update must do.

JOBS_DIR = OPS_ROOT / "jobs"
_JOB_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-z-]+-[0-9a-f]{6}$")


def _job_paths(job_id: str) -> tuple[Path, Path, Path]:
    return (JOBS_DIR / f"{job_id}.json", JOBS_DIR / f"{job_id}.log", JOBS_DIR / f"{job_id}.rc")


def _job_write(job_id: str, payload: dict[str, Any]) -> None:
    state, _, _ = _job_paths(job_id)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(payload), encoding="utf-8")


def _job_read(job_id: str) -> dict[str, Any] | None:
    state, log, rc = _job_paths(job_id)
    if not state.is_file():
        return None
    try:
        payload = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    # The exit code file is the completion signal: systemd owns the process, so
    # the sidecar cannot wait() on it and must not guess from the log.
    if payload.get("status") == "running" and rc.is_file():
        code = (rc.read_text(encoding="utf-8").strip() or "-1")
        try:
            payload["exit"] = int(code)
        except ValueError:
            payload["exit"] = -1
        payload["status"] = "done" if payload["exit"] == 0 else "failed"
        payload["finished"] = rc.stat().st_mtime
        _job_write(job_id, payload)
    payload["log"] = _read_text(log)[-200_000:]
    payload["log_bytes"] = log.stat().st_size if log.is_file() else 0
    return payload


# kind -> argv template. Nothing an operator types ever reaches these; the only
# variable parts are values the caller has already validated against an
# allowlist (compose file resolved under COMPOSE_DIRS, image against
# IMAGE_PULL_ALLOW).
def _job_argv(kind: str, body: dict[str, Any]) -> tuple[list[str] | None, str | None]:
    if kind == "apt-upgrade":
        apt = "/usr/bin/apt-get"
        return ([apt, "-y", "-o", "Dpkg::Options::=--force-confold", "upgrade"], None)
    if kind == "apt-dry-run":
        return (["/usr/bin/apt-get", "-s", "upgrade"], None)
    if kind == "backup":
        try:
            script = Path(BACKUP_SCRIPT).resolve(strict=True)
            script.relative_to((OPS_ROOT / "bin").resolve(strict=True))
        except (OSError, ValueError):
            return (None, "backup_script_outside_ops_bin_or_missing")
        return ([str(script)], None)
    if kind == "image-pull":
        image = body.get("image")
        if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,254}", image):
            return (None, "invalid_image")
        if not _image_allowed(image):
            return (None, "forbidden")
        return ([_docker_bin(), "pull", image], None)
    if kind == "stack-action":
        action = str(body.get("action") or "")
        commands = {
            "up": ["up", "-d"],
            "down": ["down"],
            "restart": ["restart"],
            "pull": ["pull"],
            "rebuild": ["up", "-d", "--build"],
        }
        if action not in commands:
            return (None, "invalid_action")
        compose_file = _resolve_compose_file(str(body.get("file") or ""))
        if compose_file is None:
            return (None, "forbidden_or_missing_file")
        return ([_docker_bin(), "compose", "-f", str(compose_file), *commands[action]], None)
    if kind == "docker-cleanup":
        try:
            script = Path(DOCKER_CLEANUP_SCRIPT).resolve(strict=True)
            script.relative_to((OPS_ROOT / "bin").resolve(strict=True))
        except (OSError, ValueError):
            return (None, "cleanup_script_outside_ops_bin_or_missing")
        # Curated host script; never invoke docker ... prune from this process.
        return ([str(script), "prune"], None)
    if kind == "ollama-pull":
        model = str(body.get("model") or "")
        if not MODEL_RE.fullmatch(model):
            return (None, "invalid_model")
        # Use curl against local Ollama so the job stays in the host namespace.
        return (
            [
                "/usr/bin/curl",
                "-fsS",
                "-X",
                "POST",
                f"{OLLAMA_URL.rstrip('/')}/api/pull",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps({"name": model, "stream": False}),
            ],
            None,
        )
    return (None, "unknown_kind")


def job_start(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    argv, error = _job_argv(kind, body)
    if argv is None:
        audit(f"job {kind} rejected={error}")
        return {"ok": False, "error": error, "http": 400 if error != "forbidden" else 403}

    nsenter = _nsenter_bin()
    if not nsenter:
        return {"ok": False, "error": "nsenter_missing", "http": 503}

    job_id = f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{kind}-{os.urandom(3).hex()}"
    state, log, rc = _job_paths(job_id)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)

    # Host-side paths: the sidecar sees /ops, systemd on the host sees the real
    # directory the volume comes from.
    host_jobs = _env("HOST_JOBS_DIR", "/ops/jobs", "NC_TOWER_HOST_JOBS_DIR")
    host_log = f"{host_jobs}/{job_id}.log"
    host_rc = f"{host_jobs}/{job_id}.rc"
    inner = " ".join(shlex.quote(part) for part in argv)
    script = f"{inner} > {shlex.quote(host_log)} 2>&1; echo $? > {shlex.quote(host_rc)}"

    launch = [
        nsenter, "--mount=/proc/1/ns/mnt", "--",
        "/usr/bin/systemd-run", f"--unit=nc-tower-{job_id}", "--collect",
        "/bin/sh", "-c", script,
    ]
    _job_write(job_id, {
        "id": job_id,
        "kind": kind,
        "argv": argv,
        "status": "running",
        "started": time.time(),
        "exit": None,
    })
    log.touch(exist_ok=True)
    result = _run(launch, timeout=30)
    audit(f"job start kind={kind} id={job_id} launch_exit={result['exit']}")
    if result["exit"] != 0:
        _job_write(job_id, {
            "id": job_id, "kind": kind, "argv": argv, "status": "failed",
            "started": time.time(), "exit": result["exit"],
            "error": result["stderr"] or "systemd_run_failed",
        })
        return {"ok": False, "error": "systemd_run_failed", "detail": result["stderr"], "id": job_id}
    return {"ok": True, "id": job_id, "kind": kind, "status": "running"}


def job_list() -> dict[str, Any]:
    if not JOBS_DIR.is_dir():
        return {"ok": True, "jobs": []}
    jobs = []
    for state in sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
        payload = _job_read(state.stem)
        if payload:
            payload.pop("log", None)
            jobs.append(payload)
    return {"ok": True, "jobs": jobs, "ts": time.time()}


def job_get(job_id: str) -> dict[str, Any]:
    if not _JOB_ID_RE.fullmatch(job_id):
        return {"ok": False, "error": "invalid_job_id", "http": 400}
    payload = _job_read(job_id)
    if payload is None:
        return {"ok": False, "error": "not_found", "http": 404}
    return {"ok": True, **payload}


def host_updates() -> dict[str, Any]:
    """Pending host updates plus the two facts that decide how risky applying them is."""
    packages = host_packages()
    pending = [row for row in packages.get("packages", []) if row.get("name")]
    # Upgrading docker restarts dockerd, which bounces every container on the
    # box — including this sidecar. The UI has to say so before anyone clicks.
    restarts_docker = [row["name"] for row in pending if row["name"].startswith("docker")]
    nsenter = _nsenter_bin()
    reboot_required = False
    reboot_packages: list[str] = []
    if nsenter:
        check = _run([nsenter, "--mount=/proc/1/ns/mnt", "--", "/bin/cat", "/var/run/reboot-required.pkgs"], timeout=8)
        reboot_required = check["exit"] == 0
        if reboot_required:
            reboot_packages = [line.strip() for line in check["stdout"].splitlines() if line.strip()]
    return {
        "ok": True,
        "unavailable": packages.get("unavailable", False),
        "packages": pending,
        "count": len(pending),
        "restarts_docker": restarts_docker,
        "reboot_required": reboot_required,
        "reboot_packages": sorted(set(reboot_packages)),
        "ts": time.time(),
    }


def host_history(limit: int = 900) -> dict[str, Any]:
    """Memory/swap history.

    The host already records this every 15 minutes; reading the existing file
    beats standing up a second collector that would disagree with the first.
    """
    path = OPS_ROOT / "state" / "memory-trend.jsonl"
    if not path.is_file():
        return {"ok": True, "samples": [], "source": str(path), "unavailable": True}
    samples = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            lines = stream.readlines()[-max(1, min(limit, 5000)):]
    except OSError as exc:
        return {"ok": False, "error": str(exc), "samples": []}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("ts"):
            samples.append(row)
    return {"ok": True, "samples": samples, "source": str(path), "ts": time.time()}


_INBOX_STAMP_RE = re.compile(r"-(\d{8})-(\d{4})\.json$")


def ops_timeline(hours: int = 24) -> dict[str, Any]:
    """Recent ops alerts as events in time, from the inbox files already on disk."""
    inbox = OPS_ROOT / "inbox"
    cutoff = time.time() - max(1, min(hours, 24 * 14)) * 3600
    events = []
    if inbox.is_dir():
        for path in inbox.iterdir():
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
            if mtime < cutoff:
                continue
            row = {"name": path.name, "ts": mtime, "monitor": None, "status": None, "detail": None}
            if path.suffix.lower() == ".json":
                row.update(_parse_alert(path) or {})
            events.append(row)
    events.sort(key=lambda row: row["ts"])
    return {"ok": True, "events": events, "hours": hours, "ts": time.time()}


# Deep-linked services. Empty by default — set NC_TOWER_SERVICE_TARGETS
# (name=url CSV) on the host. Any HTTP answer means reachable: Guacamole and
# MediaMTX both return 404 at / while perfectly healthy, so only a connection
# failure counts as down.
SERVICE_TARGETS = _csv_env(
    "SERVICE_TARGETS",
    "",
    "NC_TOWER_SERVICE_TARGETS",
)


def services_probe() -> dict[str, Any]:
    import urllib.error
    import urllib.request
    import ssl

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    results = []
    for entry in SERVICE_TARGETS:
        if "=" not in entry:
            continue
        name, url = entry.split("=", 1)
        started = time.time()
        status: int | None = None
        reachable = False
        detail = ""
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=4, context=context) as response:
                status = response.status
                reachable = True
        except urllib.error.HTTPError as exc:
            # An HTTP error is still a live service answering.
            status = exc.code
            reachable = True
        except Exception as exc:
            detail = type(exc).__name__
        results.append({
            "name": name,
            "url": url,
            "reachable": reachable,
            "http": status,
            "ms": int((time.time() - started) * 1000),
            "detail": detail,
        })
    return {"ok": True, "services": results, "ts": time.time()}


def backup_run() -> dict[str, Any]:
    try:
        script = Path(BACKUP_SCRIPT).resolve(strict=True)
        allowed_root = (OPS_ROOT / "bin").resolve(strict=True)
        script.relative_to(allowed_root)
    except (OSError, ValueError):
        audit(f"backup script={BACKUP_SCRIPT} denied")
        return {"ok": False, "error": "backup_script_outside_ops_bin_or_missing", "http": 403}
    if not script.is_file():
        return {"ok": False, "error": "backup_script_missing", "http": 404}
    argv = [str(script)] if os.access(script, os.X_OK) else ["bash", str(script)]
    result = _run(argv, timeout=600, max_output=500_000)
    audit(f"backup run script={script} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "script": str(script), **result}


def backup_inventory(retention_days: int = 30) -> dict[str, Any]:
    root = BACKUP_DIR
    items = []
    if root.is_dir():
        for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file() or path.name.startswith("."):
                continue
            st = path.stat()
            age_h = (time.time() - st.st_mtime) / 3600
            items.append(
                {
                    "name": path.name,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "age_hours": round(age_h, 1),
                    "age_days": round(age_h / 24, 2),
                }
            )
    newest = items[0] if items else None
    return {
        "ok": True,
        "dir": str(root),
        "retention_days": retention_days,
        "items": items,
        "count": len(items),
        "newest": newest,
        "stale": (not newest) or (newest["age_hours"] > 48),
        "ts": time.time(),
    }


def backup_delete(body: dict[str, Any]) -> dict[str, Any]:
    filename = str(body.get("file") or body.get("name") or "")
    path = backup_path_contained(BACKUP_DIR, filename)
    if path is None:
        return {"ok": False, "error": "invalid_or_missing_file", "http": 400}
    try:
        path.unlink()
    except OSError as exc:
        audit(f"backup delete file={filename} error={exc}")
        return {"ok": False, "error": str(exc), "http": 500}
    audit(f"backup delete file={filename}")
    return {"ok": True, "file": filename}


def host_smart_attributes(device: str) -> dict[str, Any]:
    if not DEV_RE.fullmatch(device or ""):
        return {"ok": False, "error": "invalid_device", "http": 400}
    ctl = _which(SMARTCTL) or _which("smartctl")
    if not ctl:
        return {"ok": False, "error": "smartctl_missing", "http": 503}
    result = _run([ctl, "-x", "-j", device], timeout=40, max_output=500_000)
    try:
        payload = json.loads(result["stdout"] or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "smartctl_json_parse_failed", "stdout": (result["stdout"] or "")[:500]}
    rows = parse_smart_attributes(payload)
    return {
        "ok": True,
        "device": device,
        "model": (payload.get("model_name") or payload.get("scsi_model_name")),
        "serial": payload.get("serial_number"),
        "attributes": rows,
        "ts": time.time(),
    }


def host_network() -> dict[str, Any]:
    payload = host_network_payload(run=_run, nsenter_bin=_nsenter_bin, public_ip_cache=_PUBLIC_IP_CACHE)
    try:
        return extend_network_depth(payload, run=_run, nsenter_bin=_nsenter_bin)
    except Exception as exc:  # noqa: BLE001
        payload["network_depth_error"] = str(exc)
        return payload


def host_hardware() -> dict[str, Any]:
    try:
        return collect_hardware(run=_run, nsenter_bin=_nsenter_bin, host_proc=HOST_PROC)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "unavailable": True, "reason": str(exc)}


def host_storage() -> dict[str, Any]:
    try:
        ctl = _which(SMARTCTL) or _which("smartctl")
        return collect_storage(run=_run, nsenter_bin=_nsenter_bin, smartctl=ctl)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "unavailable": True, "reason": str(exc)}


def host_temperatures() -> dict[str, Any]:
    try:
        chassis = host_chassis_fan()
    except Exception:  # noqa: BLE001
        chassis = {}
    try:
        gpu = host_gpu()
    except Exception:  # noqa: BLE001
        gpu = {}
    try:
        smart = host_smart()
    except Exception:  # noqa: BLE001
        smart = {}
    return collect_temperatures(chassis_status=chassis, gpu_payload=gpu, smart_payload=smart)


def host_posture() -> dict[str, Any]:
    targets = _csv_env("SERVICE_TARGETS", "", "NC_TOWER_SERVICE_TARGETS")
    try:
        return collect_posture(run=_run, nsenter_bin=_nsenter_bin, service_targets=targets)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "unavailable": True, "reason": str(exc)}


def host_kernel_log_get(minutes: int = 60) -> dict[str, Any]:
    try:
        return collect_kernel_log(run=_run, nsenter_bin=_nsenter_bin, minutes=minutes)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "unavailable": True, "reason": str(exc)}


def _smart_trend_disks() -> list[dict[str, Any]]:
    payload = host_smart()
    disks = []
    for d in payload.get("disks") or payload.get("items") or []:
        if not isinstance(d, dict):
            continue
        disks.append(
            {
                "device": d.get("device") or d.get("name"),
                "serial": d.get("serial") or d.get("serial_number"),
                "model": d.get("model"),
                "temp_c": d.get("temp_c"),
                "reallocated": d.get("reallocated") or d.get("reallocated_sector_ct"),
                "pending": d.get("pending") or d.get("current_pending_sector"),
                "power_on_hours": d.get("power_on_hours"),
                "health": d.get("health"),
            }
        )
    return disks


def host_smart_history(hours: int = 24) -> dict[str, Any]:
    path = OPS_ROOT / "state" / "smart-trend.jsonl"
    result = smart_history_read(path, hours=hours)
    if result.get("ok"):
        result["summary"] = smart_history_summarize(result.get("samples") or [])
    return result


def host_ollama() -> dict[str, Any]:
    payload = ollama_get(OLLAMA_URL)
    try:
        gpu = host_gpu()
        payload["vram"] = [
            {
                "name": g.get("name"),
                "mem_used_mib": g.get("mem_used_mib"),
                "mem_total_mib": g.get("mem_total_mib"),
            }
            for g in (gpu.get("gpus") or gpu.get("items") or [])
            if isinstance(g, dict)
        ]
    except Exception:  # noqa: BLE001
        payload["vram"] = []
    nsenter = _nsenter_bin()
    tunnel: dict[str, Any] = {"unavailable": True, "reason": "not_configured"}
    for unit in ("cloudflared.service", "ollama-tunnel.service"):
        argv = (
            [nsenter, "--mount=/proc/1/ns/mnt", "--", "/bin/systemctl", "is-active", unit]
            if nsenter
            else ["systemctl", "is-active", unit]
        )
        result = _run(argv, timeout=5)
        state = (result.get("stdout") or "").strip()
        if state in {"active", "inactive", "failed"}:
            tunnel = {"unavailable": False, "unit": unit, "state": state}
            break
    payload["tunnel"] = tunnel
    return payload


def host_ollama_models(body: dict[str, Any]) -> dict[str, Any]:
    op = str(body.get("op") or "")
    model = str(body.get("model") or "")
    if op == "pull":
        if not MODEL_RE.fullmatch(model):
            return {"ok": False, "error": "invalid_model", "http": 400}
        return job_start("ollama-pull", {"model": model})
    if op == "delete":
        inventory = ollama_get(OLLAMA_URL)
        names = {
            str(m.get("name") or m.get("model") or "")
            for m in (inventory.get("models") or [])
            if isinstance(m, dict)
        }
        running = {
            str(m.get("name") or m.get("model") or "")
            for m in (inventory.get("running") or [])
            if isinstance(m, dict)
        }
        if model not in names:
            return {"ok": False, "error": "model_not_in_inventory", "http": 404}
        if model in running and not body.get("force"):
            return {"ok": False, "error": "model_running", "http": 409, "running": True}
        result = ollama_delete(OLLAMA_URL, model)
        audit(f"ollama delete model={model} ok={result.get('ok')}")
        return result
    return {"ok": False, "error": "invalid_op", "http": 400}


def ops_audit(limit: int = 200) -> dict[str, Any]:
    return audit_tail(AUDIT_LOG, limit)


def _parse_alert(path: Path) -> dict[str, Any] | None:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                return {
                    "monitor": data.get("monitor"),
                    "status": data.get("status"),
                    "detail": data.get("detail"),
                }
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _backup_summary() -> dict[str, Any]:
    inbox = OPS_ROOT / "inbox"
    files = sorted(
        (path for path in inbox.glob("backup-*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if inbox.is_dir() else []
    if not files:
        return {"ok": True, "status": "ok", "summary": "no backup issue file", "stale": True}
    newest = files[0]
    parsed = _parse_alert(newest) or {}
    age_h = (time.time() - newest.stat().st_mtime) / 3600
    status = str(parsed.get("status") or "warn").lower()
    return {
        "ok": status in {"ok", "info"},
        "status": status,
        "summary": parsed.get("detail") or parsed.get("monitor") or "backup alert",
        "name": newest.name,
        "mtime": newest.stat().st_mtime,
        "age_hours": round(age_h, 1),
        "stale": age_h > 26,
    }


def ops_inbox_summary() -> dict[str, Any]:
    inbox = OPS_ROOT / "inbox"
    state = OPS_ROOT / "state"
    recent = []
    if inbox.is_dir():
        candidates = sorted(
            (path for path in inbox.iterdir() if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:50]
        for path in candidates:
            row = {
                "name": path.name,
                "mtime": path.stat().st_mtime,
                "size": path.stat().st_size,
                "monitor": None,
                "status": None,
                "detail": None,
            }
            if path.suffix.lower() == ".json":
                row.update(_parse_alert(path) or {})
            recent.append(row)
    critical = [
        row for row in recent if str(row.get("status") or "").lower() in {"crit", "critical"}
    ]
    audits = sorted(
        state.glob("port-audit-*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if state.is_dir() else []
    return {
        "ops_root": str(OPS_ROOT),
        "inbox_recent": recent,
        "critical_recent": critical,
        "backup": _backup_summary(),
        "port_audit_latest": (
            {"name": audits[0].name, "mtime": audits[0].stat().st_mtime} if audits else None
        ),
        "ts": time.time(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "NCTowerHostAgent/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return {}
        if length < 0 or length > 1_000_000:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _get_authorized(self, path: str) -> bool:
        if not TOKEN:
            if path == "/health":
                return True
            self._send(401, {"ok": False, "error": "unauthorized", "reason": "token_not_configured"})
            return False
        if self.headers.get("X-Ops-Token") != TOKEN:
            self._send(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def _post_authorized(self) -> bool:
        if not TOKEN:
            self._send(403, {"ok": False, "error": "token_required"})
            return False
        if self.headers.get("X-Ops-Token") != TOKEN:
            self._send(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def _result(self, result: dict[str, Any], success: int = 200) -> None:
        code = int(result.pop("http", success if result.get("ok", True) else 500))
        self._send(code, result)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if not self._get_authorized(path):
            return
        query = parse_qs(parsed.query)
        try:
            if path == "/health":
                self._send(
                    200,
                    {
                        "ok": True,
                        "service": "nc-tower-sidecar",
                        "version": SIDECAR_VERSION,
                        "capabilities": CAPABILITIES,
                        "ts": time.time(),
                    },
                )
            elif path == "/host/summary":
                self._send(200, host_summary())
            elif path == "/host/gpu":
                self._send(200, host_gpu())
            elif path == "/host/smart":
                self._send(200, host_smart())
            elif path == "/host/smart/attributes":
                device = (query.get("dev") or query.get("device") or [""])[0]
                self._result(host_smart_attributes(device))
            elif path == "/host/fan":
                self._send(200, host_fan_get())
            elif path == "/host/chassis-fan":
                self._send(200, host_chassis_fan())
            elif path == "/host/chassis-fan/history":
                try:
                    minutes = int((query.get("minutes") or ["60"])[0])
                except ValueError:
                    minutes = 60
                self._send(200, host_chassis_fan_history(minutes))
            elif path == "/host/mounts":
                self._send(200, host_mounts())
            elif path == "/host/packages":
                self._send(200, host_packages())
            elif path == "/host/proc":
                self._send(200, host_processes())
            elif path == "/host/net":
                self._send(200, {"ifaces": _interfaces(), "ts": time.time()})
            elif path == "/host/network":
                self._send(200, host_network())
            elif path == "/host/hardware":
                self._send(200, host_hardware())
            elif path == "/host/storage":
                self._send(200, host_storage())
            elif path == "/host/temperatures":
                self._send(200, host_temperatures())
            elif path == "/host/posture":
                self._send(200, host_posture())
            elif path == "/host/kernel-log":
                try:
                    minutes = int((query.get("minutes") or ["60"])[0])
                except ValueError:
                    minutes = 60
                self._send(200, host_kernel_log_get(minutes))
            elif path == "/host/smart/history":
                try:
                    hours = int((query.get("hours") or ["24"])[0])
                except ValueError:
                    hours = 24
                self._send(200, host_smart_history(hours))
            elif path == "/host/ollama":
                self._send(200, host_ollama())
            elif path == "/host/systemd":
                self._send(200, host_systemd())
            elif path == "/host/cron":
                self._send(200, host_cron())
            elif path == "/containers":
                self._send(200, containers())
            elif (match := re.fullmatch(r"/containers/(.+)/logs", path)):
                name = unquote(match.group(1))
                try:
                    tail = int((query.get("tail") or ["100"])[0])
                except ValueError:
                    self._send(400, {"ok": False, "error": "invalid_tail"})
                    return
                self._result(container_logs(name, tail, (query.get("since") or [None])[0]))
            elif (match := re.fullmatch(r"/containers/(.+)/inspect", path)):
                self._result(container_inspect(unquote(match.group(1))))
            elif (match := re.fullmatch(r"/containers/(.+)/stats", path)):
                self._result(container_stats(unquote(match.group(1))))
            elif path == "/docker/info":
                self._result(docker_info())
            elif path == "/docker/df":
                self._result(docker_df())
            elif path == "/docker/events":
                self._result(docker_events(
                    (query.get("since") or ["1h"])[0],
                    (query.get("probes") or ["0"])[0] in ("1", "true", "yes"),
                ))
            elif path == "/docker/images":
                self._result(docker_images())
            elif path == "/docker/volumes":
                self._result(
                    docker_volumes((query.get("inspect") or query.get("name") or [None])[0])
                )
            elif path == "/docker/networks":
                self._result(
                    docker_networks((query.get("inspect") or query.get("name") or [None])[0])
                )
            elif path == "/stacks":
                self._send(200, stacks())
            elif path == "/ops/inbox-summary":
                self._send(200, ops_inbox_summary())
            elif path == "/ops/timeline":
                try:
                    hours = int((query.get("hours") or ["24"])[0])
                except ValueError:
                    hours = 24
                self._send(200, ops_timeline(hours))
            elif path == "/ops/audit":
                try:
                    limit = int((query.get("limit") or ["200"])[0])
                except ValueError:
                    limit = 200
                self._send(200, ops_audit(limit))
            elif path == "/ops/backup":
                try:
                    retention = int((query.get("retention_days") or ["30"])[0])
                except ValueError:
                    retention = 30
                self._send(200, backup_inventory(retention))
            elif path == "/host/updates":
                self._send(200, host_updates())
            elif path == "/host/history":
                try:
                    limit = int((query.get("limit") or ["900"])[0])
                except ValueError:
                    limit = 900
                self._send(200, host_history(limit))
            elif path == "/services/probe":
                self._send(200, services_probe())
            elif path == "/jobs":
                self._result(job_list())
            elif (match := re.fullmatch(r"/jobs/(.+)", path)):
                self._result(job_get(unquote(match.group(1))))
            else:
                self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:  # defensive HTTP boundary
            audit(f"GET path={path} exception={type(exc).__name__}:{exc}")
            self._send(500, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if not self._post_authorized():
            return
        path = (urlparse(self.path).path.rstrip("/") or "/")
        body = self._read_json()
        try:
            if path == "/host/fan":
                self._result(host_fan_set(body))
                return
            if path == "/host/chassis-fan":
                self._result(host_chassis_fan_set(body))
                return
            if path == "/host/systemd/restart":
                self._result(host_systemd_restart(body))
                return
            if path == "/host/packages/hold":
                self._result(host_package_hold(body))
                return
            if path == "/host/cron":
                self._result(host_cron_save(body))
                return
            if path == "/host/ollama/models":
                self._result(host_ollama_models(body))
                return
            if path == "/docker/images/pull":
                self._result(docker_image_pull(body))
                return
            if path == "/docker/images/remove":
                self._result(docker_image_remove(body))
                return
            if path == "/ops/backup/run":
                self._result(backup_run())
                return
            if path == "/ops/backup/delete":
                self._result(backup_delete(body))
                return
            if match := re.fullmatch(r"/jobs/([a-z-]+)", path):
                self._result(job_start(match.group(1), body))
                return
            if match := re.fullmatch(r"/containers/(.+)/(start|stop|restart|kill)", path):
                self._result(container_action(unquote(match.group(1)), match.group(2)))
                return
            if match := re.fullmatch(r"/containers/(.+)/recreate", path):
                overrides = {
                    "env_set": body.get("env_set"),
                    "env_unset": body.get("env_unset"),
                    "memory": body.get("memory"),
                    "cpus": body.get("cpus"),
                    "restart_policy": body.get("restart_policy"),
                }
                self._result(
                    container_recreate(
                        unquote(match.group(1)),
                        bool(body.get("pull")),
                        overrides,
                    )
                )
                return
            if match := re.fullmatch(r"/containers/(.+)/rename", path):
                self._result(container_rename(unquote(match.group(1)), str(body.get("name") or body.get("new_name") or "")))
                return
            if match := re.fullmatch(r"/containers/(.+)/exec", path):
                self._result(container_exec(unquote(match.group(1)), body))
                return
            if match := re.fullmatch(r"/stacks/(up|down|restart|pull|rebuild)", path):
                self._result(stacks_mutate(match.group(1), body))
                return
            self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:  # defensive HTTP boundary
            audit(f"POST path={path} exception={type(exc).__name__}:{exc}")
            self._send(500, {"ok": False, "error": str(exc)})


def main() -> None:
    controller = _chassis()
    try:
        reapply = controller.re_apply()
        audit(f"chassis-fan startup re-apply ok={reapply.get('ok')}")
    except Exception as exc:  # noqa: BLE001
        audit(f"chassis-fan startup re-apply error={exc}")
    controller.start_sampler()
    global _SMART_SAMPLER
    try:
        _SMART_SAMPLER = SmartTrendSampler(
            OPS_ROOT / "state" / "smart-trend.jsonl",
            _smart_trend_disks,
            interval_s=600,
        )
        _SMART_SAMPLER.start()
        audit("smart-trend sampler started")
    except Exception as exc:  # noqa: BLE001
        audit(f"smart-trend sampler error={exc}")
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    server.daemon_threads = True
    print(
        f"nc-tower-sidecar listening on {BIND}:{PORT} "
        f"version={SIDECAR_VERSION} "
        f"token={'configured' if TOKEN else 'missing-health-only'}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
