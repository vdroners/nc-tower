#!/usr/bin/env python3
"""Control Tower host agent.

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
    ",".join(
        (
            "/media/4TB/nc-tower",
            "/media/4TB/nc-gcs",
            "/media/4TB/nc-print",
            "/media/4TB/ollama",
            "/media/4TB/cloud",
            "/media/4TB/webodm",
            "/media/4TB/caddy-proxy-manager",
            "/media/4TB/wireguard",
            "/media/4TB/guac",
            "/media/4TB/octoslicer",
            "/media/4TB/sim/sim2",
        )
    ),
    "NC_TOWER_COMPOSE_DIRS",
)
DISK_PATHS = _csv_env(
    "DISK_PATHS",
    "/,/media/4TB,/media/6TB,/media/raid5",
    "NC_TOWER_DISK_PATHS",
)
CONTAINER_ALLOW = _csv_env(
    "CONTAINER_ALLOW", "gcs_*,mavlink_gateway,nc_print_*", "NC_TOWER_CONTAINER_ALLOW"
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
    "docker.service,containerd.service,nvidia-persistenced.service",
    "NC_TOWER_SYSTEMD_ALLOW",
)
IMAGE_PULL_ALLOW = _csv_env(
    "IMAGE_PULL_ALLOW",
    "ghcr.io/vdroners/*,docker.io/*,library/*,ollama/ollama:*",
    "NC_TOWER_IMAGE_PULL_ALLOW",
)

_AUDIT_LOCK = threading.Lock()
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
) -> dict[str, Any]:
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
            "stdout": (proc.stdout or "")[-max_output:],
            "stderr": (proc.stderr or "")[-max_output:],
        }
        if check and proc.returncode:
            result["error"] = "command_failed"
        return result
    except subprocess.TimeoutExpired as exc:
        return {
            "exit": None,
            "error": "timeout",
            "stdout": (exc.stdout or "")[-max_output:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-max_output:] if isinstance(exc.stderr, str) else "",
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
    for base in Path("/sys/class/hwmon").glob("hwmon*"):
        name = _read_text(base / "name").strip().lower()
        for source in sorted(base.glob("temp*_input")):
            label = _read_text(source.with_name(source.name.replace("_input", "_label"))).strip().lower()
            if any(token in f"{name} {label}" for token in ("package", "tctl", "cpu", "coretemp", "k10temp")):
                try:
                    value = float(_read_text(source).strip())
                    return round(value / 1000.0 if value > 500 else value, 1)
                except ValueError:
                    continue
    return None


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
    nas_mounts = [row for row in mounts if row["path"].startswith(("/media/raid", "/mnt", "/nas"))]
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

        temp = match(
            [
                r"Temperature_Celsius\s+\S+(?:\s+\S+){7}\s+(\d+)",
                r"Temperature:\s+(\d+)\s+Celsius",
                r"Current Drive Temperature:\s+(\d+)",
            ]
        )
        hours = match(
            [
                r"Power_On_Hours\s+\S+(?:\s+\S+){7}\s+(\d+)",
                r"Power On Hours:\s+([\d,]+)",
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


def host_fan_get() -> dict[str, Any]:
    helper = _fan_helper()
    if not helper:
        return {"unavailable": True, "reason": "fan_helper_missing"}
    result = _run(["python3", helper, "status"], timeout=10)
    if result["exit"] != 0:
        return {"unavailable": True, "reason": result["stderr"] or result.get("error")}
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError:
        payload = {"raw": result["stdout"].strip()}
    return {"unavailable": False, "status": payload, "ts": time.time()}


def host_fan_set(body: dict[str, Any]) -> dict[str, Any]:
    helper = _fan_helper()
    if not helper:
        return {"ok": False, "error": "fan_helper_missing", "http": 503}
    op = str(body.get("op") or "")
    if op == "set-auto":
        args = ["set-auto"]
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
    result = _run(["python3", helper, *args], timeout=20)
    audit(f"fan op={op} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "op": op, **result}


def host_chassis_fan() -> dict[str, Any]:
    chips = []
    flat: list[dict[str, Any]] = []
    for base in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        sensors = []
        chip_name = _read_text(base / "name").strip()
        for source in sorted(base.glob("fan*_input")):
            token = source.stem.split("_")[0]
            pwm_path = base / f"pwm{token.replace('fan', '')}"
            if not pwm_path.is_file():
                # fan1_input -> pwm1
                m = re.match(r"fan(\d+)", token)
                pwm_path = base / f"pwm{m.group(1)}" if m else Path()
            entry = {
                "fan": token,
                "name": (_read_text(base / f"{token}_label").strip() or f"{chip_name}:{token}"),
                "rpm": _number(_read_text(source)),
                "label": _read_text(base / f"{token}_label").strip() or None,
                "pwm": _number(_read_text(pwm_path)) if pwm_path.is_file() else None,
                "chip": chip_name,
                "hwmon": base.name,
                "min_rpm": _number(_read_text(base / f"{token}_min")),
                "max_rpm": _number(_read_text(base / f"{token}_max")),
            }
            sensors.append(entry)
            flat.append(entry)
        pwms = [
            {
                "pwm": source.name,
                "value": _number(_read_text(source)),
                "enable": _number(_read_text(base / f"{source.name}_enable")),
            }
            for source in sorted(base.glob("pwm[0-9]*"))
            if re.fullmatch(r"pwm\d+", source.name)
        ]
        if sensors or pwms:
            chips.append(
                {
                    "hwmon": base.name,
                    "name": chip_name,
                    "fans": sensors,
                    "pwms": pwms,
                }
            )
    return {"chips": chips, "fans": flat, "items": flat, "ts": time.time()}


def host_packages() -> dict[str, Any]:
    apt = _which("apt")
    if not apt:
        return {"unavailable": True, "reason": "apt_missing", "packages": []}
    result = _run([apt, "list", "--upgradable"], timeout=60, max_output=150_000)
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
            }
            if match
            else {"raw": line}
        )
    return {
        "unavailable": result["exit"] != 0,
        "packages": packages,
        "exit": result["exit"],
        "error": result["stderr"] or result.get("error"),
        "ts": time.time(),
    }


def host_processes() -> dict[str, Any]:
    ps = _which("ps")
    if not ps:
        return {"unavailable": True, "reason": "ps_missing", "processes": []}
    result = _run([ps, "aux", "--sort=-%cpu"], timeout=10, max_output=100_000)
    lines = result["stdout"].splitlines()
    header = lines[0].split(None, 10) if lines else []
    processes = []
    for line in lines[1:26]:
        values = line.split(None, 10)
        if len(values) == 11:
            processes.append(dict(zip(header, values)))
    return {"unavailable": result["exit"] != 0, "processes": processes, "ts": time.time()}


def _systemctl_bin() -> str | None:
    # With pid: host, systemctl talks to the real host systemd.
    path = _which("systemctl") or "/usr/bin/systemctl"
    return path if Path(path).is_file() else None


def host_systemd() -> dict[str, Any]:
    systemctl = _systemctl_bin()
    if not systemctl:
        return {"unavailable": True, "reason": "systemctl_missing", "units": []}
    units = []
    for unit in SYSTEMD_ALLOW:
        active = _run([systemctl, "is-active", unit], timeout=8)
        enabled = _run([systemctl, "is-enabled", unit], timeout=8)
        units.append(
            {
                "unit": unit,
                "active": active["stdout"].strip() or "unknown",
                "enabled": enabled["stdout"].strip() or "unknown",
                "restartable": True,
            }
        )
    return {"unavailable": False, "units": units, "items": units, "ts": time.time()}


def host_cron() -> dict[str, Any]:
    root_lines: list[str] = []
    crontab = _which("crontab")
    error = None
    if crontab:
        result = _run([crontab, "-l", "-u", "root"], timeout=8)
        if result["exit"] == 0:
            root_lines = [
                line for line in result["stdout"].splitlines() if line.strip() and not line.lstrip().startswith("#")
            ]
        elif "no crontab" not in result["stderr"].lower():
            error = result["stderr"].strip()
    cron_d = []
    cron_dir = Path("/etc/cron.d")
    if cron_dir.is_dir():
        cron_d = sorted(p.name for p in cron_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    return {"root_crontab": root_lines, "cron_d_files": cron_d, "error": error, "ts": time.time()}


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


def container_recreate(name: str, pull: bool = False) -> dict[str, Any]:
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
    compose_result = _compose_recreate_from_labels(inspect)
    if compose_result is not None:
        audit(f"container recreate name={name} method=compose exit={compose_result['exit']}")
        return {"ok": compose_result["exit"] == 0, "name": name, **compose_result}
    run_args = _reconstruct_run_args(name, inspect)
    stop = _run([_docker_bin(), "stop", name], timeout=75)
    if stop["exit"] != 0:
        audit(f"container recreate name={name} stop_failed")
        return {"ok": False, "error": "stop_failed", "detail": stop}
    remove = _run([_docker_bin(), "rm", name], timeout=30)
    if remove["exit"] != 0:
        audit(f"container recreate name={name} remove_failed")
        return {"ok": False, "error": "remove_failed", "detail": remove}
    created = _run(run_args, timeout=120)
    audit(f"container recreate name={name} method=reconstructed exit={created['exit']}")
    return {
        "ok": created["exit"] == 0,
        "name": name,
        "method": "reconstructed",
        "warning": "compose metadata unavailable; recreated from inspect subset",
        **created,
    }


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


def docker_events(since: str) -> dict[str, Any]:
    if not _SAFE_EVENT_SINCE_RE.fullmatch(since):
        return {"ok": False, "error": "since_must_be_duration", "http": 400}
    until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = _run(
        [_docker_bin(), "events", "--since", since, "--until", until, "--format", "{{json .}}"],
        timeout=35,
        max_output=500_000,
    )
    rows = _json_lines(result["stdout"])[-100:]
    return {"ok": result["exit"] == 0, "events": rows, "since": since, "until": until, "ts": time.time()}


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
    systemctl = _systemctl_bin()
    if not systemctl:
        return {"ok": False, "error": "systemctl_missing", "http": 503}
    result = _run([systemctl, "restart", unit], timeout=90)
    audit(f"systemd restart unit={unit} exit={result['exit']}")
    return {"ok": result["exit"] == 0, "unit": unit, **result}


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
                self._send(200, {"ok": True, "service": "nc-tower-sidecar", "ts": time.time()})
            elif path == "/host/summary":
                self._send(200, host_summary())
            elif path == "/host/gpu":
                self._send(200, host_gpu())
            elif path == "/host/smart":
                self._send(200, host_smart())
            elif path == "/host/fan":
                self._send(200, host_fan_get())
            elif path == "/host/chassis-fan":
                self._send(200, host_chassis_fan())
            elif path == "/host/mounts":
                self._send(200, host_mounts())
            elif path == "/host/packages":
                self._send(200, host_packages())
            elif path == "/host/proc":
                self._send(200, host_processes())
            elif path == "/host/net":
                self._send(200, {"ifaces": _interfaces(), "ts": time.time()})
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
            elif path == "/docker/info":
                self._result(docker_info())
            elif path == "/docker/df":
                self._result(docker_df())
            elif path == "/docker/events":
                self._result(docker_events((query.get("since") or ["1h"])[0]))
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
            if path == "/host/systemd/restart":
                self._result(host_systemd_restart(body))
                return
            if path == "/docker/images/pull":
                self._result(docker_image_pull(body))
                return
            if path == "/ops/backup/run":
                self._result(backup_run())
                return
            if match := re.fullmatch(r"/containers/(.+)/(start|stop|restart|kill)", path):
                self._result(container_action(unquote(match.group(1)), match.group(2)))
                return
            if match := re.fullmatch(r"/containers/(.+)/recreate", path):
                self._result(container_recreate(unquote(match.group(1)), bool(body.get("pull"))))
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
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    server.daemon_threads = True
    print(
        f"nc-tower-sidecar listening on {BIND}:{PORT} "
        f"token={'configured' if TOKEN else 'missing-health-only'}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
