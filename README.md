# NC Tower

**Version 1.12.1**

NC Tower is the Nextcloud orchestrator for this GCS host: Nextcloud admin, Docker
day-ops, host health and the ops inbox in one place, so routine work does not need
Portainer, Webmin or an SSH session.

> **Fork of [Admin Cockpit](https://github.com/zomtec2311/admincockpit)** by Wolfgang Tödt — rebranded and extended. See [CREDITS.md](CREDITS.md).

## Architecture

Everything else follows from this shape, so read it first:

```
browser ──NC session + CSRF──▶ nc_tower (PHP)  ──X-Ops-Token──▶ nc_tower_sidecar ──▶ docker / host
          admin-only                no docker.sock            privileged agent
```

The PHP app never touches Docker. It proxies a token-authenticated HTTP API on a sidecar
container, and that sidecar is the only privileged component. **The sidecar token is
host-root equivalent** — the agent runs `privileged`, with `pid: host`, the Docker socket,
and `nsenter` into PID 1's mount namespace. Guard it accordingly: it lives in
`sidecar/.env` (mode 0600) and in Nextcloud's `config.php`, and `make deploy` deliberately
removes it from the deployed app tree so it is never sitting in the web root.

Access control is **by omission**: Nextcloud requires admin for every controller method
unless one opts out with `#[NoAdminRequired]`. None do, and gate G21 fails the build if
one ever appears.

## Tabs

| Tab | What it gives you |
|---|---|
| **Home** | Health verdict for the host plus a tile per area |
| **Ops** | Verdict banner and attention list first; then containers, stacks, host and disks, SMART, GPU, fans, engine, images, volumes, networks, events, backup, ops inbox |
| **Host** | Mounts, package updates, top processes, systemd (allowlisted restart), cron, network |
| **Apps** · **System** · **Users** | Nextcloud administration, rebuilt in Vue |
| **Tools** | Deep links to Portainer, Webmin, Kuma, Caddy, Guacamole, WebODM, OrcaSlicer, ADSB, MediaMTX (configure URLs in Settings → NC Tower; empty = hidden) |

Ops leads with a verdict — all clear, needs attention, or critical — over the findings that
produced it, with detail sections collapsed behind. The rules live in
[`src/services/health.js`](src/services/health.js) and cover unhealthy and exited
containers, disk pressure, SMART health and drive age, temperatures, critical ops alerts,
stale backups, pending package updates, and Nextcloud's own health (available update,
oversized `nextcloud.log`, app updates). Anything flagged opens its own section.

Sections refresh on their own schedules (containers 10 s … SMART and packages 300 s) and
pause entirely while the browser tab is hidden.

Where Docker generates more rows than a human can read — this host reports 213 mounts of
which 130 are `nsfs`/`overlay`, 70 interfaces of which 61 are veth, and Docker events that
are otherwise 100% healthcheck probes — the UI filters by default, shows the full count,
and offers a toggle. Nothing is hidden silently.

The System tab reports the Nextcloud *container's* filesystems and network; the Host tab
reports the physical host. They legitimately differ and are labelled accordingly.

## Security never-list

NC Tower does **not**:

- Mount `/var/run/docker.sock` into the Nextcloud PHP container (`cloud_app`)
- Offer a host shell, a file manager, or an unrestricted Portainer clone
- Run `docker system prune` or volume prune
- Manage VPN peers (use the NC WireGuard app) or Ollama models

Allowlisted **container exec** is supported as a one-shot argv with no shell. Destructive
actions require the operation typed out to confirm.

Mutations are deny-first: `NC_TOWER_CONTAINER_DENY` wins over `NC_TOWER_CONTAINER_ALLOW`,
so `cloud_*`, the sidecar itself, Portainer, `wg-easy`, `talk_*` and `*openclaw*` can never
be touched from the UI. Every mutation is audited to the sidecar's audit log.

## Requirements

- Nextcloud **31–34**
- Node **≥ 18** to build the front end
- Deployed into `custom_apps/nc_tower` — the folder name must equal the app id
- The sidecar container, for host and Docker data and for any mutation

## Install

```bash
cd /media/4TB/nc-tower
make ship RESTART=1        # build + sidecar up + deploy + gates
docker exec -u www-data cloud_app php occ app:enable nc_tower
```

`RESTART=1` restarts `cloud_app`, which is needed when routes or PHP classes change.

### Sidecar token

```bash
TOKEN=$(openssl rand -hex 32)
printf 'NC_TOWER_SIDECAR_TOKEN=%s\n' "$TOKEN" > sidecar/.env
chmod 600 sidecar/.env
docker exec -u www-data cloud_app php occ config:system:set nc_tower_sidecar_token --value="$TOKEN"
make sidecar-up
```

Both sides must match. With no token the sidecar fails closed: reads return 401 (except
`/health`) and every mutation returns 403.

