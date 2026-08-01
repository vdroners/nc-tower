# Control Tower Ops UI (1.5.0)

## Goals

Wire Phase-1 sidecar APIs into visible **Ops** / **Tools** tabs and ship allowlisted mutators via the sidecar (never `docker.sock` in `cloud_app`).

## Locked decisions

- Containers: stop / start / restart (allowlist)
- Stacks: per-file compose up / down (pinned dirs)
- Fan: GPU helper only (clamp ≥20%, no Off)
- VPN / Ollama / shell / actions queue: out
- Backup: parse inbox NDJSON only (no trigger)
- Landing: keep Admin Cockpit home

## Verify

```bash
cd /media/4TB/nc-tower && make ship RESTART=1
curl -fsS -H "X-Ops-Token: $NC_TOWER_SIDECAR_TOKEN" http://127.0.0.1:18765/health
docker inspect cloud_app --format '{{json .Mounts}}' | grep -q docker.sock && echo FAIL || echo PASS_no_sock
```

See Cursor plan `control_tower_ops_ui_f115bfed` for full API table and allow/deny lists.
