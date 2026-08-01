# Control Tower — capability matrix

Source of truth for Admin Cockpit + Webmin custom modules + Portainer CE + `/media/4TB/ops`.

Disposition: **IN** · **EXPAND** · **DEEP_LINK** · **SKIP** · **Never** · **Debt**

Program target (v1.8): standalone **day-ops** — Portainer/Webmin remain break-glass for DEEP_LINK/Never rows.

## A. Admin Cockpit (upstream)

| Item | Status | Notes |
|------|--------|-------|
| Admin home / users / apps / system | IN | Rebranded; subnav Ops/Host/Tools |
| Notifications | IN | CSRF on notify* |
| Dashboard widget | IN | Title “Control Tower” |
| GET mutators (enableapp, deleteuser, …) | **Debt** | Prebuilt JS; admin-only; not Ops |
| Stub API | IN | |

## B. Custom Webmin modules

| Module | Status | Tower |
|--------|--------|-------|
| system-health | IN | `/host/summary` CPU%/temp/swap/ifaces/unhealthy |
| nvidia-gpu | IN | `/host/gpu` (+ processes/power when available) |
| docker | IN | Allowlisted mutate + logs/inspect/exec |
| docker-stacks | IN | pinned up/down/restart/pull/rebuild |
| smart-health | IN | model/temp/hours + NAS; full attrs **DEEP_LINK** |
| backup-mgr | IN | inbox parse + **run_backup**; delete **DEEP_LINK** |
| fan-control | PARTIAL | GPU mutate IN; chassis RO IN; PWM writes **DEEP_LINK** |
| network-vpn | **SKIP** | NC WireGuard + Kuma |
| ollama-mgr | **SKIP** | out of Tower |

### compose_dirs (pinned)

`nc-gcs`, `cloud`, `webodm`, `caddy-proxy-manager`, `wireguard`, `guac`, `octoslicer`, `sim/sim2`, `nc-tower`, `nc-print`, `ollama`

### container allow (default)

Mutate: `gcs_*`, `mavlink_gateway`, `gcs_sitl`, `gcs_simcam`, `gcs_adsb*`  
Deny (wins): `nc_tower_sidecar`, `cloud_*`, `portainer`, `wg-easy`, `talk_*`, `*openclaw*`  
Optional `NC_TOWER_CONTAINER_LOG_ALLOW` for wider RO logs/inspect.

## C. Ops scripts (`/media/4TB/ops`)

| Script / signal | Status |
|-----------------|--------|
| inbox / state visibility | IN |
| backup parse + run (`backup-enhanced.sh`) | IN |
| CRITICAL inbox surface | IN (RO) |
| action-executor queue | **SKIP** |
| prune / security-update | **DEEP_LINK** / Webmin |

## D. Portainer CE (2.39.5)

| Cap | Status |
|-----|--------|
| Container list/stats/ports/project | IN |
| start/stop/restart/kill | IN (allowlist) |
| recreate | IN (allowlist + confirm) |
| logs tail + follow (2s poll) | IN |
| inspect (Env redacted) | IN |
| exec (one-shot argv) | IN (allowlist) |
| Stacks up/down/restart/pull/rebuild | IN (pinned files) |
| Images list + pull (pattern allow) | IN |
| Volumes / networks RO | IN |
| Events RO | IN |
| docker info / system df | IN |
| Env/resource editors | **DEEP_LINK** |
| remove/rename/duplicate | **DEEP_LINK** |
| prune / registries / templates / Swarm | **SKIP** / **DEEP_LINK** |
| Host shell | **Never** |

## E. Stock Webmin (hybrid Host tab)

| Cap | Status |
|-----|--------|
| Mounts / package-updates / proc RO | IN |
| systemd status + allowlisted restart | IN |
| cron RO list | IN |
| net glance | IN |
| useradmin / passwd / firewall editors / filemin / shell | **SKIP** (break-glass `:10000`) |

## F. Tools deep-links

Portainer `:9443`, Webmin `:10000` modules, Kuma `:3100`, Caddy `:3080`, Guac `:8081`, WebODM `:8001`, Orca `:3030`, ADSB `:8087`, MediaMTX `:8889`, NC `:8080`. WireGuard → NC WireGuard app.

## Hard rules

- No `docker.sock` in `cloud_app` (sidecar only)
- No host shell endpoint
- No `docker system prune` / volume prune routes
- Sidecar token required (not `changeme`); rotate via `sidecar/.env` + `occ config:system:set nc_tower_sidecar_token`
- CSRF on all Tower POSTs from NC UI
- Audit every mutate (stdout + audit log volume)
