# NC Tower 1.16.0 — verification result + fix/improve plan

## Context

Full read-only verification of the deployed 1.16.0 (five parallel inspectors + adversarial
adjudication of every claimed defect). Health baseline is genuinely good and should be
stated plainly:

- **All shipped checks pass**: preflight 86/86, in-container api-gates 86/86, route-gates
  22/22, vitest 69/69, template-refs OK.
- **Deployed tree == repo, bit-for-bit** (js bundle, sidecar, controllers md5-identical),
  and the **running sidecar is current** — the container's `/app/app.py` md5 matches
  `git show 680ed16:sidecar/app.py`, so despite later file mtimes it is not stale.
- Zero `nc_tower` errors in the Nextcloud log; sidecar clean; job queue idle-clean; 9/10
  services up (only OrcaSlicer down, correctly shown).

So nothing is broken at the plumbing level. What the audit found is **data the UI displays
that is wrong or misleading** — every field-name/namespace contract that drifted as
surfaces were added in 1.12–1.16. All 12 defects below were adversarially reproduced live;
none were refuted.

## Confirmed defects, grouped by root cause

### P0 — a degrading drive is invisible (fix first, regardless of the rest)
- **SMART sector counters are dropped.** `/dev/sda` reports **Reallocated_Sector_Ct = 1072**
  right now (confirmed via `/host/smart/attributes`), but `host_smart()`
  (`sidecar/app.py` ~617) emits only device/health/model/temp_c/power_on_hours/smartctl_exit.
  The health-rule sector gate (`src/services/health.js:117`) and the Ops SMART-trend
  Realloc/Pending columns are therefore dead. **The one thing this app exists to catch is
  silently unmonitored.** Fix: emit reallocated/pending/uncorrectable from `host_smart()`
  and `_smart_trend_disks`; the health rule already consumes them.

### Field-name contract drift (pure UI-vs-sidecar key mismatches — unambiguous, no decision)
- **GPU per-fan rows never render.** `FanPanel.vue:191` reads `status.fans || status.Fans`;
  sidecar `/host/fan` emits `status.gpu_fans` (confirmed: 2 fans). Set-speed controls dead.
- **NIC link chip always warns.** `Ops.vue:560` reads `nic.link`; sidecar emits
  `link_detected` → every NIC chip styled warn even when up.
- **Container Inspect summary is all dashes.** `docker inspect` returns an array;
  `formatInspectSummary` (`Ops.vue:1816`) reads `.Config/.State` off the array instead of
  `[0]`. Header always dashes (raw JSON below it is fine).
- **Temperatures 24 h chart plots 1970.** `HostInventoryPanels.vue:357` does
  `new Date(row.ts)` but `/host/temperatures/history` emits `ts` as epoch **seconds**
  (`/host/history` emits ISO — inconsistent contract). Multiply by 1000 or normalise the
  endpoint.
- **Ops/Widget verdict can never show app updates.** `Ops.vue:1386` polls `/appupdates`,
  a hard-coded stub (`{available:false, appscount:0}`). Home already uses the OCS path
  (`listAppUpdates`). Point Ops at the same source.

### Namespace / tooling cluster (sidecar reads its own namespace, not the host's)
- **Network depth shows the sidecar container, not the host.** Routes/interfaces/listeners
  on `/host/network` are the Docker-bridge view (`inventory.py` `_host_cmd` enters only
  `--mount`, never `--net`); host has 73 ifaces, panel shows `lo`+`eth0`.
- **`hardware.os.hostname` is the container id** (`46a5c28cbf4c`) — `_host_cmd` lacks
  `--uts`.
- **All interface Addresses columns are empty** — the sidecar image has no `ip` binary, so
  `_interfaces()` falls back to `/sys/class/net` and hard-codes `addresses:[]`.
- **NIC firmware/bus_info capture the next line** — `parse_ethtool_i`
  (`inventory.py:224`) uses `\s*` which crosses newlines on empty values (same bug class as
  the 1.8.2 SMART regex).

### Packaging
- **App Store tarball is not installable.** `make appstore` roots the archive at
  `nc_tower-<version>/`; Nextcloud requires the single top folder to be exactly `nc_tower`.
- Lab defaults still ship in sidecar source (`OLLAMA_URL=10.0.0.84`, `CONTAINER_ALLOW=gcs_*`,
  `SYSTEMD_USER=vdroners`) despite 1.12.0's neutralization claim.

### Security hardening (notes — all contained, none exploitable as shipped)
- Cron-editor "reject shell metacharacters" guard only rejects NUL (cosmetic).
- `container_exec` denylist is basename-only; `python3 -c` bypasses it (contained by the
  container boundary + allowlist; matches the documented design, but the UI copy overclaims).
- `X-Ops-Token` compared with `!=` not `hmac.compare_digest` (localhost-bound; low).

## UI/UX improvements (ranked by operator value; all reuse existing components)

1. **Ops is a 16-section scroll wall with no in-page nav, and its anchors are dead**
   (`Section.vue` root has no `id`, so `href="#ops.engine"` targets nothing). Add a sticky
   jump-bar of section chips with Severity dots; give `Section` an `id`.
2. **Sidecar-down floods ~25 duplicate 502 errors** across Ops/Host sections. Add the
   page-level banner Home already has; suppress per-section repeats of one root cause.
3. **First load flashes "No containers / No users / No disks"** — `DataTable` has no loading
   state. Add a `loading` prop → "Loading…" row.
4. **Home puts the sidecar-down / API-down notices last**, below the chart. Move them
   directly under the StatusBanner (above the fold on phones).
