#!/usr/bin/env python3
"""Control Tower sidecar — host/Docker/ops RO + allowlisted mutators.

Never exposed without X-Ops-Token when NC_TOWER_SIDECAR_TOKEN is set.
docker.sock is used only here (not from Nextcloud PHP).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

docker = None  # unused; Docker via CLI only

TOKEN = os.environ.get("NC_TOWER_SIDECAR_TOKEN", "")
OPS_ROOT = Path(os.environ.get("NC_TOWER_OPS_ROOT", "/ops"))
FAN_HELPER = os.environ.get(
    "NC_TOWER_FAN_HELPER",
    "/usr/local/bin/gpu-fan-helper.py",
)
NVIDIA_SMI = os.environ.get("NC_TOWER_NVIDIA_SMI", "/usr/bin/nvidia-smi")
SMARTCTL = os.environ.get("NC_TOWER_SMARTCTL", "/usr/sbin/smartctl")

COMPOSE_DIRS = [
    p.strip()
    for p in os.environ.get(
        "NC_TOWER_COMPOSE_DIRS",
        ",".join(
            [
                "/media/4TB/nc-gcs",
                "/media/4TB/cloud",
                "/media/4TB/webodm",
                "/media/4TB/caddy-proxy-manager",
                "/media/4TB/wireguard",
                "/media/4TB/guac",
                "/media/4TB/octoslicer",
                "/media/4TB/sim/sim2",
            ]
        ),
    ).split(",")
    if p.strip()
]

CONTAINER_ALLOW = [
    p.strip()
    for p in os.environ.get(
        "NC_TOWER_CONTAINER_ALLOW",
        "gcs_*,mavlink_gateway",
    ).split(",")
    if p.strip()
]

CONTAINER_DENY = [
    p.strip()
    for p in os.environ.get(
        "NC_TOWER_CONTAINER_DENY",
        "nc_tower_sidecar,cloud_*,portainer,wg-easy,talk_*,*openclaw*",
    ).split(",")
    if p.strip()
]

BIND = os.environ.get("NC_TOWER_BIND", "0.0.0.0")
PORT = int(os.environ.get("NC_TOWER_PORT", "18765"))
DISK_PATHS = [
    p.strip()
    for p in os.environ.get("NC_TOWER_DISK_PATHS", "/,/media/4TB").split(",")
    if p.strip()
]


def audit(msg: str) -> None:
    print(f"[audit] {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}", flush=True)


def _read_proc(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _statvfs_disk(path: str) -> dict:
    try:
        st = os.statvfs(path)
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        used = total - free
        return {
            "path": path,
            "total_b": total,
            "free_b": free,
            "used_b": used,
            "used_pct": round((used / total) * 100, 1) if total else 0,
        }
    except OSError as exc:
        return {"path": path, "error": str(exc)}


def host_summary() -> dict:
    loadavg = _read_proc("/proc/loadavg").split()[:3]
    mem: dict[str, str] = {}
    for line in _read_proc("/proc/meminfo").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            mem[k.strip()] = v.strip()
    return {
        "loadavg": loadavg,
        "mem_total": mem.get("MemTotal"),
        "mem_available": mem.get("MemAvailable"),
        "uptime_s": float(_read_proc("/proc/uptime").split()[0] or 0),
        "disks": [_statvfs_disk(p) for p in DISK_PATHS],
        "ts": time.time(),
    }


def host_gpu() -> dict:
    if not Path(NVIDIA_SMI).is_file() and not _which("nvidia-smi"):
        return {"unavailable": True, "reason": "nvidia-smi_missing", "gpus": []}
    smi = NVIDIA_SMI if Path(NVIDIA_SMI).is_file() else "nvidia-smi"
    try:
        out = subprocess.check_output(
            [
                smi,
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,fan.speed",
                "--format=csv,noheader,nounits",
            ],
            timeout=8,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        return {"unavailable": True, "reason": str(exc), "gpus": []}
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        gpus.append(
            {
                "name": parts[0],
                "util_pct": _to_num(parts[1]),
                "mem_used_mib": _to_num(parts[2]),
                "mem_total_mib": _to_num(parts[3]),
                "temp_c": _to_num(parts[4]),
                "fan_pct": _to_num(parts[5]),
            }
        )
    return {"unavailable": False, "gpus": gpus, "ts": time.time()}


def _to_num(s: str):
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _which(name: str) -> str | None:
    for d in os.environ.get("PATH", "").split(":"):
        p = Path(d) / name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def host_smart() -> dict:
    ctl = SMARTCTL if Path(SMARTCTL).is_file() else (_which("smartctl") or "")
    if not ctl:
        return {"unavailable": True, "reason": "smartctl_missing", "disks": []}
    disks = []
    try:
        scan = subprocess.check_output(
            [ctl, "--scan"],
            timeout=10,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        return {"unavailable": True, "reason": str(exc), "disks": []}
    for line in scan.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # e.g. /dev/sda -d sat # ...
        parts = line.split()
        if not parts:
            continue
        dev = parts[0]
        health = "UNKNOWN"
        try:
            h = subprocess.check_output(
                [ctl, "-H", dev],
                timeout=15,
                text=True,
                stderr=subprocess.STDOUT,
            )
            if re.search(r"PASSED", h, re.I):
                health = "PASS"
            elif re.search(r"FAILED", h, re.I):
                health = "FAIL"
        except subprocess.CalledProcessError as exc:
            text = exc.output or ""
            if re.search(r"PASSED", text, re.I):
                health = "PASS"
            elif re.search(r"FAILED", text, re.I):
                health = "FAIL"
            else:
                health = "UNKNOWN"
        except subprocess.SubprocessError:
            health = "UNKNOWN"
        disks.append({"device": dev, "health": health})
    return {"unavailable": False, "disks": disks, "ts": time.time()}


def _fan_helper() -> str | None:
    if Path(FAN_HELPER).is_file():
        return FAN_HELPER
    return _which("gpu-fan-helper.py")


def host_fan_get() -> dict:
    helper = _fan_helper()
    if not helper:
        return {"unavailable": True, "reason": "fan_helper_missing"}
    try:
        out = subprocess.check_output(
            ["python3", helper, "status"],
            timeout=10,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out)
        data["unavailable"] = False
        data["ts"] = time.time()
        return data
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError) as exc:
        return {"unavailable": True, "reason": str(exc)}


def host_fan_set(body: dict) -> dict:
    helper = _fan_helper()
    if not helper:
        return {"ok": False, "error": "fan_helper_missing"}
    op = (body.get("op") or "").strip()
    if op == "set-auto":
        argv = ["python3", helper, "set-auto"]
    elif op == "set-all-speeds":
        speed = int(body.get("speed", -1))
        if speed < 20 or speed > 100:
            return {"ok": False, "error": "speed_must_be_20_to_100"}
        argv = ["python3", helper, "set-all-speeds", str(speed)]
    elif op == "set-speed":
        fan = int(body.get("fan", -1))
        speed = int(body.get("speed", -1))
        if fan < 0:
            return {"ok": False, "error": "fan_index_required"}
        if speed < 20 or speed > 100:
            return {"ok": False, "error": "speed_must_be_20_to_100"}
        argv = ["python3", helper, "set-speed", str(fan), str(speed)]
    else:
        return {"ok": False, "error": "invalid_op"}
    try:
        out = subprocess.check_output(argv, timeout=15, text=True, stderr=subprocess.STDOUT)
        audit(f"fan op={op} argv={argv[2:]} ok")
        try:
            payload = json.loads(out) if out.strip().startswith("{") else {"raw": out.strip()}
        except json.JSONDecodeError:
            payload = {"raw": out.strip()}
        return {"ok": True, "result": payload}
    except subprocess.CalledProcessError as exc:
        audit(f"fan op={op} FAIL {exc.returncode}")
        return {"ok": False, "error": "helper_failed", "detail": (exc.output or "")[:500]}
    except subprocess.SubprocessError as exc:
        return {"ok": False, "error": str(exc)}


def _name_denied(name: str) -> bool:
    for pat in CONTAINER_DENY:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


def _name_allowed(name: str) -> bool:
    if _name_denied(name):
        return False
    for pat in CONTAINER_ALLOW:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


def _docker_bin() -> str:
    env = os.environ.get("NC_TOWER_DOCKER", "/usr/bin/docker")
    if Path(env).is_file():
        return env
    return _which("docker") or "docker"


def _docker_json(args: list[str], timeout: int = 30) -> list | dict:
    out = subprocess.check_output(
        [_docker_bin(), *args],
        timeout=timeout,
        text=True,
        stderr=subprocess.DEVNULL,
    )
    out = out.strip()
    if not out:
        return []
    # docker -f json may emit NDJSON
    if "\n" in out and not out.startswith("["):
        rows = []
        for line in out.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    return json.loads(out)


def containers() -> dict:
    rows = []
    counts = {"running": 0, "exited": 0, "paused": 0, "total": 0, "other": 0}
    stats_map: dict[str, dict] = {}
    try:
        raw = subprocess.check_output(
            [
                _docker_bin(),
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}",
            ],
            timeout=25,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                stats_map[parts[0]] = {"cpu": parts[1], "mem": parts[2]}
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    try:
        items = _docker_json(
            [
                "ps",
                "-a",
                "--format",
                "{{json .}}",
            ],
            timeout=30,
        )
        if isinstance(items, dict):
            items = [items]
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError) as exc:
        return {"error": str(exc), "containers": [], "counts": counts}

    for c in items:
        name = c.get("Names") or c.get("Name") or ""
        # Names may be "/foo" or "foo"
        name = name.lstrip("/").split(",")[0]
        status_raw = (c.get("State") or c.get("Status") or "").lower()
        if "running" in status_raw or status_raw == "running":
            status = "running"
            counts["running"] += 1
        elif "exited" in status_raw or status_raw == "exited":
            status = "exited"
            counts["exited"] += 1
        elif "paused" in status_raw:
            status = "paused"
            counts["paused"] += 1
        else:
            status = status_raw or "unknown"
            counts["other"] += 1
        counts["total"] += 1
        labels = c.get("Labels") or ""
        project = ""
        service = ""
        if isinstance(labels, str):
            for part in labels.split(","):
                if part.startswith("com.docker.compose.project="):
                    project = part.split("=", 1)[1]
                elif part.startswith("com.docker.compose.service="):
                    service = part.split("=", 1)[1]
        elif isinstance(labels, dict):
            project = labels.get("com.docker.compose.project", "")
            service = labels.get("com.docker.compose.service", "")
        ports = []
        pr = c.get("Ports") or ""
        if isinstance(pr, str) and pr:
            ports = [pr]
        st = stats_map.get(name, {})
        rows.append(
            {
                "name": name,
                "id": (c.get("ID") or c.get("Id") or "")[:12],
                "status": status,
                "image": c.get("Image") or "",
                "project": project,
                "service": service,
                "ports": ports,
                "started_at": c.get("RunningFor") or c.get("CreatedAt") or "",
                "cpu": st.get("cpu", ""),
                "mem": st.get("mem", ""),
                "mutable": _name_allowed(name),
            }
        )
    return {"containers": rows, "counts": counts, "ts": time.time()}


def container_logs(name: str, tail: int = 100) -> dict:
    if not _name_allowed(name):
        return {"ok": False, "error": "forbidden", "http": 403}
    try:
        text = subprocess.check_output(
            [
                _docker_bin(),
                "logs",
                "--timestamps",
                "--tail",
                str(max(1, min(tail, 500))),
                name,
            ],
            timeout=30,
            text=True,
            stderr=subprocess.STDOUT,
        )
        return {"ok": True, "name": name, "logs": text[-50000:], "ts": time.time()}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": (exc.output or str(exc))[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def container_action(name: str, action: str) -> dict:
    if action not in ("start", "stop", "restart"):
        return {"ok": False, "error": "invalid_action", "http": 400}
    if not _name_allowed(name):
        audit(f"container {action} {name} FORBIDDEN")
        return {"ok": False, "error": "forbidden", "http": 403}
    try:
        subprocess.check_call(
            [_docker_bin(), action, name],
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        # status
        st = subprocess.check_output(
            [_docker_bin(), "inspect", "-f", "{{.State.Status}}", name],
            timeout=15,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        audit(f"container {action} {name} -> {st}")
        return {"ok": True, "name": name, "action": action, "status": st}
    except Exception as exc:  # noqa: BLE001
        audit(f"container {action} {name} FAIL {exc}")
        return {"ok": False, "error": str(exc)}


def _running_compose_projects() -> set[str]:
    projects: set[str] = set()
    try:
        items = _docker_json(["ps", "--format", "{{json .}}"], timeout=20)
        if isinstance(items, dict):
            items = [items]
        for c in items:
            labels = c.get("Labels") or ""
            if isinstance(labels, str):
                for part in labels.split(","):
                    if part.startswith("com.docker.compose.project="):
                        projects.add(part.split("=", 1)[1])
            elif isinstance(labels, dict):
                p = labels.get("com.docker.compose.project")
                if p:
                    projects.add(p)
    except Exception:  # noqa: BLE001
        pass
    return projects


def _compose_files_under(root: Path) -> list[Path]:
    found: list[Path] = []
    for name in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
        cand = root / name
        if cand.is_file():
            found.append(cand)
    compose_dir = root / "compose"
    if compose_dir.is_dir():
        found.extend(sorted(compose_dir.glob("docker-compose*.yml")))
        found.extend(sorted(compose_dir.glob("docker-compose*.yaml")))
        found.extend(sorted(compose_dir.glob("compose*.yml")))
    # dedupe
    seen = set()
    out = []
    for f in found:
        rp = str(f.resolve())
        if rp not in seen:
            seen.add(rp)
            out.append(f)
    return out

def _yaml_service_names(path: Path, limit: int = 40) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    services: list[str] = []
    in_services = False
    for line in text.splitlines()[:400]:
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


def stacks() -> dict:
    running_projects = _running_compose_projects()

    units = []
    for d in COMPOSE_DIRS:
        root = Path(d)
        if not root.is_dir():
            units.append(
                {
                    "dir": d,
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
                    "dir": d,
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
        for f in files:
            stem = f.stem.replace("docker-compose.", "").replace("compose.", "")
            project_hint = stem if stem not in ("yml", "yaml", "") else root.name
            # common compose project = directory name
            proj_candidates = {root.name, project_hint, f.parent.name}
            running = bool(proj_candidates & running_projects)
            name_l = f.name.lower()
            risky = bool(re.search(r"sim|gazebo|sitl", name_l)) or bool(
                re.search(r"sim|gazebo|sitl", str(f).lower())
            )
            units.append(
                {
                    "dir": d,
                    "exists": True,
                    "file": str(f.resolve()),
                    "project_hint": project_hint,
                    "running_hint": running,
                    "services": _yaml_service_names(f),
                    "preview": _file_preview(f),
                    "risky": risky,
                }
            )
    return {"stacks": units, "ts": time.time()}


def _resolve_compose_file(file_path: str) -> Path | None:
    try:
        target = Path(file_path).resolve()
    except OSError:
        return None
    if not target.is_file():
        return None
    for d in COMPOSE_DIRS:
        try:
            root = Path(d).resolve()
        except OSError:
            continue
        try:
            target.relative_to(root)
            return target
        except ValueError:
            continue
    return None


def stacks_mutate(action: str, body: dict) -> dict:
    if action not in ("up", "down"):
        return {"ok": False, "error": "invalid_action", "http": 400}
    file_path = (body.get("file") or "").strip()
    resolved = _resolve_compose_file(file_path)
    if resolved is None:
        audit(f"stacks {action} forbidden file={file_path}")
        return {"ok": False, "error": "forbidden_or_missing_file", "http": 403}
    cmd = ["docker", "compose", "-f", str(resolved)]
    if action == "up":
        cmd += ["up", "-d"]
    else:
        cmd += ["down"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        audit(f"stacks {action} file={resolved} exit={proc.returncode}")
        return {
            "ok": proc.returncode == 0,
            "action": action,
            "file": str(resolved),
            "exit": proc.returncode,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired:
        audit(f"stacks {action} TIMEOUT file={resolved}")
        return {"ok": False, "error": "timeout"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _parse_alert_file(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return None
        # NDJSON or single JSON
        first = text.splitlines()[0]
        data = json.loads(first)
        if isinstance(data, dict):
            return {
                "monitor": data.get("monitor"),
                "status": data.get("status"),
                "detail": data.get("detail"),
            }
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _backup_summary() -> dict:
    inbox = OPS_ROOT / "inbox"
    files = []
    if inbox.is_dir():
        files = sorted(
            [p for p in inbox.glob("backup-*.json") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if not files:
        return {
            "ok": True,
            "status": "ok",
            "summary": "no backup issue file (success-when-absent)",
            "mtime": None,
            "stale": True,
            "name": None,
        }
    newest = files[0]
    mtime = newest.stat().st_mtime
    age_h = (time.time() - mtime) / 3600.0
    lines = []
    try:
        for line in newest.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as exc:
        return {"ok": False, "status": "error", "summary": str(exc), "mtime": mtime, "name": newest.name}

    rank = {"ok": 0, "info": 0, "warn": 1, "warning": 1, "crit": 2, "critical": 2, "error": 2}
    worst = "ok"
    details = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        st = str(row.get("status") or "ok").lower()
        if rank.get(st, 0) > rank.get(worst, 0):
            worst = st
        det = row.get("detail") or row.get("monitor")
        if det:
            details.append(str(det))
    if worst in ("ok", "info") and not lines:
        worst = "ok"
        summary = "backup check passed (empty issue file)"
    elif not lines:
        summary = "unparseable backup file"
        worst = "warn"
    else:
        summary = "; ".join(details[:5]) if details else f"backup status={worst}"
    ok = worst in ("ok", "info")
    return {
        "ok": ok,
        "status": worst,
        "summary": summary,
        "mtime": mtime,
        "name": newest.name,
        "stale": age_h > 26,
        "age_hours": round(age_h, 1),
    }


def ops_inbox_summary() -> dict:
    inbox = OPS_ROOT / "inbox"
    state = OPS_ROOT / "state"
    recent = []
    if inbox.is_dir():
        files = sorted(inbox.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in files[:40]:
            if not f.is_file():
                continue
            entry = {
                "name": f.name,
                "mtime": f.stat().st_mtime,
                "size": f.stat().st_size,
                "monitor": None,
                "status": None,
                "detail": None,
            }
            if f.suffix == ".json":
                parsed = _parse_alert_file(f)
                if parsed:
                    entry.update(parsed)
            recent.append(entry)

    port_audit = None
    if state.is_dir():
        audits = sorted(state.glob("port-audit-*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if audits:
            port_audit = {"name": audits[0].name, "mtime": audits[0].stat().st_mtime}

    return {
        "ops_root": str(OPS_ROOT),
        "inbox_recent": recent,
        "backup": _backup_summary(),
        "port_audit_latest": port_audit,
        "ts": time.time(),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass

    def _auth_ok(self) -> bool:
        if not TOKEN:
            return True
        return self.headers.get("X-Ops-Token") == TOKEN

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def do_GET(self) -> None:  # noqa: N802
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
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
            elif path == "/containers":
                self._send(200, containers())
            elif path.startswith("/containers/") and path.endswith("/logs"):
                name = path[len("/containers/") : -len("/logs")]
                tail = int((qs.get("tail") or ["100"])[0])
                result = container_logs(name, tail=tail)
                code = int(result.pop("http", 200 if result.get("ok") else 500))
                self._send(code, result)
            elif path == "/stacks":
                self._send(200, stacks())
            elif path == "/ops/inbox-summary":
                self._send(200, ops_inbox_summary())
            else:
                self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        if not TOKEN:
            # refuse mutators when token unset (hardening)
            self._send(403, {"ok": False, "error": "token_required_for_mutators"})
            return
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/host/fan":
                result = host_fan_set(body)
                self._send(200 if result.get("ok") else 400, result)
                return
            m = re.match(r"^/containers/([^/]+)/(start|stop|restart)$", path)
            if m:
                result = container_action(m.group(1), m.group(2))
                code = int(result.pop("http", 200 if result.get("ok") else 500))
                self._send(code, result)
                return
            if path == "/stacks/up":
                result = stacks_mutate("up", body)
                code = int(result.pop("http", 200 if result.get("ok") else 500))
                self._send(code, result)
                return
            if path == "/stacks/down":
                result = stacks_mutate("down", body)
                code = int(result.pop("http", 200 if result.get("ok") else 500))
                self._send(code, result)
                return
            self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"ok": False, "error": str(exc)})


def main() -> None:
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"nc-tower-sidecar listening on {BIND}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
