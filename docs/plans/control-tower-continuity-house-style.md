# Control Tower — continuity and house-style alignment

## Context

Control Tower reached 1.9.2 through a fast rebuild: the whole front end was replaced with
Vue in 1.9.0, then patched twice for defects. That rebuild was done against the app's own
backend in isolation and never compared against the other Nextcloud apps in this estate
(nc_gcs, nc-print, nc-roomba, nc-litter, nc-wireguard). It also inherited routing from the
pre-Vue era without re-checking that every button still reaches its handler.

This pass is an end-to-end continuity test of front end against backend, plus an alignment
check of theming, iconography and naming against the sibling apps. It found one genuinely
broken feature, one regression, and a set of consistency gaps.

## What the continuity test found

**Verified against the live Nextcloud router**, not by reading code:

| # | Finding | Status |
|---|---|---|
| C1 | **Container Exec and Recreate are broken.** `/tower/containers/{name}/{action}` is registered before the specific `/exec` and `/recreate` routes, so Symfony matches the generic one first. `containerAction()` then rejects anything outside `start\|stop\|restart\|kill` with HTTP 400. Both are advertised as working in README and CAPABILITY_MATRIX | **P0 bug** |
| C2 | `tower#stackUp` / `tower#stackDown` are shadowed by `tower#stackAction`. Harmless — same semantics — but dead aliases | Cleanup |
| C3 | Backend surface the front end never calls: `/appsasc`, `/isnoti`, `/islogcleaner`, `/widgetinfo`, `/tower/health` | Leave dormant, document |
| C4 | **The Users tab lost user editing in the 1.9.0 rebuild.** `edituser`, `saveuser` and `userexists` still exist in PHP with no UI | Regression → restore |

Proof for C1: loading the real route collection inside `cloud_app` and matching each
contested URL resolves `POST …/exec` to `containeraction action=exec`, which 400s.

## What the style comparison found

House convention, set by `nc_gcs` and followed by `nc-print`:

- **Icons are a per-app inline-SVG registry component** — `GcsIcon.vue` (64 call sites),
  `NcPrintIcon.vue` (26). Tabler-derived paths, 24×24 viewBox, `fill="none"`,
  `stroke="currentColor"`, stroke-width 2, round caps, `props: { name, size=16 }`, registry
  lookup with an empty/dot fallback. **No icon library is used anywhere in the estate**, so
  adding `@mdi` would itself be off-convention.
- **CSS classes prefixed `nc-<app>-`** — `nc-print-`, `nc-roomba-`, `nc-litter-`, `nc-wg-`.
- **Each app has its own branded `img/app.svg`.**
- **Tests are vitest + happy-dom**, specs under `src/__tests__/`, `"test": "vitest run"`.

Control Tower diverges:

| # | Finding |
|---|---|
| S1 | **No icon component — Unicode glyphs stand in for icons**: `◎` brand, `▾ ▸` disclosure, `↻` refresh, `▲ ▼` sort, `→` link. Nine sites across `App.vue`, `Section.vue`, `DataTable.vue`, `Ops.vue`, `Host.vue`, `Widget.vue`. Glyphs ignore stroke weight and render per-platform font |
| S2 | **Class prefix is `tower-`, not `nc-tower-`** — the only app in the family off-pattern (~115 usages) |
| S3 | **Nav icon never rebranded** — `img/app.svg` is still upstream Admin Cockpit's generic window glyph |
| S4 | Dead upstream assets: `img/infoLogCleaner.png` (unreferenced) and `img/app-dark.svg` (only app carrying one). `img/dummy.svg` **is** still used by `AppsController` — keep it |
| S5 | No unit tests (nc_gcs 239, nc-print 63, nc-roomba 13, nc-tower 0) |

**Already aligned:** zero hardcoded colours (all Nextcloud theme variables), custom root div
with its own nav rather than `NcContent` nesting, `@nextcloud/vue` for controls.

## Fix plan

### P0 — restore Exec and Recreate (`appinfo/routes.php`)

Replace the catch-all with explicit verbs so nothing can shadow a sibling. Declare
`recreate` and `exec` first, then four literal routes (`start`, `stop`, `restart`, `kill`)
all pointing at `tower#containerAction`. Keep the allowlist check inside
`containerAction()` as defence in depth. Drop the shadowed `tower#stackUp` /
`tower#stackDown` aliases — `stackAction` already serves both and the front end only calls
`/tower/stacks/{action}`.

