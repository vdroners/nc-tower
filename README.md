# Control Tower

**Version 1.5.0**

Control Tower is the Nextcloud orchestrator for this GCS host — admin, stacks, health, and ops inbox in one place.

> **Fork of [Admin Cockpit](https://github.com/zomtec2311/admincockpit)** by Wolfgang Tödt — rebranded and extended. See [CREDITS.md](CREDITS.md).

## Attribution / Fork lineage

| | |
|---|---|
| Upstream | [zomtec2311/admincockpit](https://github.com/zomtec2311/admincockpit) (Admin Cockpit) |
| Baseline | v1.3.2 |
| This repo | [vdroners/nc-tower](https://github.com/vdroners/nc-tower) |
| License | [AGPL-3.0](LICENSE) |

Git remotes: `origin` → vdroners/nc-tower, `upstream` → zomtec2311/admincockpit.

## Features

- **Nextcloud admin** — users, groups, apps, system overview (Admin Cockpit home kept)
- **Ops tab** — host disks, GPU, SMART, GPU fan, containers (stats/ports/logs + allowlisted start/stop/restart), per-file compose up/down, backup summary, ops inbox
- **Tools tab** — deep links to Portainer, Webmin modules, Kuma, Caddy, Guac, WebODM, Orca, ADSB, MediaMTX, NC; WireGuard via **NC WireGuard app**
- **Sidecar** — Docker + host metrics; mutators allowlisted (`gcs_*`, `mavlink_gateway` by default; `cloud_*` denied)

## Security never-list

Control Tower does **not**:

- Mount `/var/run/docker.sock` into the Nextcloud PHP container (`cloud_app`)
- Offer an interactive container console / shell
- Replace Webmin or Portainer as break-glass tools
- Manage VPN (use NC WireGuard app) or Ollama

Sidecar may mount docker.sock **read-write** for allowlisted actions only.

### Sidecar token

```bash
# Prefer a strong token in production (preflight warns if still changeme)
docker exec -u www-data cloud_app php occ config:system:set nc_tower_sidecar_token --value='YOUR_TOKEN'
# Match sidecar env NC_TOWER_SIDECAR_TOKEN
```

Optional env: `NC_TOWER_CONTAINER_ALLOW`, `NC_TOWER_CONTAINER_DENY`, `NC_TOWER_COMPOSE_DIRS`.

## Requirements

- Nextcloud **31–34**
- Deploy into `custom_apps/nc_tower` (folder name = app id)
- Control Tower sidecar for host/Docker metrics and allowlisted mutators

## Install / deploy (this host)

```bash
cd /media/4TB/nc-tower
make ship RESTART=1   # new routes/classes in 1.5.0
```

Enable if needed:

```bash
docker exec -u www-data cloud_app php occ app:enable nc_tower
```

## Development

| Path | Role |
|------|------|
| `appinfo/` | id, routes, version |
| `lib/` | PHP controllers / services |
| `js/nc_tower-ops.js` | Owned Ops/Tools UI |
| `js/nc_tower-{main,apps,system,user}.js` | Prebuilt Admin Cockpit bundles |
| `sidecar/` | Host/Docker API |
| `docs/plans/` | Phase plans |
| `docs/CAPABILITY_MATRIX.md` | Port inventory |

```bash
make deploy
make gate-preflight
make bump-patch
```

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) and [CREDITS.md](CREDITS.md).
