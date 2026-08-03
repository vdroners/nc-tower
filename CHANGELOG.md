# Changelog

## [1.11.0] - 2026-08-03

Job runner, host updates brought in-house, and the first visualisations.
Plan: `docs/plans/control-tower-jobs-and-visuals.md`.

### Added
- **Detached job runner.** Long operations are handed to the host's systemd and their
  state lives in `/ops/jobs`, so they survive both this request and the sidecar itself.
  Proven: a job was started, the sidecar restarted underneath it, and it still completed
  and stayed readable. This is a prerequisite for updates — every pending package on this
  host is `docker-ce`, and upgrading it restarts the daemon that runs the sidecar
- **Host → Updates.** Pending packages, whether any restart Docker, whether a reboot is
  required, a dry run, and an **Install updates** action behind a typed confirmation.
  `apt-get` is invoked with a fixed argv; nothing an operator types reaches the command.
  Control Tower never reboots — that stays deliberate and manual
- `TowerChart.vue` (chart.js, modelled on nc-wireguard's RateChart) and `Sparkline.vue`
  (canvas, modelled on nc-print's TemperatureSparkline) — the estate's two chart patterns
- Visualisations: per-container CPU sparkline and share bar, SMART drive-life bars against
  the 7-year mark, Docker used-vs-reclaimable, host memory trend from the 6,202 samples the
  host already records, a 24 h ops-alert timeline on Home, and a top-10 storage bar on Users
- Gates **G27** (jobs detached, argv fixed, no reboot ever issued) and G20 payload cases for
  the new endpoints, including that a service answering 404 counts as reachable

### Changed
- **Tools is now Services**: live reachability per console, grouped into absorbed into
  Tower / break-glass / external, with each break-glass entry stating what it is still for.
  OrcaSlicer was down and the old flat link grid gave no hint
- Backup, image pull and stack actions can move onto the job path, which fixes their
  existing habit of timing out in the browser while succeeding on the host

## [1.10.0] - 2026-08-03

Continuity test of front end against backend, plus alignment with the other Nextcloud
apps in this estate. Plan: `docs/plans/control-tower-continuity-house-style.md`.

### Fixed
- **Container Exec and Recreate never worked.** `/tower/containers/{name}/{action}` was
  declared ahead of the specific `/exec` and `/recreate` routes, so the router matched the
  generic one first and `containerAction()` rejected both with `400 invalid_action`. The
  placeholder is now constrained to `start|stop|restart|kill` and the specific routes come
  first. Unknown actions are refused by the router instead of reaching the controller
- `fmt.years(null)` rendered `0 y` — a drive of unknown age looked brand new. Caught by the
  new test suite on its first run
- Removed the `tower#stackUp` / `tower#stackDown` aliases, which `stackAction` shadowed

### Added
- **`NcTowerIcon.vue`** — inline-SVG registry matching the estate convention set by
  `GcsIcon.vue` and `NcPrintIcon.vue` (Tabler paths, 24 viewBox, `stroke="currentColor"`,
  name-keyed with a dot fallback). No icon library, as everywhere else in the estate
- Icons on the seven nav tabs, section disclosure and refresh, table sort carets, and every
  container / stack / user row action
- **User editing is back.** The 1.9.0 rebuild dropped it while `edituser`, `saveuser` and
  `userexists` stayed in PHP with no UI. Create now checks `userexists` before POSTing
- vitest + happy-dom matching nc-print's setup; 40 tests covering every triage rule
  threshold in `health.js` and the payload shapes `format.js` has to absorb
- Gate **G25** resolves contested URLs through the real Nextcloud router — the only check
  that catches route shadowing, since grepping `routes.php` cannot. Gate **G26** asserts the
  house style: icon component present, no Unicode glyphs, `nc-tower-` prefix, tests present

### Changed
- CSS classes renamed `tower-*` → `nc-tower-*`, matching `nc-print-`, `nc-roomba-`,
  `nc-litter-` and `nc-wg-`. Control Tower was the last app off-pattern
- New `img/app.svg`: a Control Tower mark replacing upstream Admin Cockpit's generic window
  glyph, which had never been rebranded

### Removed
- `img/app-dark.svg` and `img/infoLogCleaner.png`, both dead upstream leftovers.
  `img/dummy.svg` stays — `AppsController` serves it for apps with no icon

## [1.9.2] - 2026-08-02

Fixes found by auditing the deployed app against live data — every column of every
table checked against the payload that feeds it.

### Fixed
- **Users → Used was always `—`** while 15 of 126 accounts held real data (521 GB,
  66 GB, 63 GB…). `quotaUsedLabel()` depended on `IUser::getQuotaUsage()`, which does
  not exist on Nextcloud 31–34, so every account fell through to a dash. Replaced with
  a single `filecache`⋈`storages` join covering all users at once — no per-user
  filesystem setup, so it does not reintroduce the 1.4.1 hang. Sorts on raw bytes
- **System → "data dir" showed a filesystem path where a size belongs.** `/storage`
  returns the datadirectory *path* in `folder`; the byte counts are in `folder4`/`folder3`.
  Now renders used / free / total with a usage bar
- **Ops → Docker events was 100% healthcheck noise** — every event in the last hour was
  `exec_create`/`exec_start`/`exec_die`, and the 100-row cap evicted real lifecycle
  events before anyone saw them. The sidecar now filters probes before capping, so
  start/die/pull/health_status are visible; a switch restores them

### Changed
- Host → Mounts hides container and pseudo filesystems by default (213 rows → 9 here)
  and Host → Network hides docker veth/bridge interfaces (70 → 9). Both show the total
  and a toggle, so nothing is filtered silently
- The verdict banner now covers Nextcloud's own health: pending Nextcloud update,
  oversized `nextcloud.log`, and app updates
- Ops opens Containers, Stacks, Host and storage, and Backup / Ops inbox by default
- System labels its filesystem and network figures as the Nextcloud container's view —
  the Host tab reports the physical host, and the two legitimately differ

### Added
- Gate G24 (user storage no longer depends on an absent API) and a G20 case asserting
  Docker events are not exclusively healthcheck probes

## [1.9.1] - 2026-08-02

### Fixed
- Ops failed to render: the template read `stackRows`, which no component ever
  declared, so the whole flagship view died on a TypeError. Found by the new
  reference checker, not by the build — webpack compiles such templates happily
- Host → Top processes listed the *lowest* CPU first: the table re-sorted the
  sidecar's `--sort=-pcpu` output ascending. `DataTable` gained `default-desc`
- Confirmation dialogs received their callback through `v-bind`, so Vue
  stringified a function onto the DOM as an `action` attribute; the pending
  callback is now held separately from the dialog's props
- Opening logs for a second container left the first container's 2 s follow
  timer running, overwriting the new dialog's contents
- The app never mounted if its script landed after `DOMContentLoaded`, leaving a
  blank page; both entries now check `document.readyState`

### Changed
- The `Poller` moved out of `data()`. Vue was observing its Map and timer
  handles for a value that is never rendered; templates call a `refresh()` method
- Sortable table headers are keyboard reachable and expose `aria-sort`

### Added
- `scripts/check-template-refs.mjs` — compiles every SFC template and asserts each
  name it uses is declared in data / computed / methods / props / components.
  Runs from `prebuild` and as preflight gate G23

## [1.9.0] - 2026-08-01

Full Vue rebuild of all seven tabs. Plan: `docs/plans/control-tower-vue-rebuild.md`.

### Added
- Vue 2.7 + `@nextcloud/vue` front end for Home, Ops, Host, Apps, System, Users, Tools
  and the dashboard widget, built with the same toolchain as nc_gcs
- **Status-first Ops**: verdict banner (all clear / needs attention / critical) over an
  attention list, with every detail section collapsed behind it. Triage rules live in
  `src/services/health.js` — unhealthy/exited containers, disk pressure, SMART health,
  drive age, temperatures, critical ops alerts, stale backups, pending updates
- Home is now an overview: the same verdict plus one tile per area
- Sortable tables that reflow into stacked cards below 720 px; row actions collapse into
  an overflow menu instead of six inline buttons
- Gate G19 (build + every template mounts the bundle), G20 (payload shape asserted
  against the live sidecar), G21 (no `#[NoAdminRequired]` in any controller),
  G22 (prebuilt bundles gone)
- `scripts/fix-vue-demi.mjs`, run from `prebuild`, so the build is reproducible where
  npm blocks dependency install scripts

### Changed
- Per-section refresh intervals replace the 12 s blanket tick: containers 10 s, host 15 s,
  GPU/events 30 s, engine/fans/inbox/stacks 60 s, images/volumes/networks 120 s,
  **SMART and packages 300 s**. Polling pauses while the tab is hidden and catches up on
  return. 1.8 re-ran a five-disk `smartctl` sweep every twelve seconds
- `confirm()` / `prompt('Type RECREATE')` replaced by a themed dialog that keeps the
  typed-confirmation gate but works with a keyboard and on a phone
- Compose previews moved out of table cells into a dialog
- `make build` now compiles from `src/`; the "prebuilt assets" shortcut is gone

### Removed
- The four prebuilt Admin Cockpit bundles (~14 MB of minified JS with no source in this
  repo) plus the hand-rolled Ops UI, subnav partial and legacy stylesheets. The app now
  ships a 1.16 MB bundle with lazily loaded dialog chunks
- Hardcoded light-mode colours (`#fff3cd`, `#222`, `#b00020`); everything uses Nextcloud
  theme variables, so dark mode is correct

### Notes
- New UI strings are English only; the upstream `l10n/` catalogues are retained but no
  longer cover the rebuilt views

## [1.8.2] - 2026-08-01

### Fixed
- SMART power-on-hours reported the next attribute row's ID instead of the raw value
  (`\s` spanned newlines) — `/dev/sda` read as 10 h against a true 60404 h. ATA temp
  and hours patterns are now line-anchored; added SCSI hours fallback
- Host → Top processes returned nonsense keys: `ps aux` output (~110 KB / 792 procs)
  exceeded the truncation cap and `_run` kept the tail, discarding the header row and
  the highest-CPU entries. Fixed `-o` columns, `--no-headers`, and head-side truncation
- SMART NAS mounts always rendered red "down" — rows carried no reachability flag;
  sidecar now emits `ok` and a flat `fstype`
- Host → Package updates showed a blank Version column (`new_version` vs `version`)
- GPU process list showed no memory (`used_memory_mib` vs `used_memory`)

### Changed
- `_run` takes `keep="head"|"tail"` so listings sorted most-important-first survive truncation

## [1.8.1] - 2026-08-01

### Fixed
- Ops Containers table crash when `ports` is a string (fmtPorts)
- Docker engine chips empty — unwrap `{info:{…}}` payload
- GPU power column uses `power_draw_w`; Host iface chips format address objects
- GPU fan helper via host python3 + nsenter (pynvml on host)
- ATA SMART temperature parse; package temp prefers x86_pkg_temp / skips 0°C noise
- Log follow uses tail-only poll (no duplicate since-append)

### Changed
- Selective Ops refresh: fan form / backup button not fully rebuilt every 12s
- Volume and network Inspect buttons; event times localized
- Align sidecar default CONTAINER_ALLOW / IMAGE_PULL_ALLOW with compose

## [1.8.0] - 2026-08-01

### Added
- **Host** tab — mounts, package updates, top processes, systemd allowlisted restart, cron RO, network glance
- Portainer day-ops close: docker info/df/events, images list+pull, volumes/networks RO, live log follow (2s poll), redacted inspect, allowlisted kill/recreate/exec
- Stack restart / pull / rebuild on pinned compose dirs (incl. nc-tower, nc-print, ollama)
- Backup **run now** via allowlisted `/ops/bin/webmin/backup-enhanced.sh`; CRITICAL inbox surface
- Chassis fan RO; richer host summary (CPU%, temp, swap, ifaces, unhealthy containers); SMART model/temp/hours + NAS
- Sidecar audit log volume; `docs/plans/control-tower-standalone.md`

### Changed
- Sidecar privileged host agent with device/sysfs mounts for GPU/SMART
- Default container allow includes sitl/simcam/adsb patterns; optional RO-log tier
- CAPABILITY_MATRIX rewritten with Webmin + Portainer disposition tables
- Version jump 1.5 → 1.8 covers Portainer parity + Webmin custom close + Host hybrid

### Security
- Rotated sidecar token off `changeme`; PHP default empty (fail closed); compose loads `sidecar/.env`
- Deny-first allowlists unchanged for `cloud_*` / sidecar / portainer / openclaw
- Explicit never: host shell, system/volume prune, unrestricted docker mutate
- Removed leftover `docker.sock` RO mount from host `cloud` compose (`cloud_app`) — Docker only via sidecar

## [1.5.0] - 2026-07-27

### Added
- **Ops** tab — host disks, GPU, SMART, GPU fan, containers (stats/ports/logs), per-file stacks, backup summary, ops inbox
- **Tools** tab — full deep-link set (Portainer, Webmin modules, Kuma, Caddy, Guac, WebODM, Orca, ADSB, MediaMTX, NC); WireGuard → NC WireGuard app note
- Sidecar mutators: allowlisted container start/stop/restart; pinned compose up/down; GPU fan set-auto / set-all-speeds (clamp ≥20%)
- Shared Apps|System|Users|Ops|Tools subnav
- docs/plans/control-tower-ops-ui.md

### Changed
- Sidecar `docker.sock` mounted read-write (sidecar only; `cloud_app` still sock-free)
- CAPABILITY_MATRIX synced for 1.5 UI + fan helper; VPN/Ollama marked N/A
- Dashboard widget title → Control Tower

### Security
- Container default allow `gcs_*` / `mavlink_gateway`; hard deny `cloud_*`, sidecar, portainer, wg-easy, talk_*, openclaw*
- Mutators require sidecar token + Nextcloud CSRF; refuse mutators if token empty

## [1.4.2] - 2026-07-27

### Fixed
- System tab forever-spinners: `/storage` no longer runs `du -sb` on the whole datadirectory (blocked sequential load of sqlinfo + systeminfo). Uses filesystem free/total only; `getFolderSize` also capped with `timeout 5`.

## [1.4.1] - 2026-07-27

### Fixed
- Forever loading spinner / empty Apps sidebar: `/usercount` no longer recursively walks every user home (`folderSize`) or JSON-encodes raw `IUser` objects — was hanging on large Nextcloud datadirs (~126 users)

## [1.4.0] - 2026-07-27

### Added
- Rebrand as **Control Tower** (`nc_tower`) — fork of Admin Cockpit 1.3.2
- CREDITS.md + README attribution / fork lineage
- Read-only sidecar (containers, stacks, host summary, ops inbox)
- TowerController proxy routes + Tools deep-links
- Makefile ship / gate-preflight (nc-print style)

### Changed
- Admin-only page controllers (removed NoAdminRequired)
- CSRF required again on notify user/group
- Dual authors in info.xml (Wolfgang Tödt + Sarge)

### Security
- No docker.sock in Nextcloud PHP; sidecar-only Docker access

## 1.3.2

### Fixed
- Undefined array key 'model1' for some systems ([#16](https://github.com/zomtec2311/admincockpit/issues/16)) @ggwashburn

## 1.3.1

### Changed
- swedish language files new translated by @Leffe64

### Fixed
- bug in editing users for Nextcloud > 32

## 1.3.0

### Added
- Nextcloud 34 compatibility
- display current version at dashboard widget

## 1.2.9

### Fixed
- too long GET request for large number of user accounts ([#12](https://github.com/zomtec2311/admincockpit/issues/12)) @ArmelClo

## 1.2.8

### Added
- checks if direct Nextcloud update is allowed and webupdater is enabled
- direct update possible if allowed

## 1.2.7

### Changed
- view of dashboard widget
- update language files

### Fixed
- getAppInfo returns null  ([#11](https://github.com/zomtec2311/admincockpit/issues/11)) @manymane

## 1.2.6

### Fixed
- Dashbord Widget bug fixed

## 1.2.5

### Changed
- LogCleaner box due to LogCleaner changes

### Added
- Dashboard widget displaying available nextcloud and app updates

## 1.2.3

### Fixed
- some code cleanup due to deprecated methods

## 1.2.2

### Added
-new functions for some information boxes

### Fixed
- some code cleanup

## 1.2.1

### Added
- Information about additional functions


## 1.2.0

### Added
- Information about additional functions

### Fixed
- **l10n:** Correction of Czech translations  ([#9](https://github.com/zomtec2311/admincockpit/issues/9)) @onacilam

### Added
- Information about type of Nextcloud update channel

### Changed
- some css cleanups
- update language files

## 1.1.8

### Fixed
- displayed number of cpu threads was wrong ([#8](https://github.com/zomtec2311/admincockpit/issues/8)) @onacilam

### Added
- new function displaying network informations

### Changed
- update language files

## 1.1.7

### Added
- informations about logfile

### Changed
- update language files

### Fixed
- Additional settings error ([#7](https://github.com/zomtec2311/admincockpit/issues/7)) @onacilam

## 1.1.6

### Added
- New function to detect the type of web server and a possible proxy server

### Changed
- update language files

### Fixed
- some css cleanups

## 1.1.5

### Fixed
- added 'nowrap' to some containers within css file because of unwanted line breaks

### Added
- New function to detect the nextcloud installation method (local, docker etc.)

## 1.1.4

### Added
- loading-spinner appears in navigation as long as it checks for app updates

### Changed
- **l10n:** Correction of Czech translations  ([#5](https://github.com/zomtec2311/admincockpit/issues/5)) @onacilam
- **main.css** Changed width for boxes displaying long paths or words ([#6](https://github.com/zomtec2311/admincockpit/issues/6)) @onacilam

## 1.1.3

### Fixed
- Bugs fixed in "overview" and "system" while deleting duplicates from logfile

## 1.1.2

### Changed
- new features for overview and system

### Fixed
- some code cleanup

## 1.1.1

### Changed
- **l10n:** Critical correction of Russian translations ([#3](https://github.com/zomtec2311/admincockpit/pull/3)) and ([#4](https://github.com/zomtec2311/admincockpit/pull/4)) @drsmoll
- **l10n:** Critical correction of Czech translations  ([#1](https://github.com/zomtec2311/admincockpit/issues/2)) @onacilam

## 1.1.0

### Fixed
- Bug fixed for apps list in Nextcloud 31.x

## 1.0.9

### Fixed
- Bug fixed sending notifications

## 1.0.8

### Fixed
- deprecated method getInstalledApps() exchanged for getEnabledApps()
- check only enabled apps for upgrades

### Added
- LogCleaner integration if installed

## 1.0.7

### Changed
- update language files

### Fixed
- some code changes

## 1.0.6

### Added
- Nextcloud 33 compatibility

## 1.0.5

### Fixed
- Some bugs fixed

### Added
- send notifications to group members

## 1.0.4

### Added
- send notifications to users

## 1.0.3

### Added
- Update button for Apps if update available

## 1.0.2

### Fixed
- fixed undefined array key warnings

### Changed
- App update view

## 1.0.1

### Changed
- **l10n:** Critical correction of French translations  ([#1](https://github.com/zomtec2311/admincockpit/pull/1)) @Jerome-Herbinet

## 1.0.0

### Release
