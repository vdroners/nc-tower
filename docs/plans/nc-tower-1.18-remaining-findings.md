# NC Tower — fix the remaining audit findings (post-1.17.0)

## Context

The 1.17.0 pass fixed all 12 confirmed defects and 9 of 12 UI improvements. This plan
proposes fixes for **everything the audit surfaced that is still open**: the audit's
"notes" that weren't actioned, plus the 3 deferred UI items. Re-verified against the
current `nc-tower-1.17.0` branch (four notes — cron guard, hmac token, exec-copy, lab
neutralization — were already fixed in 1.17.0 and are excluded here).

Investigating note #5 turned up something bigger than a note, so it leads.

**Decisions locked with the user:** explicit `isAdmin()` guard for P0; all four scope groups
(P0 security, P1 correctness+cleanup, P2 compat, P3 deferred UI) are in; dead routes were
assessed individually (see P1) — 5 discarded as upstream relics, `/isnoti` kept (in use),
`/tower/chassis-fan/history` implemented as a sparkline. Ship as one minor bump (**1.18.0**).

## P0 — Admin enforcement is not what the code implies (security)

**Finding.** Modern Nextcloud (verified in the running NC 34 `SecurityMiddleware`) enforces
admin **only** via `#[AuthorizedAdminSetting]` / `SubAdminRequired`; a controller method with
no such attribute is reachable by **any logged-in user**. The old "admin by omission" model
(absence of `@NoAdminRequired` ⇒ admin) is not how NC 34 behaves.

In nc_tower:
- `#[AdminRequired]` (used on AppsController/UserController) **does not exist** as an OCP
  attribute — the container has `NoAdminRequired`, `SubAdminRequired`,
  `AuthorizedAdminSetting`, but no `AdminRequired`. It is inert, and it gives a reviewer
  false confidence that these endpoints are admin-gated per method.
- **`TowerController` — the host-root sidecar proxy — has no admin attribute at all** (GETs
  carry `#[NoCSRFRequired]`; POST mutators carry nothing).
- The only actual admin gate is `enableAppForGroups(self::APP_ID, ['admin'])` in
  `Application.boot()`. That likely blocks non-admins today (the app isn't enabled for their
  groups), but it is a fragile, implicit, whole-app gate: `occ app:enable nc_tower` without
  `--groups`, an added group, or the App-Store install path widens it silently, and nothing
  per-endpoint stops a logged-in non-admin from `POST /tower/containers/x/kill`.

**Fix.** Enforce admin explicitly on every privileged controller method, mirroring the
estate pattern (`nc_gcs` EquipmentController uses `$this->groupManager->isAdmin($userId)`):

- Add a small shared guard — a base controller or a one-line
  `if (!$this->groupManager->isAdmin($uid)) throw new OCSForbiddenException()` / 403
  `JSONResponse` — invoked at the top of every mutating and data method in
  `TowerController`, `AppsController`, `UserController`, `GroupController`, `SystemController`.
