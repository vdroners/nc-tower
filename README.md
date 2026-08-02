# Control Tower

**Version 1.8.2**

Control Tower is the Nextcloud orchestrator for this GCS host — admin, stacks, host health, Docker day-ops, and ops inbox in one place.

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
- **Ops tab** — host/GPU/SMART/fans, Docker engine df/events, containers (logs follow, inspect, allowlisted start/stop/restart/kill/recreate/exec), stacks (up/down/restart/pull/rebuild), images/volumes/networks RO, backup run, CRITICAL inbox
- **Host tab** — mounts, package updates, top processes, systemd allowlisted restart, cron RO, network glance
- **Tools tab** — deep links to Portainer, Webmin modules, Kuma, Caddy, Guac, WebODM, Orca, ADSB, MediaMTX, NC; WireGuard via **NC WireGuard app**
- **Sidecar** — privileged host agent; deny-first container allowlist; no `docker.sock` in PHP

## Security never-list

Control Tower does **not**:

- Mount `/var/run/docker.sock` into the Nextcloud PHP container (`cloud_app`)
- Offer a host shell / filemin / unrestricted Portainer clone
- Run `docker system prune` or volume prune
- Manage VPN peers (NC WireGuard app) or Ollama model pull/delete

Allowlisted **container exec** (one-shot argv) is supported; host shell is not.

### Sidecar token

```bash
TOKEN=$(openssl rand -hex 32)
printf 'NC_TOWER_SIDECAR_TOKEN=%s\n' "$TOKEN" > sidecar/.env
chmod 600 sidecar/.env
docker exec -u www-data cloud_app php occ config:system:set nc_tower_sidecar_token --value="$TOKEN"
make sidecar-up
```

Optional env: `NC_TOWER_CONTAINER_ALLOW`, `NC_TOWER_CONTAINER_LOG_ALLOW`, `NC_TOWER_CONTAINER_DENY`, `NC_TOWER_COMPOSE_DIRS`, `NC_TOWER_SYSTEMD_ALLOW`, `NC_TOWER_IMAGE_PULL_ALLOW`.

See [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) and [docs/plans/control-tower-standalone.md](docs/plans/control-tower-standalone.md).

## Requirements

- Nextcloud **31–34**
- Deploy into `custom_apps/nc_tower` (folder name = app id)
- Control Tower sidecar for host/Docker metrics and allowlisted mutators

## Install / deploy (this host)

```bash
cd /media/4TB/nc-tower
make ship RESTART=1   # new routes/classes — restart required
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
