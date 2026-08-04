"""NC Tower host inventory & observability collectors (read-only).

Pure helpers take injected `run` / `nsenter_bin` callables so unit tests can
exercise parsers without host privileges.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

# Kernel taint flag bits (linux Documentation/admin-guide/tainted-kernels.rst)
TAINT_FLAGS: list[tuple[int, str, bool]] = [
    (0, "proprietary_module", False),
    (1, "force_loaded", False),
    (2, "smp_unsafe", False),
    (3, "force_unloaded", False),
    (4, "mce", True),  # hardware
    (5, "bad_page", True),
    (6, "user_requested", False),
    (7, "died_recently", False),
    (8, "acpi_override", False),
    (9, "warning", False),
    (10, "staging_driver", False),
    (11, "firmware_workaround", False),
    (12, "out_of_tree", False),
    (13, "unsigned_module", False),
    (14, "soft_lockup", True),
    (15, "live_patched", False),
    (16, "aux", False),
    (17, "struct_randomization_off", False),
]

KERNEL_PATTERNS = [
    (re.compile(r"Machine check|mce:|Hardware Error|EDAC", re.I), "mce"),
    (re.compile(r"Out of memory|oom-killer|Killed process", re.I), "oom"),
    (re.compile(r"resetting link|I/O error|Buffer I/O error|ata\d+:.*HARDRESET|nvme.*reset", re.I), "disk_reset"),
]

_HARDWARE_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_HARDWARE_TTL = 3600.0
_SMART_TREND_LOCK = threading.Lock()


def _host_cmd(
    run: Callable[..., dict[str, Any]],
    nsenter_bin: Callable[[], str | None],
    argv: list[str],
    timeout: int = 15,
) -> dict[str, Any]:
    nsenter = nsenter_bin()
    if nsenter:
        return run([nsenter, "--mount=/proc/1/ns/mnt", "--", *argv], timeout=timeout)
    return run(argv, timeout=timeout)


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _dmi_field(name: str) -> str | None:
    value = _read_text(Path("/sys/class/dmi/id") / name)
    if not value or value.lower() in {"none", "not specified", "default string", "to be filled by o.e.m."}:
        return None
    return value


def decode_taint(value: int) -> dict[str, Any]:
    flags = []
    hardware = False
    for bit, name, is_hw in TAINT_FLAGS:
        if value & (1 << bit):
            flags.append(name)
            if is_hw:
                hardware = True
    return {"value": value, "flags": flags, "hardware_tainted": hardware}


def parse_dmidecode_memory(text: str) -> list[dict[str, Any]]:
    dimms: list[dict[str, Any]] = []
    blocks = re.split(r"\nMemory Device\n", text)
    for block in blocks[1:]:
        def field(key: str) -> str | None:
            m = re.search(rf"^\s*{re.escape(key)}:\s*(.+)$", block, re.M)
            return m.group(1).strip() if m else None

        size = field("Size")
        if not size or size.lower() in {"no module installed", "unknown"}:
            continue
        dimms.append(
            {
                "locator": field("Locator"),
                "bank": field("Bank Locator"),
                "size": size,
                "type": field("Type"),
                "speed": field("Speed"),
                "configured_speed": field("Configured Memory Speed") or field("Configured Clock Speed"),
                "manufacturer": field("Manufacturer"),
                "part_number": field("Part Number"),
                "serial": field("Serial Number"),
                "form_factor": field("Form Factor"),
                "ecc": "Error Correction Type" in block and "None" not in (field("Error Correction Type") or "None"),
            }
        )
    return dimms


def parse_lspci_mm(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        # -mm: "Class" "Vendor" "Device" …
        parts = re.findall(r'"(?:\\.|[^"\\])*"|\S+', line)
        if len(parts) < 4:
            continue
        cleaned = [p.strip('"').replace('\\"', '"') for p in parts]
        rows.append(
            {
                "slot": cleaned[0],
                "class": cleaned[1] if len(cleaned) > 1 else None,
                "vendor": cleaned[2] if len(cleaned) > 2 else None,
                "device": cleaned[3] if len(cleaned) > 3 else None,
            }
        )
    return rows


def parse_lsusb(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        m = re.match(
            r"Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-fA-F:]+)\s+(.*)$",
            line.strip(),
        )
        if not m:
            continue
        rows.append(
            {
                "bus": m.group(1),
                "device": m.group(2),
                "id": m.group(3),
                "name": m.group(4).strip(),
            }
        )
    return rows


def parse_mdstat(text: str) -> dict[str, Any]:
    arrays = []
    degraded = False
    for line in text.splitlines():
        m = re.match(r"^(md\d+)\s*:\s*(\S+)\s+(\S+)\s+(.*)$", line.strip())
        if not m:
            continue
        devices = re.findall(r"(\w+)\[\d+\](?:\((\w)\))?", m.group(4))
        members = [{"name": n, "flag": f or None} for n, f in devices]
        if any(mem.get("flag") in {"F", "S"} for mem in members):
            degraded = True
        if "[_" in m.group(4) or re.search(r"\[\d+/\d+\]", text[text.find(line) : text.find(line) + 200] if False else ""):
            pass
        arrays.append(
            {
                "name": m.group(1),
                "state": m.group(2),
                "level": m.group(3),
                "members": members,
            }
        )
    # Detect [U_] degraded patterns in following lines
    if re.search(r"\[[U_]+\]", text) and "_" in text:
        degraded = True
    return {"arrays": arrays, "degraded": degraded, "raw_present": bool(text.strip())}


def parse_ss_tlnp(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        if line.startswith("State") or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        process = None
        users = re.search(r'users:\(\("([^"]+)"', line)
        if users:
            process = users.group(1)
        rows.append(
            {
                "state": parts[0],
                "recv_q": parts[1],
                "send_q": parts[2],
                "local": local,
                "process": process,
            }
        )
    return rows


def parse_ethtool(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, pattern in (
        ("speed", r"Speed:\s*(.+)"),
        ("duplex", r"Duplex:\s*(.+)"),
        ("link_detected", r"Link detected:\s*(.+)"),
        ("port", r"Port:\s*(.+)"),
    ):
        m = re.search(pattern, text)
        if m:
            out[key] = m.group(1).strip()
    return out


def parse_ethtool_i(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, pattern in (
        ("driver", r"driver:\s*(.+)"),
        ("version", r"version:\s*(.+)"),
        ("firmware", r"firmware-version:\s*(.+)"),
        ("bus_info", r"bus-info:\s*(.+)"),
    ):
        m = re.search(pattern, text)
        if m:
            out[key] = m.group(1).strip()
    return out


def parse_resolv_conf(text: str) -> dict[str, Any]:
    nameservers = re.findall(r"^\s*nameserver\s+(\S+)", text, re.M)
    searches = re.findall(r"^\s*search\s+(.+)$", text, re.M)
    return {
        "nameservers": nameservers,
        "search": searches[0].split() if searches else [],
    }


def tag_kernel_line(message: str) -> list[str]:
    tags = []
    for pattern, tag in KERNEL_PATTERNS:
        if pattern.search(message or ""):
            tags.append(tag)
    return tags


def collect_hardware(
    *,
    run: Callable[..., dict[str, Any]],
    nsenter_bin: Callable[[], str | None],
    host_proc: Path,
    os_release_path: Path = Path("/host/etc/os-release"),
    force: bool = False,
) -> dict[str, Any]:
    now = time.time()
    if (
        not force
        and _HARDWARE_CACHE["payload"] is not None
        and now - float(_HARDWARE_CACHE["ts"]) < _HARDWARE_TTL
    ):
        cached = dict(_HARDWARE_CACHE["payload"])
        cached["cached"] = True
        return cached

    def host(argv: list[str], timeout: int = 15) -> dict[str, Any]:
        return _host_cmd(run, nsenter_bin, argv, timeout=timeout)

    dmi = {
        "board_vendor": _dmi_field("board_vendor"),
        "board_name": _dmi_field("board_name"),
        "board_version": _dmi_field("board_version"),
        "bios_vendor": _dmi_field("bios_vendor"),
        "bios_version": _dmi_field("bios_version"),
        "bios_date": _dmi_field("bios_date"),
        "product_name": _dmi_field("product_name"),
        "product_serial": _dmi_field("product_serial"),
        "product_version": _dmi_field("product_version"),
        "sys_vendor": _dmi_field("sys_vendor"),
        "chassis_type": _dmi_field("chassis_type"),
    }

    # CPU
    cpuinfo = _read_text(host_proc / "cpuinfo")
    model = None
    for line in cpuinfo.splitlines():
        if line.lower().startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    lscpu = host(["lscpu", "-J"], timeout=10)
    lscpu_fields: dict[str, Any] = {}
    if lscpu.get("exit") == 0:
        try:
            for entry in (json.loads(lscpu.get("stdout") or "{}").get("lscpu") or []):
                if isinstance(entry, dict) and entry.get("field"):
                    lscpu_fields[entry["field"].rstrip(":")] = entry.get("data")
        except json.JSONDecodeError:
            pass
    governors = set()
    mhz_values: list[float] = []
    cpufreq = Path("/sys/devices/system/cpu")
    if cpufreq.is_dir():
        for cpu_dir in sorted(cpufreq.glob("cpu[0-9]*")):
            gov = _read_text(cpu_dir / "cpufreq/scaling_governor")
            if gov:
                governors.add(gov)
            cur = _read_text(cpu_dir / "cpufreq/scaling_cur_freq")
            if cur.isdigit():
                mhz_values.append(int(cur) / 1000.0)
    cpu = {
        "model": model or lscpu_fields.get("Model name"),
        "sockets": lscpu_fields.get("Socket(s)"),
        "cores_per_socket": lscpu_fields.get("Core(s) per socket"),
        "threads_per_core": lscpu_fields.get("Thread(s) per core"),
        "cpus": lscpu_fields.get("CPU(s)"),
        "arch": lscpu_fields.get("Architecture"),
        "mhz_min": lscpu_fields.get("CPU min MHz"),
        "mhz_max": lscpu_fields.get("CPU max MHz"),
        "governor": sorted(governors)[0] if len(governors) == 1 else (sorted(governors) if governors else None),
        "mhz_current_avg": round(sum(mhz_values) / len(mhz_values), 1) if mhz_values else None,
    }

    # OS / kernel
    uname = host(["uname", "-a"], timeout=5)
    hostname = host(["hostname"], timeout=5)
    uptime_s = None
    try:
        uptime_s = float(_read_text(host_proc / "uptime").split()[0])
    except (OSError, IndexError, ValueError):
        pass
    last_boot = None
    if uptime_s is not None:
        last_boot = datetime.fromtimestamp(time.time() - uptime_s, tz=timezone.utc).isoformat()

    os_release: dict[str, str] = {}
    for line in _read_text(os_release_path).splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os_release[key] = val.strip().strip('"')

    taint_raw = _read_text(host_proc / "sys/kernel/tainted", "0")
    try:
        taint = decode_taint(int(taint_raw))
    except ValueError:
        taint = {"value": None, "flags": [], "hardware_tainted": False, "unavailable": True}

    # DIMMs
    dimms: dict[str, Any] = {"unavailable": False, "items": []}
    dm = host(["dmidecode", "-t", "memory"], timeout=20)
    if dm.get("exit") != 0:
        dm = host(["/usr/sbin/dmidecode", "-t", "memory"], timeout=20)
    if dm.get("exit") == 0:
        dimms["items"] = parse_dmidecode_memory(dm.get("stdout") or "")
    else:
        dimms = {"unavailable": True, "reason": dm.get("stderr") or "dmidecode_missing", "items": []}

    # PCIe
    pcie: dict[str, Any] = {"unavailable": False, "items": []}
    pci = host(["lspci", "-mm"], timeout=15)
    if pci.get("exit") == 0:
        pcie["items"] = parse_lspci_mm(pci.get("stdout") or "")
    else:
        pcie = {"unavailable": True, "reason": pci.get("stderr") or "lspci_missing", "items": []}

    # USB
    usb: dict[str, Any] = {"unavailable": False, "items": []}
    usb_r = host(["lsusb"], timeout=10)
    if usb_r.get("exit") == 0:
        usb["items"] = parse_lsusb(usb_r.get("stdout") or "")
    else:
        usb = {"unavailable": True, "reason": usb_r.get("stderr") or "lsusb_missing", "items": []}

    payload = {
        "ok": True,
        "dmi": dmi,
        "cpu": cpu,
        "os": {
            "hostname": (hostname.get("stdout") or "").strip() or None,
            "uname": (uname.get("stdout") or "").strip() or None,
            "arch": os.uname().machine if hasattr(os, "uname") else None,
            "pretty_name": os_release.get("PRETTY_NAME"),
            "id": os_release.get("ID"),
            "version_id": os_release.get("VERSION_ID"),
            "os_release": os_release,
            "uptime_s": uptime_s,
            "last_boot": last_boot,
            "taint": taint,
        },
        "dimms": dimms,
        "pcie": pcie,
        "usb": usb,
        "cached": False,
        "ts": now,
    }
    _HARDWARE_CACHE["ts"] = now
    _HARDWARE_CACHE["payload"] = payload
    return payload


def collect_storage(
    *,
    run: Callable[..., dict[str, Any]],
    nsenter_bin: Callable[[], str | None],
    smartctl: str | None = None,
) -> dict[str, Any]:
    def host(argv: list[str], timeout: int = 20) -> dict[str, Any]:
        return _host_cmd(run, nsenter_bin, argv, timeout=timeout)

    tree: dict[str, Any] = {"unavailable": False, "blockdevices": []}
    lsblk = host(
        [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,TYPE,SIZE,MODEL,SERIAL,UUID,FSTYPE,MOUNTPOINT,TRAN,ROTA,PKNAME",
        ],
        timeout=20,
    )
    if lsblk.get("exit") == 0:
        try:
            tree = json.loads(lsblk.get("stdout") or "{}")
            tree["unavailable"] = False
        except json.JSONDecodeError:
            tree = {"unavailable": True, "reason": "lsblk_json_parse", "blockdevices": []}
    else:
        tree = {"unavailable": True, "reason": lsblk.get("stderr") or "lsblk_missing", "blockdevices": []}

    mdstat_text = _read_text(Path("/proc/mdstat"))
    if not mdstat_text:
        # try hostproc
        pass
    raid = parse_mdstat(mdstat_text)

    nvme_temps: list[dict[str, Any]] = []
    ctl = smartctl
    if ctl:
        # Scan common NVMe nodes from lsblk
        def walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                name = node.get("name") or ""
                if node.get("type") == "disk" and (
                    str(node.get("tran") or "").lower() == "nvme" or name.startswith("nvme")
                ):
                    dev = f"/dev/{name}"
                    result = run([ctl, "-A", "-j", dev], timeout=25, max_output=200_000)
                    if result.get("exit") in (0, 4):  # 4 = some SMART warnings
                        try:
                            payload = json.loads(result.get("stdout") or "{}")
                        except json.JSONDecodeError:
                            payload = {}
                        temp = None
                        temp_block = payload.get("temperature")
                        if isinstance(temp_block, dict):
                            temp = temp_block.get("current")
                        nvme = payload.get("nvme_smart_health_information_log") or {}
                        if temp is None and isinstance(nvme, dict):
                            temp = nvme.get("temperature")
                        nvme_temps.append(
                            {
                                "device": dev,
                                "serial": node.get("serial") or payload.get("serial_number"),
                                "model": node.get("model") or payload.get("model_name"),
                                "temp_c": temp,
                            }
                        )
                walk(node.get("children") or [])

        walk(tree.get("blockdevices") or [])

    return {
        "ok": True,
        "lsblk": tree,
        "raid": raid,
        "nvme_temps": nvme_temps,
        "ts": time.time(),
    }


def collect_temperatures(
    *,
    chassis_status: dict[str, Any] | None,
    gpu_payload: dict[str, Any] | None,
    smart_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    sensors: list[dict[str, Any]] = []
    for t in (chassis_status or {}).get("temps") or []:
        if not isinstance(t, dict):
            continue
        sensors.append(
            {
                "source": "hwmon",
                "label": t.get("label") or t.get("name"),
                "chip": t.get("chip"),
                "celsius": t.get("celsius") if t.get("celsius") is not None else t.get("temp_c"),
            }
        )
    for g in (gpu_payload or {}).get("gpus") or (gpu_payload or {}).get("items") or []:
        if isinstance(g, dict) and g.get("temp_c") is not None:
            sensors.append(
                {
                    "source": "gpu",
                    "label": g.get("name") or f"GPU {g.get('index')}",
                    "chip": g.get("uuid"),
                    "celsius": g.get("temp_c"),
                }
            )
    for d in (smart_payload or {}).get("disks") or (smart_payload or {}).get("items") or []:
        if isinstance(d, dict) and d.get("temp_c") is not None:
            sensors.append(
                {
                    "source": "disk",
                    "label": d.get("model") or d.get("device") or d.get("name"),
                    "chip": d.get("device") or d.get("name"),
                    "celsius": d.get("temp_c"),
                    "serial": d.get("serial") or d.get("serial_number"),
                }
            )
    return {"ok": True, "sensors": sensors, "count": len(sensors), "ts": time.time()}


def collect_posture(
    *,
    run: Callable[..., dict[str, Any]],
    nsenter_bin: Callable[[], str | None],
    service_targets: list[str],
) -> dict[str, Any]:
    def host(argv: list[str], timeout: int = 15) -> dict[str, Any]:
        return _host_cmd(run, nsenter_bin, argv, timeout=timeout)

    who_r = host(["who"], timeout=5)
    users = []
    if who_r.get("exit") == 0:
        for line in (who_r.get("stdout") or "").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                users.append(
                    {
                        "user": parts[0],
                        "tty": parts[1],
                        "since": " ".join(parts[2:4]) if len(parts) >= 4 else None,
                        "host": parts[4] if len(parts) >= 5 else None,
                    }
                )
    else:
        users = []

    last_r = host(["last", "-n", "10", "-w"], timeout=8)
    recent = []
    if last_r.get("exit") == 0:
        for line in (last_r.get("stdout") or "").splitlines():
            if not line.strip() or line.startswith("wtmp") or line.startswith("btmp"):
                continue
            recent.append({"line": line.strip()})

    ntp: dict[str, Any] = {"unavailable": False}
    td = host(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "Timezone", "--value"], timeout=8)
    if td.get("exit") == 0:
        lines = [ln.strip() for ln in (td.get("stdout") or "").splitlines() if ln.strip()]
        # show --value prints values in property order
        props = host(["timedatectl", "show"], timeout=8)
        synced = None
        timezone = None
        if props.get("exit") == 0:
            for line in (props.get("stdout") or "").splitlines():
                if line.startswith("NTPSynchronized="):
                    synced = line.split("=", 1)[1].strip().lower() == "yes"
                if line.startswith("Timezone="):
                    timezone = line.split("=", 1)[1].strip()
        ntp = {"unavailable": False, "synchronized": synced, "timezone": timezone}
    else:
        ntp = {"unavailable": True, "reason": td.get("stderr") or "timedatectl_missing"}

    failed_ssh = 0
    journal = host(
        ["journalctl", "-u", "ssh", "-u", "sshd", "--since", "24 hours ago", "-p", "err", "--no-pager", "-o", "cat"],
        timeout=20,
    )
    if journal.get("exit") == 0:
        text = journal.get("stdout") or ""
        failed_ssh = len(re.findall(r"Failed password|Invalid user|authentication failure", text, re.I))

    certs = []
    for entry in service_targets:
        if "=" not in entry:
            continue
        name, url = entry.split("=", 1)
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            continue
        host_name = parsed.hostname
        port = parsed.port or 443
        try:
            import socket as _socket

            ctx = ssl.create_default_context()
            with ctx.wrap_socket(
                _socket.create_connection((host_name, port), timeout=5),
                server_hostname=host_name,
            ) as sock:
                cert = sock.getpeercert()
            not_after = cert.get("notAfter")
            expires_at = None
            days_left = None
            if not_after:
                expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                expires_at = expires.isoformat()
                days_left = int((expires - datetime.now(timezone.utc)).total_seconds() // 86400)
            certs.append(
                {
                    "name": name.strip(),
                    "host": host_name,
                    "port": port,
                    "expires_at": expires_at,
                    "days_left": days_left,
                    "ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            certs.append(
                {
                    "name": name.strip(),
                    "host": host_name,
                    "port": port,
                    "ok": False,
                    "error": str(exc),
                }
            )

    return {
        "ok": True,
        "users": users,
        "recent_logins": recent[:10],
        "ntp": ntp,
        "failed_ssh_24h": failed_ssh,
        "certs": certs,
        "ts": time.time(),
    }


def collect_kernel_log(
    *,
    run: Callable[..., dict[str, Any]],
    nsenter_bin: Callable[[], str | None],
    minutes: int = 60,
) -> dict[str, Any]:
    minutes = max(1, min(int(minutes), 24 * 60))
    result = _host_cmd(
        run,
        nsenter_bin,
        [
            "journalctl",
            "-k",
            "-p",
            "warning",
            "--since",
            f"{minutes} minutes ago",
            "-o",
            "json",
            "--no-pager",
            "-n",
            "200",
        ],
        timeout=25,
    )
    rows = []
    tags_seen: set[str] = set()
    if result.get("exit") == 0:
        for line in (result.get("stdout") or "").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = entry.get("MESSAGE") or ""
            tags = tag_kernel_line(msg)
            tags_seen.update(tags)
            rows.append(
                {
                    "ts": entry.get("__REALTIME_TIMESTAMP"),
                    "priority": entry.get("PRIORITY"),
                    "message": msg,
                    "tags": tags,
                }
            )
    else:
        return {
            "ok": False,
            "unavailable": True,
            "reason": result.get("stderr") or "journalctl_missing",
            "rows": [],
            "tags_seen": [],
        }
    return {
        "ok": True,
        "minutes": minutes,
        "rows": rows[-200:],
        "tags_seen": sorted(tags_seen),
        "ts": time.time(),
    }


def extend_network_depth(
    payload: dict[str, Any],
    *,
    run: Callable[..., dict[str, Any]],
    nsenter_bin: Callable[[], str | None],
) -> dict[str, Any]:
    def host(argv: list[str], timeout: int = 10) -> dict[str, Any]:
        return _host_cmd(run, nsenter_bin, argv, timeout=timeout)

    routes: dict[str, Any] = {"unavailable": False, "items": []}
    rt = host(["ip", "-j", "route"], timeout=8)
    if rt.get("exit") != 0:
        rt = host(["/sbin/ip", "-j", "route"], timeout=8)
    if rt.get("exit") == 0:
        try:
            routes["items"] = json.loads(rt.get("stdout") or "[]")
        except json.JSONDecodeError:
            routes = {"unavailable": True, "reason": "route_json_parse", "items": []}
    else:
        routes = {"unavailable": True, "reason": "ip_route_missing", "items": []}

    dns: dict[str, Any] = {"unavailable": False}
    resolvectl = host(["resolvectl", "status"], timeout=8)
    if resolvectl.get("exit") == 0:
        text = resolvectl.get("stdout") or ""
        dns["resolvectl"] = True
        dns["nameservers"] = re.findall(r"DNS Servers:\s*(.+)", text)
        dns["domains"] = re.findall(r"DNS Domain:\s*(.+)", text)
    else:
        # Fall back to resolv.conf via host cat
        rc = host(["cat", "/etc/resolv.conf"], timeout=5)
        if rc.get("exit") == 0:
            dns.update(parse_resolv_conf(rc.get("stdout") or ""))
            dns["resolvectl"] = False
        else:
            dns = {"unavailable": True, "reason": "resolv_missing"}

    listeners: dict[str, Any] = {"unavailable": False, "items": []}
    ss = host(["ss", "-tlnp"], timeout=10)
    if ss.get("exit") == 0:
        listeners["items"] = parse_ss_tlnp(ss.get("stdout") or "")
    else:
        listeners = {"unavailable": True, "reason": ss.get("stderr") or "ss_missing", "items": []}

    nic_detail: list[dict[str, Any]] = []
    for iface in (payload.get("interfaces") or {}).get("items") or []:
        name = iface.get("ifname")
        if not name or name == "lo":
            continue
        detail: dict[str, Any] = {"ifname": name}
        eth = host(["ethtool", name], timeout=5)
        if eth.get("exit") == 0:
            detail.update(parse_ethtool(eth.get("stdout") or ""))
        ethi = host(["ethtool", "-i", name], timeout=5)
        if ethi.get("exit") == 0:
            detail.update(parse_ethtool_i(ethi.get("stdout") or ""))
        if len(detail) > 1:
            nic_detail.append(detail)

    payload["routes"] = routes
    payload["dns"] = dns
    payload["listeners"] = listeners
    payload["nic_detail"] = nic_detail
    payload["network_depth"] = True
    return payload


def smart_history_read(path: Path, hours: int = 24) -> dict[str, Any]:
    hours = max(1, min(int(hours), 168))
    cutoff = time.time() - hours * 3600
    if not path.is_file():
        return {"ok": True, "samples": [], "hours": hours}
    samples = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if float(row.get("ts") or 0) >= cutoff:
                samples.append(row)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "samples": []}
    return {"ok": True, "samples": samples, "hours": hours, "ts": time.time()}


def smart_history_summarize(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse samples into per-disk min/now/max temp + latest realloc/pending."""
    by_serial: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        for disk in sample.get("disks") or []:
            if not isinstance(disk, dict):
                continue
            key = str(disk.get("serial") or disk.get("device") or disk.get("name") or "")
            if not key:
                continue
            by_serial.setdefault(key, []).append({**disk, "ts": sample.get("ts")})
    rows = []
    for serial, points in by_serial.items():
        temps = [p.get("temp_c") for p in points if p.get("temp_c") is not None]
        latest = points[-1]
        rows.append(
            {
                "serial": serial,
                "device": latest.get("device") or latest.get("name"),
                "model": latest.get("model"),
                "temp_min": min(temps) if temps else None,
                "temp_now": latest.get("temp_c"),
                "temp_max": max(temps) if temps else None,
                "reallocated": latest.get("reallocated"),
                "pending": latest.get("pending"),
                "power_on_hours": latest.get("power_on_hours"),
                "samples": len(points),
            }
        )
    return rows