### Tuning

`NC_TOWER_CONTAINER_ALLOW`, `NC_TOWER_CONTAINER_LOG_ALLOW`, `NC_TOWER_CONTAINER_DENY`,
`NC_TOWER_COMPOSE_DIRS`, `NC_TOWER_SYSTEMD_ALLOW`, `NC_TOWER_IMAGE_PULL_ALLOW`.

`NC_TOWER_CONTAINER_LOG_ALLOW` is worth setting deliberately: left empty it falls back to
the *mutate* allowlist, so containers outside that list show as `locked` with no logs at
all. Widening it grants read-only logs and inspect without granting any mutation rights.

## Verify

```bash
make gate-preflight                                              # host-side gates
docker exec cloud_app php /var/www/html/custom_apps/nc_tower/tools/tower-api-gates.php
docker exec cloud_app grep '<version>' /var/www/html/custom_apps/nc_tower/appinfo/info.xml
curl -fsS -H "X-Ops-Token: $(grep TOKEN sidecar/.env | cut -d= -f2)" http://127.0.0.1:18765/health
```

The gates are the safety net, so they check behaviour rather than only file presence:

| Gate | Asserts |
|---|---|
| G11–G12 | No `docker.sock` in PHP, no host-shell or prune route, sidecar fails closed, token absent from the deployed tree |
| G19 | The bundle is really built, every template mounts it, and it never carries the sidecar header |
| G20 | Sidecar **payload field names**, against the live sidecar |
| G21 | No `#[NoAdminRequired]` in any controller |
| G22 | The prebuilt upstream bundles are gone |
| G23 | Every name a Vue template uses is actually declared |
| G24 | User storage does not depend on an API that Nextcloud 31–34 lacks |
| G25 | Contested URLs resolve to their intended handler, asked of the real router |
| G26 | House style: icon component, no Unicode glyphs, `nc-tower-` prefix, tests present |

G20, G23, G24 and G25 each exist because of a real defect: shipped code passed every route and
file gate while the values it displayed were wrong, webpack compiles a template that reads
an undeclared name without complaint, and the Users tab showed a dash for every account
while some held hundreds of gigabytes, and a route placeholder declared one line too early
silently swallowed container Exec and Recreate for three releases.

## Development

| Path | Role |
|---|---|
| `appinfo/` | App id, routes, version |
| `lib/` | PHP controllers and services |
| `src/` | Vue front end — `views/` (7 tabs + widget), `components/`, `services/` |
| `js/` | Build output — generated, never edit by hand |
| `sidecar/` | Privileged host agent (Python, stdlib only) |
| `tools/` | Gate harnesses |
| `src/__tests__/` | vitest specs (`npm run test`) |
| `docs/plans/` | Checked-in plans |

```bash
npm ci && npm run build    # or: make build
npm run check:refs         # template reference check alone
npm run test               # vitest (triage rules and formatters)
make deploy
make gate-preflight
make bump-patch
```

Icons are inline SVG from `src/components/NcTowerIcon.vue`, the same per-app registry
pattern as `GcsIcon.vue` and `NcPrintIcon.vue` — no icon library is used anywhere in the
estate. CSS classes are prefixed `nc-tower-`, matching `nc-print-` / `nc-roomba-` / `nc-wg-`.

The front end is Vue 2.7 + `@nextcloud/vue` 8, matching nc_gcs. All seven PHP routes mount
the same bundle and choose their view from a `data-page` attribute, so deep links and hard
refreshes work without a router.

**Build gotcha.** `vue-demi` ships a shim its own `postinstall` rewrites to match the
installed Vue. Where npm blocks dependency install scripts, that never runs and every
`@nextcloud/vue` component fails to compile with a misleading
`export 'Fragment' was not found in 'vue-demi'`. `scripts/fix-vue-demi.mjs` runs from
`prebuild` to make the build deterministic either way — don't remove it.

Changes big enough to need a plan get one checked into `docs/plans/` first;
[`control-tower-vue-rebuild.md`](docs/plans/control-tower-vue-rebuild.md) is the most
recent. See also [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) for what is
deliberately in, deep-linked, or refused.

## Attribution / fork lineage

| | |
|---|---|
| Upstream | [zomtec2311/admincockpit](https://github.com/zomtec2311/admincockpit) (Admin Cockpit) |
| Baseline | v1.3.2 |
| This repo | [vdroners/nc-tower](https://github.com/vdroners/nc-tower) |
| License | [AGPL-3.0](LICENSE) |

Git remotes: `origin` → vdroners/nc-tower, `upstream` → zomtec2311/admincockpit.

The four Admin Cockpit page bundles were removed in 1.9.0 and their pages reimplemented in
Vue against the same PHP endpoints, so those views no longer track upstream.

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) and [CREDITS.md](CREDITS.md).
