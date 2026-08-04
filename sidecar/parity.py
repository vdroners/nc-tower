"""NC Tower sidecar parity helpers — Portainer/Webmin gap closures.

Pure functions taking injected runners so unit tests can exercise validation
without Docker or host privileges.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+./-]{0,200}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,200}$")
DEV_RE = re.compile(r"^/dev/[a-zA-Z0-9/._+-]+$")


def validate_container_name(name: str) -> bool:
    return bool(NAME_RE.fullmatch(name or ""))


def redact_wg_key(key: str) -> str:
    key = (key or "").strip()
    if len(key) <= 8:
        return "********"
    return f"…{key[-8:]}"


def backup_path_contained(backup_root: Path, filename: str) -> Path | None:
    """Resolve filename under backup_root; reject traversal."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        # Allow one-level relative names only (no path separators).
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            return None
    try:
        root = backup_root.resolve(strict=True)
    except OSError:
        try:
            root = backup_root.resolve()
        except OSError:
            return None
    candidate = (root / Path(filename).name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def apply_recreate_overrides(
    run_args: list[str],
    body: dict[str, Any],
) -> tuple[list[str] | None, str | None]:
    """Merge env/memory/cpus/restart overrides into reconstructed docker run argv."""
    args = list(run_args)
    env_set = body.get("env_set") or []
    env_unset = body.get("env_unset") or []
    if not isinstance(env_set, list) or not isinstance(env_unset, list):
        return None, "env_must_be_lists"
    unset_keys = set()
    for key in env_unset:
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key):
            return None, "invalid_env_unset_key"
        unset_keys.add(key)
    # Drop existing -e KEY=… for unset / replaced keys
    new_env: dict[str, str] = {}
    i = 0
    rebuilt: list[str] = []
    while i < len(args):
        if args[i] == "-e" and i + 1 < len(args):
            pair = args[i + 1]
            key = pair.split("=", 1)[0]
            if key not in unset_keys:
                new_env[key] = pair.split("=", 1)[1] if "=" in pair else ""
            i += 2
            continue
        rebuilt.append(args[i])
        i += 1
    for pair in env_set:
        if not isinstance(pair, str) or "=" not in pair:
            return None, "env_set_must_be_key_equals_value"
        key, value = pair.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key):
            return None, "invalid_env_set_key"
        if any(ch in value for ch in ";|&$`"):
            return None, "unsafe_env_value"
        new_env[key] = value
    # Re-insert env before image (last non-flag-ish token cluster is fragile;
    # insert after --name NAME which is always early).
    insert_at = 1
    for idx, token in enumerate(rebuilt):
        if token == "--name" and idx + 1 < len(rebuilt):
            insert_at = idx + 2
            break
    env_args: list[str] = []
    for key, value in new_env.items():
        env_args += ["-e", f"{key}={value}"]
    rebuilt = rebuilt[:insert_at] + env_args + rebuilt[insert_at:]

    # Resource flags: strip existing then append
    def strip_flag(argv: list[str], flags: set[str]) -> list[str]:
        out: list[str] = []
        skip = 0
        for token in argv:
            if skip:
                skip -= 1
                continue
            if token in flags:
                skip = 1
                continue
            if token.startswith("--memory=") or token.startswith("--cpus="):
                continue
            out.append(token)
        return out

    if body.get("memory") is not None or body.get("cpus") is not None or body.get("restart_policy") is not None:
        rebuilt = strip_flag(rebuilt, {"--memory", "-m", "--cpus", "--restart"})
    memory = body.get("memory")
    if memory is not None and memory != "":
        if not isinstance(memory, str) or not re.fullmatch(r"[0-9]+[bBkKmMgGtT]?", memory):
            return None, "invalid_memory"
        # Insert after docker run -d
        rebuilt = rebuilt[:3] + ["--memory", memory] + rebuilt[3:]
    cpus = body.get("cpus")
    if cpus is not None and cpus != "":
        try:
            cpus_f = float(cpus)
        except (TypeError, ValueError):
            return None, "invalid_cpus"
        if not 0.01 <= cpus_f <= 256:
            return None, "cpus_out_of_range"
        rebuilt = rebuilt[:3] + ["--cpus", str(cpus_f)] + rebuilt[3:]
    restart = body.get("restart_policy")
    if restart is not None and restart != "":
        if not isinstance(restart, str) or restart not in {"no", "always", "unless-stopped", "on-failure"}:
            return None, "invalid_restart_policy"
        rebuilt = rebuilt[:3] + ["--restart", restart] + rebuilt[3:]
    return rebuilt, None


