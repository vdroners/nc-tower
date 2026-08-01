# Control Tower — capability matrix

Source of truth for porting Admin Cockpit + Webmin custom modules + Portainer + `/media/4TB/ops`.

Phases: **1** = RO + harden · **1.5** = Ops/Tools UI · **2** = allowlisted actions · **3** = gated advanced · **Never** = break-glass · **N/A** = handled elsewhere · **Debt** = known leftover.

## A. Admin Cockpit (upstream)

| Item | Phase | Notes |
|------|-------|-------|
| Admin home / users / apps / system | 1 + 1.5 | Rebranded; subnav adds Ops/Tools |
| Notifications | 1 | CSRF restored on notify* |
| Dashboard widget | 1.5 | Title “Control Tower” |
| GET mutators (enableapp, deleteuser, …) | **Debt** | Still GET for prebuilt JS; admin-only; not part of Ops UI |
| Stub API | 1 | Returns app/version |

## B. Custom Webmin modules

| Module | Phase | Approach |
|--------|-------|----------|
| system-health | 1.5 UI | Ops Host + `/host/summary` |
| nvidia-gpu | 1.5 UI | Ops GPU + `/host/gpu` (RO) |
| docker / docker-stacks | 1.5 + 2 | list/stats/logs + allowlisted start/stop/restart; per-file up/down |
| smart-health | 1.5 UI | `/host/smart` PASS/FAIL; full attrs via Webmin |
| backup-mgr | 1.5 parse-only | Ops inbox NDJSON; **no** trigger in Tower |
| network-vpn | **N/A** | NC WireGuard app |
| ollama-mgr | **N/A** | Out of Tower |
| fan-control | **1.5** GPU helper | `/host/fan` via gpu-fan-helper; chassis → Webmin |

### compose_dirs (pinned)

`/media/4TB/nc-gcs`, `cloud`, `webodm`, `caddy-proxy-manager`, `wireguard`, `guac`, `octoslicer`, `sim/sim2` (ollama may show missing)

## C. Ops scripts (`/media/4TB/ops/bin/webmin`)

| Script | Phase |
|--------|-------|
| inbox / state visibility | 1.5 UI |
| backup parse (issues NDJSON) | 1.5 |
| action-executor queue | deferred / out this ship |
| container-watchdog CRITICAL allowlist | **Deferred** next round |
| backup / prune / security-update | 3 SoD / Webmin |

## D. Portainer CE

| Cap | Phase |
|-----|-------|
| Container list/stats/ports | 1.5 UI |
| Stacks for compose_dirs | 1.5 UI |
| Logs / restart allowlist | 2 shipped in 1.5 |
| Console / arbitrary deploy | **Never** |
| Env/volumes/registry | Portainer deep-link |

## E. Tools deep-links

Portainer `:9443`, Webmin `:10000` + modules (system-health, docker, docker-stacks, nvidia-gpu, smart-health, backup-mgr, fan-control), Kuma `:3100`, Caddy `:3080`, Guac `:8081`, WebODM `:8001`, Orca `:3030`, ADSB `:8087`, MediaMTX `:8889`, NC `:8080`. WireGuard → **NC WireGuard app** (not wg-easy URL).

## F. Stock Webmin

Defer useradmin/firewall editors/filemin/shell. Break-glass on `:10000`.

## Hard rules

- No `docker.sock` in `cloud_app` (sidecar may use `:rw` for allowlisted mutators)
- No interactive console in NC PHP
- Sidecar token required; default URL `http://nc_tower_sidecar:18765` on `cloud_cloud_network`
- Default container allow: `gcs_*`, `mavlink_gateway` — **not** `cloud_*`
