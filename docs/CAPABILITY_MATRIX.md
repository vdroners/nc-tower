# NC Tower — capability matrix

Source of truth for Webmin custom modules + Portainer CE + `/media/4TB/ops` (heritage: Admin Cockpit — see CREDITS.md).

Disposition: **IN** · **EXPAND** · **DEEP_LINK** · **SKIP** · **Never** · **Debt**

Program target (v1.16): standalone **day-ops** — Portainer/Webmin optional second opinion for Never/SKIP rows only.

## A. Nextcloud admin surfaces

| Item | Status | Notes |
|------|--------|-------|
| Admin home / users / apps / system | IN | Subnav Ops/Host/Tools |
| NC log viewer / setup checks / jobs / bruteforce / shares / sessions / bloat | IN (1.15) | `NcAdminController` OCP/DB RO; maintenance status chip only |
| Notifications | IN | CSRF on notify* |
| Dashboard widget | IN | Title “NC Tower” |
| GET mutators (enableapp, deleteuser, …) | **Debt** | Admin-only; not Ops |
| Stub API | IN | |

## B. Custom Webmin modules

| Module | Status | Tower |
|--------|--------|-------|
| system-health | IN | `/host/summary` CPU%/temp/swap/ifaces/unhealthy |
| nvidia-gpu | IN | `/host/gpu` (+ processes/power when available) |
| docker | IN | Allowlisted mutate + logs/inspect/exec |
| docker-stacks | IN | pinned up/down/restart/pull/rebuild |
| smart-health | IN | model/temp/hours + NAS + per-attribute detail + 10-min trend |
| backup-mgr | IN | inventory + run + delete; restore stays manual |
| fan-control | IN | GPU + chassis PWM (profiles/curves/pump safety; no history gauges) |
| network-vpn | IN | ZT/WG/ifaces/ddclient/public IP + routes/DNS/listeners/ethtool (RO) |
| host inventory | IN (1.15–1.16) | DMI/DIMM/PCIe/USB, lsblk/RAID, temps+history, posture, kernel log; 1.16 viz |
| containers UX | IN (1.16) | project groups, health/uptime fields, inline actions, active inbox |
| ollama-mgr | IN | models list/pull/delete + VRAM |

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
| prune / security-update | curated cleanup job IN / package hold IN |

## D. Portainer CE (2.39.5)

| Cap | Status |
|-----|--------|
| Container list/stats/ports/project | IN |
| start/stop/restart/kill | IN (allowlist) |
| recreate | IN (allowlist + env/memory/CPU overrides) |
| logs tail + follow (2s poll) | IN |
| inspect (Env redacted) | IN |
| exec (one-shot argv) | IN (allowlist) |
| Stacks up/down/restart/pull/rebuild | IN (pinned files) |
| Images list + pull (pattern allow) | IN |
| Image remove (in-use guarded) | IN |
| Volumes / networks RO | IN |
| Events RO | IN |
| docker info / system df | IN |
| Env/resource editors | IN (via recreate overrides) |
| rename | IN (allowlist) |
| duplicate | **SKIP** |
| prune / registries / templates / Swarm | curated cleanup job IN / **SKIP** |
| Host shell | **Never** |

## E. Stock Webmin (hybrid Host tab)

| Cap | Status |
|-----|--------|
| Mounts / package-updates / proc RO | IN |
| Hardware / storage / temps / posture / kernel log | IN (1.15) |
| systemd status + allowlisted restart | IN |
| cron RO list + root crontab write | IN |
| package hold/unhold | IN |
| net glance + VPN status + network depth | IN |
| useradmin / passwd / firewall editors / filemin / shell | **SKIP** (optional `:10000`) |

## F. Tools deep-links

Portainer `:9443`, Webmin `:10000` modules, Kuma `:3100`, Caddy `:3080`, Guac `:8081`, WebODM `:8001`, Orca `:3030`, ADSB `:8087`, MediaMTX `:8889`, NC `:8080`. WireGuard → NC WireGuard app.

## Hard rules

- No `docker.sock` in `cloud_app` (sidecar only)
- No host shell endpoint
- No `docker system prune` / volume prune routes
- Sidecar token required (not `changeme`); rotate via `sidecar/.env` + `occ config:system:set nc_tower_sidecar_token`
- CSRF on all Tower POSTs from NC UI
- Audit every mutate (stdout + audit log volume)
