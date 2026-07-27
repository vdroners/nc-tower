#!/usr/bin/env python3
"""Control Tower read-only sidecar — Docker + host + ops inbox. No mutations."""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    import docker
except ImportError:  # pragma: no cover
    docker = None

TOKEN = os.environ.get("NC_TOWER_SIDECAR_TOKEN", "")
OPS_ROOT = Path(os.environ.get("NC_TOWER_OPS_ROOT", "/media/4TB/ops"))
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
                "/media/4TB/ollama",
                "/media/4TB/wireguard",
                "/media/4TB/guac",
                "/media/4TB/octoslicer",
                "/media/4TB/sim/sim2",
            ]
        ),
    ).split(",")
    if p.strip()
]
BIND = os.environ.get("NC_TOWER_BIND", "127.0.0.1")
PORT = int(os.environ.get("NC_TOWER_PORT", "18765"))


def _read_proc(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def host_summary() -> dict:
    loadavg = _read_proc("/proc/loadavg").split()[:3]
    mem = {}
    for line in _read_proc("/proc/meminfo").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            mem[k.strip()] = v.strip()
    return {
        "loadavg": loadavg,
        "mem_total": mem.get("MemTotal"),
        "mem_available": mem.get("MemAvailable"),
        "uptime_s": float(_read_proc("/proc/uptime").split()[0] or 0),
        "ts": time.time(),
    }


def containers() -> dict:
    if docker is None:
        return {"error": "docker_sdk_missing", "containers": []}
    client = docker.from_env()
    rows = []
    for c in client.containers.list(all=True):
        rows.append(
            {
                "name": c.name,
                "id": c.short_id,
                "status": c.status,
                "image": (
                    c.image.tags[0]
                    if c.image.tags
                    else (c.image.short_id if c.image else "")
                ),
            }
        )
    return {"containers": rows, "count": len(rows), "ts": time.time()}


def stacks() -> dict:
    found = []
    for d in COMPOSE_DIRS:
        p = Path(d)
        compose = None
        for name in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
            cand = p / name
            if cand.is_file():
                compose = str(cand)
                break
        # Also scan one level for compose/ subdir (nc-gcs style)
        compose_files = []
        if (p / "compose").is_dir():
            compose_files = sorted(str(x) for x in (p / "compose").glob("docker-compose*.yml"))
        found.append(
            {
                "dir": d,
                "exists": p.is_dir(),
                "compose": compose,
                "compose_files": compose_files[:40],
            }
        )
    return {"stacks": found, "ts": time.time()}


def ops_inbox_summary() -> dict:
    inbox = OPS_ROOT / "inbox"
    state = OPS_ROOT / "state"
    actions = OPS_ROOT / "actions"
    recent = []
    if inbox.is_dir():
        files = sorted(inbox.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in files[:30]:
            if f.is_file():
                recent.append(
                    {
                        "name": f.name,
                        "mtime": f.stat().st_mtime,
                        "size": f.stat().st_size,
                    }
                )
    return {
        "ops_root": str(OPS_ROOT),
        "inbox_recent": recent,
        "state_exists": state.is_dir(),
        "actions_exists": actions.is_dir(),
        "ts": time.time(),
    }


ROUTES = {
    "/health": lambda: {"ok": True, "service": "nc-tower-sidecar", "ts": time.time()},
    "/host/summary": host_summary,
    "/containers": containers,
    "/stacks": stacks,
    "/ops/inbox-summary": ops_inbox_summary,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter
        pass

    def _auth_ok(self) -> bool:
        if not TOKEN:
            return True
        return self.headers.get("X-Ops-Token") == TOKEN

    def do_GET(self) -> None:  # noqa: N802
        if not self._auth_ok():
            self.send_response(401)
            self.end_headers()
            return
        path = urlparse(self.path).path
        fn = ROUTES.get(path)
        if fn is None:
            self.send_response(404)
            self.end_headers()
            return
        try:
            payload = fn()
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            err = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)


def main() -> None:
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"nc-tower-sidecar listening on {BIND}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
