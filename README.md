# Control Tower

**Version 1.4.0**

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

```bash
git fetch upstream
# cherry-pick / merge carefully — do not rewrite fork history
```

## Features

- **Nextcloud admin** — users, groups, apps, system overview (from Admin Cockpit)
- **Host health** — CPU/RAM/disk/GPU summary via allowlisted sidecar (Phase 1+)
- **Containers / stacks** — read-only status for pinned compose directories
- **Ops inbox** — visibility into `/media/4TB/ops` alerts (read-only)
- **Tools** — deep links to Portainer, Webmin, Kuma, and related UIs

## Security never-list

Control Tower does **not**:

- Mount `/var/run/docker.sock` into the Nextcloud PHP container
- Offer an interactive container console / shell
- Replace Webmin or Portainer as break-glass tools

Docker power stays in a least-privilege **sidecar** (read-only in Phase 1). Destructive actions (later phases) use allowlists and the existing ops/Alfred JSON queue.

## Requirements

- Nextcloud **31–34**
- Deploy into `custom_apps/nc_tower` (folder name = app id)
- Optional: Control Tower sidecar for host/Docker metrics

## Install / deploy (this host)

```bash
cd /media/4TB/nc-tower
make ship            # deploy + gates
make ship RESTART=1  # when routes/classes were added
```

Enable if needed:

```bash
docker exec -u www-data cloud_app php occ app:enable nc_tower
```

App appears in the Nextcloud navigation as **Control Tower** (admin group).

## Development

| Path | Role |
|------|------|
| `appinfo/` | id, routes, version |
| `lib/` | PHP controllers / services |
| `js/` | Prebuilt frontend bundles (upstream ships without Vue `src/`) |
| `sidecar/` | Read-only host/Docker API (optional) |
| `docs/plans/` | Phase plans |
| `docs/CAPABILITY_MATRIX.md` | Port inventory (Webmin / Portainer / ops) |

```bash
make deploy          # copy into cloud_app
make gate-preflight  # layout + version + API gates
make bump-patch      # sync info.xml version + CHANGELOG stub
```

## Screenshots

See `screenshots/` (inherited from Admin Cockpit; will be updated for Control Tower UI).

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) and [CREDITS.md](CREDITS.md).