def parse_wg_dump(text: str) -> list[dict[str, Any]]:
    peers = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        # interface public_key ... OR peer lines: public_key endpoint allowed_ips ...
        if parts[0] and not parts[0].startswith("wg") and len(parts[0]) > 20:
            peers.append(
                {
                    "public_key": redact_wg_key(parts[0]),
                    "endpoint": parts[2] if len(parts) > 2 else None,
                    "allowed_ips": parts[3] if len(parts) > 3 else None,
                    "latest_handshake": int(parts[4]) if parts[4].isdigit() else None,
                    "transfer_rx": int(parts[5]) if parts[5].isdigit() else None,
                    "transfer_tx": int(parts[6]) if parts[6].isdigit() else None,
                }
            )
    return peers


def host_network_payload(
    *,
    run: Callable[..., dict[str, Any]],
    nsenter_bin: Callable[[], str | None],
    public_ip_cache: dict[str, Any],
) -> dict[str, Any]:
    nsenter = nsenter_bin()

    def host_cmd(argv: list[str], timeout: int = 10) -> dict[str, Any]:
        if nsenter:
            return run([nsenter, "--mount=/proc/1/ns/mnt", "--", *argv], timeout=timeout)
        return run(argv, timeout=timeout)

    zerotier: dict[str, Any] = {"unavailable": False}
    zt = host_cmd(["/usr/sbin/zerotier-cli", "-j", "listnetworks"])
    if zt.get("exit") != 0:
        zt = host_cmd(["zerotier-cli", "-j", "listnetworks"])
    if zt.get("exit") == 0:
        try:
            zerotier["networks"] = json.loads(zt.get("stdout") or "[]")
        except json.JSONDecodeError:
            zerotier["networks"] = []
            zerotier["raw"] = zt.get("stdout")
        info = host_cmd(["/usr/sbin/zerotier-cli", "-j", "info"])
        if info.get("exit") != 0:
            info = host_cmd(["zerotier-cli", "-j", "info"])
        if info.get("exit") == 0:
            try:
                zerotier["info"] = json.loads(info.get("stdout") or "{}")
            except json.JSONDecodeError:
                pass
    else:
        zerotier = {"unavailable": True, "reason": zt.get("stderr") or "zerotier-cli_missing"}

    wireguard: dict[str, Any] = {"unavailable": False, "peers": []}
    wg = host_cmd(["/usr/bin/wg", "show", "all", "dump"])
    if wg.get("exit") != 0:
        wg = host_cmd(["wg", "show", "all", "dump"])
    if wg.get("exit") == 0:
        wireguard["peers"] = parse_wg_dump(wg.get("stdout") or "")
    else:
        wireguard = {"unavailable": True, "reason": wg.get("stderr") or "wg_missing", "peers": []}

    interfaces: dict[str, Any] = {"unavailable": False, "items": []}
    ip = host_cmd(["/sbin/ip", "-j", "-s", "link"])
    if ip.get("exit") != 0:
        ip = host_cmd(["ip", "-j", "-s", "link"])
    if ip.get("exit") == 0:
        try:
            rows = json.loads(ip.get("stdout") or "[]")
        except json.JSONDecodeError:
            rows = []
        for row in rows if isinstance(rows, list) else []:
            stats = row.get("stats64") or row.get("stats") or {}
            rx = (stats.get("rx") or {})
            tx = (stats.get("tx") or {})
            interfaces["items"].append(
                {
                    "ifname": row.get("ifname"),
                    "operstate": row.get("operstate"),
                    "mtu": row.get("mtu"),
                    "rx_bytes": rx.get("bytes"),
                    "tx_bytes": tx.get("bytes"),
                    "rx_errors": rx.get("errors"),
                    "tx_errors": tx.get("errors"),
                }
            )
    else:
        interfaces = {"unavailable": True, "reason": "ip_missing", "items": []}

    ddclient: dict[str, Any] = {"unavailable": False}
    dd = host_cmd(["/bin/systemctl", "is-active", "ddclient.service"])
    if dd.get("exit") is None or (dd.get("stderr") or "").find("not found") >= 0:
        ddclient = {"unavailable": True, "reason": "ddclient_missing"}
    else:
        ddclient["active"] = (dd.get("stdout") or "").strip() == "active"
        ddclient["state"] = (dd.get("stdout") or "").strip() or "unknown"

    public_ip: dict[str, Any] = {"unavailable": False}
    now = time.time()
    if public_ip_cache.get("ip") and now - float(public_ip_cache.get("ts") or 0) < 600:
        public_ip["ip"] = public_ip_cache["ip"]
        public_ip["cached"] = True
    else:
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
                ip_text = resp.read().decode("utf-8", errors="replace").strip()
            if re.fullmatch(r"[0-9a-fA-F:.]+", ip_text):
                public_ip_cache["ip"] = ip_text
                public_ip_cache["ts"] = now
                public_ip["ip"] = ip_text
                public_ip["cached"] = False
            else:
                public_ip = {"unavailable": True, "reason": "bad_response"}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            public_ip = {"unavailable": True, "reason": str(exc)}

    return {
        "zerotier": zerotier,
        "wireguard": wireguard,
        "interfaces": interfaces,
        "ddclient": ddclient,
        "public_ip": public_ip,
        "ts": time.time(),
    }


