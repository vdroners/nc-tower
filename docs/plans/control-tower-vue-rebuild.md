# Control Tower 1.9 — Vue rebuild (all seven tabs)

Plan-First artifact for the UI rebuild. Supersedes the hand-rolled `js/nc_tower-ops.js`
UI and the four prebuilt Admin Cockpit bundles.

## Why

The 1.8 UI works but is structurally wrong in four ways:

1. **The render loop fights itself.** `loadTick()` fires 13 concurrent calls every 12 s and
   every `setBody()` replaces `innerHTML`, destroying scroll position, selection and ~300
   container buttons per tick. `soft` flags were bolted on to stop forms being clobbered —
   the architecture conceding defeat. The same tick re-runs `smartctl -a` across five
   physical disks every 12 s.
2. **No hierarchy, no severity.** Ops is 13 equal-weight cards. Unhealthy containers are a
   muted `<p>`; the CRITICAL inbox is the last card on the page. Disks at 2 % and 98 %
   render identically. Nothing answers "is this host OK" above the fold.
3. **Two visual languages.** Ops/Host/Tools are hand-rolled CSS with hardcoded light-mode
   values (`#fff3cd`, `#222`, `#b00020`) that break in dark theme; Home/Apps/System/Users
   are prebuilt Admin Cockpit bundles with their own look. One subnav stitches them.
4. **14 MB of dead JS.** `nc_tower-{main,apps,system,user}.js` are 3.5 MB minified bundles
   each, with no source in this repo. Every admin page load ships 3.5 MB.

## Scope

**In:** all seven tabs (Home, Apps, System, Users, Ops, Host, Tools) plus the dashboard
widget, rebuilt as Vue 2.7 + `@nextcloud/vue` components against the existing PHP and
sidecar APIs. No backend route changes.

**Out:** any change to the sidecar security model — allowlists, token, CSRF, audit and the
never-list (no host shell, no prune, no `docker.sock` in `cloud_app`) are untouched.

## Toolchain

Matches nc_gcs so there is one house standard: Vue `2.7.16`, `@nextcloud/vue ^8`,
`@nextcloud/webpack-vue-config ^7`, `@nextcloud/axios`, `@nextcloud/router`,
`@nextcloud/dialogs ^7`, webpack 5, sass. `make build` becomes `npm ci && npm run build`;
the "prebuilt assets — nothing to compile" shortcut goes away.

## Architecture

Seven PHP routes stay exactly as they are — deep links and hard refresh keep working, and
the existing route gates keep passing. Each template renders one mount point:

```php
<div id="nc_tower" data-page="ops"></div>
```

A single bundle (`js/nc_tower-app.js`) mounts on every page and selects its view from
`data-page`. Navigation items are plain anchors to the PHP routes, so no vue-router and no
catch-all route is needed; the bundle is cached across tabs.

```
src/
  main.js                  mount + view selection
  App.vue                  NcContent > NcAppNavigation + NcAppContent
  views/                   Home Apps System Users Ops Host Tools
  components/              StatusBanner AttentionList Section DataTable
                           ContainerActions LogDialog ExecDialog InspectDialog
                           ConfirmDialog UsageBar SeverityDot Chip
  services/api.js          axios + generateUrl + normalized errors
  services/poll.js         tiered polling, pauses on hidden tab
  services/health.js       triage rules (below)
```

## Ops — status-first triage

The landing state answers one question. A verdict banner (OK / ATTENTION / CRITICAL) over
an attention list; every detail section below is collapsed to a one-line summary.

Triage rules in `services/health.js`, each producing a severity and a human sentence:

| Signal | Warn | Critical |
|---|---|---|
| Unhealthy containers | — | any |
| Container exited | any | — |
| Disk `used_pct` | > 85 | > 95 |
| SMART health | not `PASS` | `FAIL` |
| SMART power-on hours | > 43 800 (5 y) | > 61 320 (7 y) |
| SMART / package temp | > 55 °C | > 65 °C |
| GPU temp | > 80 °C | > 90 °C |
| Ops inbox | any `warn` | any `crit` |
| Backup age | stale > 26 h | — |
| Package updates | any | — |

The power-on-hours rule only became possible in 1.8.2 — before that fix `/dev/sda` reported
10 h against a true 60 404 h, so the drive that most needs flagging was invisible.

## Refresh

Per-section intervals replace the 12 s blanket tick, all paused while the tab is hidden,
each with a manual refresh:

containers 10 s · host 15 s · GPU 30 s · docker events 30 s · engine/df 60 s · chassis fan
60 s · inbox 60 s · images/volumes/networks 120 s · **SMART 300 s** · packages 300 s.

## Desktop and phone

`DataTable` renders a real table at ≥ 768 px and a stacked card list below it. Row actions
collapse into an `NcActions` overflow menu instead of six inline buttons. Dialogs go
full-screen on phone. `confirm()` / `prompt('Type RECREATE')` are replaced by `NcDialog`
with a typed-confirmation field — same safety gate, keyboard and touch friendly.

## Ported upstream tabs

No source exists for the bundles, so these are reimplemented over the current endpoints:

- **Apps** — `appsasc`, `appsinfo`, `appupdates`, `enableapp`, `disableapp`, `updateapp`, `isnoti`, `islogcleaner`
- **System** — `systeminfo`, `storage`, `sqlinfo`
- **Users** — `usercount`, `userexists`, `newuser`, `saveuser`, `edituser`, `deleteuser`, `notifyuser`, `notifygroup`, `addgroup`, `deletegroup`
- **Home** — overview composed from the above plus `tower/health`
- **Dashboard widget** — `widgetinfo`, rebuilt to match

The GET-verb mutators (`enableapp/{who}`, `deleteuser/{who}`) stay on GET for now — they are
admin-gated and CSRF-checked, and changing verbs is a separate backend change. Logged as
debt in the capability matrix, unchanged by this plan.

## Verification

Visual review is the author's (per this task's direction), so the automated gates carry the
weight. Existing 40 preflight + 44 API gates must keep passing, plus new ones:

- **G19 build** — `js/nc_tower-app.js` exists and `npm run build` exits 0
- **G20 payload shape** — preflight curls the sidecar and asserts the field names the UI
  actually reads: `host/proc` rows have `pid` + `command`, `host/smart` disks have a
  plausible `power_on_hours` (> 100 for a spinning disk), `host/packages` rows have
  `new_version`, `host/smart` `nas_mounts` carry `ok`. This is the class of defect that
  shipped in 1.8.1 while every route gate passed.
- **G21 admin gating** — no active `#[NoAdminRequired]` anywhere in `lib/Controller/`,
  not just `PageController` (admin-gating is by omission, so a single stray attribute
  would expose host mutators)
- **G22 dead weight** — the four 3.5 MB bundles are gone from `js/`

Then `make ship RESTART=1`, confirm `occ` reports 1.9.0, and confirm no container crashed.

## Sequence

1. Toolchain + app shell + navigation (bundle builds, all seven routes mount)
2. Ops status-first + Host + Tools
3. Apps + System + Users + Home + widget; delete the prebuilt bundles
4. Gates, `make ship`, version 1.9.0

Waves 1–2 are shippable on their own: until wave 3 lands, the four upstream tabs keep their
existing bundles, so the app is never broken mid-rebuild.