**New gate G25** in `tools/tower-api-gates.php`: load the route collection and assert each
contested URL resolves to its intended handler. Grepping `routes.php` cannot catch C1 —
only real route resolution can. Negative-test it by restoring the catch-all and confirming
the gate fires.

### P1 — icon system (`src/`)

Add `src/components/NcTowerIcon.vue` mirroring `NcPrintIcon.vue` exactly (same viewBox,
stroke settings, `{ name, size=16 }` props, registry lookup). Tabler-derived paths only.

Replace all nine glyph sites, then add icons where the family has them:

- **Nav tabs** (7): home, activity/pulse (Ops), server (Host), apps/grid, settings (System),
  users, external-link (Tools) — `nc_gcs` puts an icon on every tab.
- **Section header**: `chevron-right`/`chevron-down` for disclosure, `refresh` for reload.
- **Table**: `sort-asc`/`sort-desc` carets.
- **Row actions**: play, square (stop), refresh, x (kill), rotate (recreate), terminal
  (exec), file-text (logs), search (inspect) — these carry the most visual weight since
  every container and stack row shows them.

### P2 — naming (`src/`)

Rename `tower-*` → `nc-tower-*` across templates and scoped styles, including the root
`#nc-tower-root` children and the `nc_tower.section.*` localStorage keys' CSS counterparts.
Mechanical, no behaviour change, touches every `.vue` file. Do it in the same pass as P1 so
each file is edited once.

### P3 — restore the Users edit dialog (`src/views/Users.vue`)

Wire an edit dialog over the existing endpoints — `edituser/{who}` to load, `saveuser` to
persist, `userexists/{who}` for validation on create. Fields: display name, email, quota,
groups, admin membership. Reuse the existing `ConfirmDialog`/`NcDialog` pattern already in
the view; do not add new dialog machinery.

### Housekeeping

- New `img/app.svg`: a Control Tower mark (tower / radar sweep) in the family's stroke
  style, replacing upstream's window glyph. Delete `img/app-dark.svg` and
  `img/infoLogCleaner.png`. **Keep `img/dummy.svg`** — `AppsController` serves it for apps
  with no icon.
- Add vitest + happy-dom matching nc-print's setup (`vitest.config.cjs`,
  `"test": "vitest run"`, specs in `src/__tests__/`). Cover `src/services/health.js` first:
  each triage rule's threshold and severity ordering, the size parser, and `worst()`. These
  rules decide what an operator sees as critical and are currently untested. Add
  `format.js` cases while there.
- Leave C3's dormant routes in place; note them in `docs/CAPABILITY_MATRIX.md` so they are
  not mistaken for live surface.

Ship as **1.10.0** (behaviour change plus restored features). Check in a short plan under
`docs/plans/` per the repo's Plan-First rule, update README (icon convention, gate table
with G25) and CHANGELOG.

## Critical files

- `appinfo/routes.php` — P0 route ordering
- `tools/tower-api-gates.php` — G25 router-resolution gate
- `src/components/NcTowerIcon.vue` (new), modelled on `/media/4TB/nc-print/src/components/NcPrintIcon.vue`
- `src/App.vue`, `src/components/Section.vue`, `src/components/DataTable.vue` — glyphs and prefix
- `src/views/Ops.vue`, `Host.vue`, `Widget.vue` — glyphs, row-action icons, prefix
- `src/views/Users.vue` — edit dialog
- `img/app.svg` — rebrand
- `vitest.config.cjs` + `src/__tests__/health.spec.js` (new)

## Verification

1. `npm run build && npm run check:refs` — bundle builds, no undefined template refs.
2. `npm run test` — new vitest suite green.
3. `make gate-preflight` + in-container API gates — currently 64 + 58, plus G25.
4. **Router proof for C1**:
   ```bash
   docker exec -u www-data cloud_app php -r '…IRouter…match("/apps/nc_tower/tower/containers/x/exec")'
   # must report tower.containerexec, not tower.containeraction
   ```
5. **Live mutation proof**: exec `["ls","-la"]` in an allowlisted container (`gcs_*`) and
   confirm 200 with output rather than `400 invalid_action`. Recreate is riskier — test it
   against `gcs_simcam` only, and confirm the container returns healthy afterwards.
6. Style audits: `grep -rP '[▾▸▲▼◎↻→]' src/ --include=*.vue` and
   `grep -rc 'class="tower-' src/` both return nothing.
7. Deploy, confirm `occ` reports 1.10.0, and confirm no container crashed.

Visual review remains the author's — I still have no authenticated browser session, so
layout and icon rendering are unverified beyond the build and the audits above.