class SmartTrendSampler:
    """Background 10-minute SMART trend writer."""

    def __init__(
        self,
        path: Path,
        collect_fn: Callable[[], list[dict[str, Any]]],
        interval_s: int = 600,
        max_lines: int = 2000,
    ) -> None:
        self.path = path
        self.collect_fn = collect_fn
        self.interval_s = interval_s
        self.max_lines = max_lines
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="smart-trend", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                disks = self.collect_fn()
                row = {"ts": time.time(), "disks": disks}
                with _SMART_TREND_LOCK:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(row, separators=(",", ":")) + "\n")
                    self._trim()
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(self.interval_s)

    def _trim(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > self.max_lines:
                self.path.write_text("\n".join(lines[-self.max_lines:]) + "\n", encoding="utf-8")
        except OSError:
            pass


_TEMP_HISTORY_LOCK = threading.Lock()


class TempHistorySampler:
    """Background package-temp ring for Host › Temperatures chart."""

    def __init__(
        self,
        path: Path,
        collect_fn: Callable[[], dict[str, Any]],
        interval_s: int = 60,
        max_lines: int = 1500,
    ) -> None:
        self.path = path
        self.collect_fn = collect_fn
        self.interval_s = interval_s
        self.max_lines = max_lines
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="temp-history", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self.collect_fn()
                row = {"ts": time.time(), **sample}
                with _TEMP_HISTORY_LOCK:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(row, separators=(",", ":")) + "\n")
                    self._trim()
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(self.interval_s)

    def _trim(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > self.max_lines:
                self.path.write_text("\n".join(lines[-self.max_lines:]) + "\n", encoding="utf-8")
        except OSError:
            pass


def temp_history_read(path: Path, hours: int = 24) -> dict[str, Any]:
    hours = max(1, min(int(hours), 168))
    cutoff = time.time() - hours * 3600
    if not path.is_file():
        return {"ok": True, "samples": [], "hours": hours}
    samples = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if float(row.get("ts") or 0) >= cutoff:
                samples.append(row)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "samples": []}
    return {"ok": True, "samples": samples, "hours": hours, "ts": time.time()}