- Remove the inert `#[AdminRequired]` imports/attributes (note #5) as part of the rework, so
  the only admin signal in the code is the one that actually runs.
- Keep `enableAppForGroups(['admin'])` as defence-in-depth.
- **New gate G35 (or extend G21):** statically assert every route in `appinfo/routes.php`
  maps to a controller method that either calls the admin guard or is on an explicit
  public-allowlist (`page#index` etc.). Negative-test it (drop a guard → gate fails).

I could not prove a non-admin can reach these today (the group-enable may fully block it),
so this is framed as correctness + defence-in-depth on a host-root surface — but the current
enforcement being implicit and the attributes being inert is not acceptable for what this
app can do.

## P1 — Data correctness (small, server-verifiable)

- **Posture "Logged in" From column** (note #3): `collect_posture` in `sidecar/inventory.py`
  parses `who` with `parts[4]`, so `(login screen)` renders as `(login`. Join `parts[4:]`
  (or capture the trailing `(...)`).
- **Watched-path mount labeling** (note #4): `/host/mounts` `interesting` shows the
  container's overlay for `/` (device/fs = `overlay`) though the usage numbers are
  host-correct. Resolve the mount row from the host mount table (read via the host mount
  namespace, consistent with 1.17.0's `_host_cmd`) or drop the container-scoped device/FS
  cells for `/`.

## P1 — Dead-code / dead-surface cleanup (safe, verifiable)

- **Helper.php stray attributes** (note #6): `#[NoCSRFRequired]` + `#[FrontpageRoute(POST,
  '/')]` sit on `Helper`'s constructor — a non-routed class. Remove them (the stray
  `FrontpageRoute` is also a phantom POST-`/` route waiting to surprise someone).
- **`docker_image_remove` unreachable `elif`** (note #12): the second branch is subsumed by
  the first. Simplify.
- **Dead routes** (note #2) — assessed each for intent (git provenance + method body +
  caller check):
  - **Discard — upstream Admin Cockpit relics, 0 callers:** `/appsasc` (`listCategories`,
    now a stub returning `[]`), `/updateapp/{who}` (stub returning 501 "use OCS"),
    `/islogcleaner`, `/widgetinfo` (superseded by the Vue widget's own `/tower/*` fetches),
    and `/userlist` GET+POST (legacy server-rendered page — also drop `templates/userlist.php`
    and the `PageController::userlist*` methods). All trace to upstream "Add files via upload"
    / zomtec2311 commits, not NC Tower features.
  - **Keep:** `/isnoti` is **not** dead — `Users.vue:240` calls it to gate the Notify action.
    (The audit correctly did not list it; included here only to record the check.)
  - **Implement — genuine unfinished NC Tower feature:** `/tower/chassis-fan/history`
    returns real data (120 live samples over 60 min) but nothing consumes it. It is the
    remnant of the fan-history UI that **1.14.1 pulled for chart clipping**. Wire it as a
    minimal `Sparkline` (see P3), explicitly not the `FanCharts`/gauges that were removed.

## P2 — Compatibility (note #11)

`appstoreOcs.js` calls the `appstore` OCS API, which exists only on NC ≥ 34, but
`info.xml` declares `min-version="31"`. On 31–33 the Apps-update listing fails (surfaced,
not fatal). Either bump `min-version` to 34, or guard the OCS call so pre-34 shows a plain
"update check needs NC 34+" instead of an error.

## P3 — Deferred UI (needs a browser to verify)

The three 1.17.0 deferrals, all reusing existing components:
- Mem/swap **UsageBars** in the Ops "Host and storage" chips.
- **GPU-temp sparkline** (in-memory ring buffer like container CPU), and a **chassis-fan
  history sparkline** fed by the live `/tower/chassis-fan/history` endpoint — a plain
  `Sparkline`, not the `FanCharts` gauges 1.14.1 removed for clipping.
- Container **Stats** / SMART-attr panels rendered **inline** under the clicked row instead
  of appended after all groups.

I still have no authenticated browser session, so these ship unverified beyond build +
template-ref check unless you log one in.

## Critical files
- Admin guard: new `lib/Controller/AdminGuardTrait.php` (or base controller);
  `lib/Controller/{Tower,Apps,User,Group,System}Controller.php`; `tools/tower-api-gates.php`
  (G35).
- Correctness: `sidecar/inventory.py` (`collect_posture`), `sidecar/app.py` /
  `src/views/Host.vue` (mount labeling).
- Cleanup: `lib/Controller/Helper.php`, `sidecar/app.py` (`docker_image_remove`),
  `appinfo/routes.php` (+ controller methods for dropped routes).
- Compat: `appinfo/info.xml` or `src/services/appstoreOcs.js`.
- UI: `src/views/Ops.vue`, `src/components/{Sparkline,UsageBar}.vue`.

## Verification
- Re-run the five gates (preflight, api-gates, route-gates, vitest, check-template-refs),
  all currently green at 88/86/22/72 + 27 sidecar unit tests.
- **P0:** new G35 passes and fails when a guard is removed; live-curl a privileged
  endpoint and confirm the guard path (as admin: 200; the negative non-admin case noted for
  a manual check since it needs a second session).
- **P1:** live `/host/posture` shows `(login screen)`; `/host/mounts` `/` row shows the host
  device/fs (or no misleading cell).
- Recreate the sidecar from the host shell for `inventory.py`/`app.py` changes (single-file
  bind-mount inode gotcha); deploy the app; confirm no container crashed.
- Ship as a single version bump; check the plan into `docs/plans/`, update CHANGELOG/README.
