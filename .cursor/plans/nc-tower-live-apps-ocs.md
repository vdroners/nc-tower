# NC Tower 1.13.0 — live Apps + honesty pass

## Why

Apps Updates banner was an honest OCP stub, but operators also saw empty Enabled/Disabled lists when `/appsinfo` CSRF/listing was fragile. Cross-tab honesty bugs (false Widget “All clear”, shared System errors blanking the tab, quota/password save, etc.) needed the same cut.

## What changed

1. **Read GETs** on Apps/System/User controllers: `#[AdminRequired]` + `#[NoCSRFRequired]`. Mutators keep CSRF.
2. **`appsinfo`**: enable/disable lists first; settings sections in try/catch; `array_values()`; disable uses `isEnabledForAnyone()`.
3. **Live store updates** via `src/services/appstoreOcs.js` (appstore OCS list + update + password confirmation). No `OC\Installer` in Tower PHP.
4. **Honesty**: Widget load tracking; System per-endpoint errors + Section partial render; `saveuser` quota/`setPassword`; Home NC API banner; Ops `mutate` requires `ok === true`; Users Notify gated on `/isnoti`; widget chrome → Ops.

## Verify

- `GET /apps/nc_tower/appsinfo` → 200 with enabled rows
- Appstore OCS drives Updates table (or honest empty/unavailable note)
- Enable/disable still via Tower + CSRF
- Widget with sidecar stopped → not “All clear”
- System with one endpoint failing → other sections still render
- No `OC\Installer` / `VersionCheck` imports in Tower PHP
