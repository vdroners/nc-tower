# Control Tower — capability matrix

Source of truth for porting Admin Cockpit + Webmin custom modules + Portainer + `/media/4TB/ops`.

Phases: **1** = this ship (RO + harden) · **2** = allowlisted actions · **3** = gated advanced · **Never** = keep break-glass.

## A. Admin Cockpit (upstream)

| Item | Phase | Notes |
|------|-------|-------|
| Admin home / users / apps / system | 1 | Rebranded Control Tower |
| Notifications | 1 | CSRF restored on notify* |
| Dashboard widget | 1 | NcTowerWidget |
| GET mutators (enableapp, deleteuser, …) | 1 debt / 2 | Still GET for prebuilt JS; admin-only |
| Stub API | 1 | Returns app/version |

## B. Custom Webmin modules

| Module | Phase | Approach |
|--------|-------|----------|
| system-health | 1 RO | sidecar `/host/summary` + containers |
| nvidia-gpu | 1–2 | host metrics later |
| docker / docker-stacks | 1 RO / 2 actions | `/containers`, `/stacks` + compose_dirs |
| smart-health | 2 | |
| backup-mgr | 2 | |
| network-vpn | 2 | |
| ollama-mgr | 2 | |
| fan-control | 3 | |

### compose_dirs (pinned)

`/media/4TB/nc-gcs`, `cloud`, `webodm`, `caddy-proxy-manager`, `ollama`, `wireguard`, `guac`, `octoslicer`, `sim/sim2`

## C. Ops scripts (`/media/4TB/ops/bin/webmin`)

| Script | Phase |
|--------|-------|
| inbox / state visibility | 1 RO |
| action-executor queue (same JSON) | 2 |
| container-watchdog CRITICAL allowlist | 2 |
| backup / prune / security-update | 3 SoD |

## D. Portainer CE

| Cap | Phase |
|-----|-------|
| Container list/stats | 1 RO |
| Stacks for compose_dirs | 1 RO |
| Logs / restart allowlist | 2 |
| Console / arbitrary deploy | **Never** |

## E. Tools deep-links

Portainer `:9443`, Webmin `:10000`, Kuma `:3100`, Caddy `:3080`, Guac `:8081` (also `:8280`), WebODM `:8001`, WG `:51821`, Orca `:3030`, ADSB `:8087`, MediaMTX `:8889`, NC `:8080`.

## F. Stock Webmin

Defer useradmin/firewall editors/filemin/shell. Break-glass on `:10000`.

## Hard rules

- No `docker.sock` in `cloud_app`
- No interactive console in NC PHP
- Sidecar token required; default URL `http://nc_tower_sidecar:18765` on `cloud_cloud_network`