def ollama_get(base_url: str, timeout: int = 10) -> dict[str, Any]:
    base = base_url.rstrip("/")

    def fetch(path: str) -> Any:
        req = urllib.request.Request(base + path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    try:
        tags = fetch("/api/tags")
        models = tags.get("models") if isinstance(tags, dict) else []
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"unavailable": True, "reason": str(exc), "models": [], "running": []}
    try:
        ps = fetch("/api/ps")
        running = ps.get("models") if isinstance(ps, dict) else []
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        running = []
    return {
        "unavailable": False,
        "base_url": base,
        "models": models or [],
        "running": running or [],
        "ts": time.time(),
    }


def ollama_delete(base_url: str, model: str) -> dict[str, Any]:
    if not MODEL_RE.fullmatch(model or ""):
        return {"ok": False, "error": "invalid_model", "http": 400}
    base = base_url.rstrip("/")
    data = json.dumps({"model": model}).encode("utf-8")
    req = urllib.request.Request(
        base + "/api/delete",
        data=data,
        method="DELETE",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return {"ok": True, "model": model, "response": body}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"http_{exc.code}", "detail": exc.read().decode("utf-8", errors="replace")}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": str(exc), "http": 502}


def audit_tail(path: Path, limit: int = 200) -> dict[str, Any]:
    limit = max(1, min(int(limit), 2000))
    if not path.is_file():
        return {"ok": True, "rows": [], "path": str(path)}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError as exc:
        return {"ok": False, "error": str(exc), "rows": []}
    rows = []
    for line in lines:
        ts = None
        m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", line)
        if m:
            ts = m.group(1)
        rows.append({"ts": ts, "line": line})
    return {"ok": True, "rows": rows, "path": str(path), "ts": time.time()}


def parse_smart_attributes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    table = payload.get("ata_smart_attributes") or {}
    for entry in table.get("table") or []:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("raw") or {}
        rows.append(
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "value": entry.get("value"),
                "worst": entry.get("worst"),
                "thresh": entry.get("thresh"),
                "raw": raw.get("string") or raw.get("value"),
                "when_failed": entry.get("when_failed"),
            }
        )
    # NVMe
    for key, block in (payload.get("nvme_smart_health_information_log") or {}).items() if isinstance(payload.get("nvme_smart_health_information_log"), dict) else []:
        rows.append({"id": None, "name": key, "value": block, "worst": None, "thresh": None, "raw": block})
    return rows


SIDECAR_VERSION = "1.15.0"
CAPABILITIES = [
    "chassis-fan-write",
    "chassis-fan-history",
    "rename",
    "recreate-overrides",
    "image-remove",
    "container-stats",
    "cleanup-job",
    "package-hold",
    "cron-write",
    "smart-attributes",
    "backup-delete",
    "network",
    "network-depth",
    "ollama",
    "audit",
    "hardware",
    "storage-topology",
    "temperatures",
    "posture",
    "kernel-log",
    "smart-history",
]