5. **Host leads with reference hardware inventory**; day-ops (Updates, Services) sit below.
   Reorder Updates + Services first; drop `default-open` on Hardware.
6. **FanPanel still uses `window.confirm()`** — the only surface not on `ConfirmDialog`.
7. **Phone (<720 px) hides the Section summary entirely** (`Section.vue:178`), removing the
   per-section verdict that the whole design leans on; and `DataTable` drops its only sort
   UI (thead) with no replacement. Wrap the summary instead of hiding; add a compact sort
   control in card mode.
8. **Chip modifier classes are scoped per-component**, so `Ops.vue`'s NIC `--ok/--warn`
   chips never actually colour (the class lives only in HostInventoryPanels/FanPanel scope);
   plus a `tower-bad` typo. Promote chip modifiers to the global stylesheet.
9. **Chart-vs-number rebalance**: mem/swap as text while disks get UsageBars (add bars);
   Docker df rendered as *both* a chart and a table (drop the chart, add a reclaimable bar);
   GPU temp a bare number (give it the container-CPU Sparkline treatment).
10. **"Is everything up to date?" spans three tabs** with apt duplicated in Host›Updates and
    Ops›Packages. Make Home's card a combined apt+apps+core rollup; one canonical apt home.
11. **Container Stats/SMART-attr panels render after all groups**, hundreds of px from the
    click — looks like nothing happened. Make them inline expandable rows or reuse
    OutputDialog.
12. **Dialog/widget a11y**: autofocus ConfirmDialog's phrase field; OutputDialog's Copy
    emits events no caller handles (silent); add `role=progressbar`/`aria-valuenow` and a
    non-colour cue to UsageBar.

## Sequencing — decided: everything in one pass, ship as 1.17.0

All four waves land together. Order of execution (each verified before the next so a
regression is caught close to its cause):

- **Wave 1 — correctness:** SMART sectors (P0) + the five field-name mismatches + the
  ethtool regex. Add a vitest/gate case per fix so the contract can't silently drift again
  — this is the exact class the estate keeps re-hitting, so each gets a regression test.
- **Wave 2 — namespace/tooling (decided: fix properly):** add `iproute2` to the sidecar
  image (`sidecar/Dockerfile`) and make `_host_cmd` / `_interfaces` enter the host **net +
  UTS** namespaces (`nsenter --target 1 --net --uts --mount`, or per-call `-n`/`-u`) so
  Network depth, Addresses and `hostname` show real host data.
  **Operational caveats:**
  1. This requires rebuilding the sidecar image and recreating the privileged
     `nc_tower_sidecar` container. That recreate must be run from the **host shell**
     (`docker compose -f sidecar/docker-compose.yml up -d --build`), never through Tower —
     same self-restart trap as the apt-upgrade job. It briefly interrupts host/Docker
     telemetry; the PHP app and Nextcloud are unaffected.
  2. Entering the host net namespace changes what `services/probe` and any bind-to-127.0.0.1
     assumptions see — re-verify the probe and `/health` reachability after recreate.
- **Wave 3 — UI/UX:** improvements 1–12, biggest-value first (jump-nav + live Section
  anchors, single sidecar-down banner, DataTable loading state, phone summary wrap,
  Host/Home hierarchy reorders, FanPanel → ConfirmDialog, global chip classes, chart-vs-
  number rebalance, updates rollup, inline stats panels, dialog a11y).
- **Wave 4 — packaging + hardening (decided: yes, App Store is a goal):**
  - Fix `make appstore` so the tarball's single top folder is exactly `nc_tower`.
  - **Neutralize without breaking the live box:** move the lab values
    (`OLLAMA_URL`, `CONTAINER_ALLOW=gcs_*`, `SYSTEMD_USER=vdroners`, service-probe IPs) out
    of the `sidecar/app.py` source defaults and into this deployment's compose env / `.env`
    (lab-local, gitignored), leaving neutral defaults in source. Verify the running sidecar
    still resolves the same values from env after the change, so behaviour here is unchanged.
  - Fold in the contained hardening notes while in the sidecar: real cron-metachar guard,
    `hmac.compare_digest` for the token, and correct the Ops exec-dialog copy that overclaims
    the denylist.
  - Add a preflight gate asserting the tarball top-folder name and that source defaults carry
    no lab-specific IPs/allowlists (so neutralization can't silently regress).

Single release, single version bump to **1.17.0**, one plan already checked in at
`docs/plans/` per the repo's Plan-First rule, README + CHANGELOG updated, gates + tests green
before commit/push.

## Verification per wave
Re-run the same five checks (preflight, api-gates, route-gates, vitest, check-template-refs)
plus a live curl of each fixed endpoint; for SMART, assert the summary now carries the
sector counts and that health.js flags `/dev/sda`. Deploy, confirm no container crashed.
Visual review stays the author's — no authenticated browser session here.

## Key files
- Correctness: `sidecar/app.py` (`host_smart`, `_smart_trend_disks`, `_interfaces`),
  `src/components/FanPanel.vue`, `src/views/Ops.vue`, `src/components/HostInventoryPanels.vue`,
  `lib/Controller/AppsController.php` / `src/views/Ops.vue` (app-updates source),
  `sidecar/inventory.py` (`_host_cmd`, `parse_ethtool_i`).
- UI: `src/components/{Section,DataTable,ConfirmDialog,OutputDialog,UsageBar}.vue`,
  `src/views/{Home,Host,Ops}.vue`, `src/App.vue` (global chip classes).
- Packaging: `Makefile` (appstore target), `sidecar/app.py` (env defaults).
