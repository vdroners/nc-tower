# NC-Tower 1.12.0 — App Store readiness

**Version:** 1.11.0 → **1.12.0**  
**Date:** 2026-08-03  
**Goal:** Clear private-API / lab-IP disqualifiers so NC Tower can ship as a generic Nextcloud app (plus optional host sidecar).

## Why

App Store review rejects private `OC\*` / `OC_App` usage and lab-specific hardcoding (`10.0.0.84`, `/media/4TB`). This release removes those blockers, makes deep-links and sidecar paths admin-configurable with empty defaults, and adds packaging/CI expected of a store app.

## Scope

### 1. OCP rewrite (store disqualifier)

| Area | Action |
|---|---|
| `AppsController` | Drop `OC\Installer`, `OC\App\*`, `OC_App`. Keep enable/disable via `OCP\App\IAppManager`. Stub app-update / category routes as “not available — use Nextcloud Apps”. |
| `SystemController` + `MyService` | Drop `OC\Updater\VersionCheck`. Stub NC update check (`updateAvailable: false`) or read only public config. |
| `$_SERVER` | Replace with `OCP\IRequest` (`getHeader`, `server` via request). |

**Verify:** `rg 'use OC\\|\\\\OC::|OC_App|\\$_SERVER' lib/` → zero hits (except comments).

### 2. Configurable endpoints

- Move every Tools deep-link URL (Webmin, Portainer, Kuma, Caddy, Guac, WebODM, OrcaSlicer, ADSB, MediaMTX, Nextcloud, …) into **appconfig** with **empty defaults**.
- `TowerController::tools()` builds groups from config; omit tiles with empty URL.
- Admin Settings section to edit sidecar base URL + tool URLs.
- Sidecar base URL app setting default: `http://nc_tower_sidecar:18765` (Docker DNS), not a lab IP. Prefer appconfig over `config.php` system value (keep system-value fallback for existing lab installs).

### 3. Sidecar packaging

- Add `sidecar/Dockerfile` (`python:3.12-slim`, COPY `app.py`).
- Rename current lab compose → `sidecar/docker-compose.lab.yml`.
- Add generic `sidecar/docker-compose.yml` with env-driven mounts/allowlists (no `/media/4TB` defaults).
- Neutralize `sidecar/app.py` defaults: empty/env for compose dirs, disk paths, service targets, jobs dir.

### 4. Appstore + CI

- Port `make appstore` / `appstore-sign` from nc-print (no composer vendor required).
- `.github/workflows/ci.yml`: npm ci, eslint, vitest, build.
- `.github/workflows/release.yml`: build appstore tarball on published release.
- Fix Makefile `test` → `npm test` (vitest).
- Sync `package.json` / `package-lock.json` to **1.12.0**.

### 5. info.xml

- Version **1.12.0**
- Nested `<documentation><user>/<admin>`
- Screenshots via HTTPS `raw.githubusercontent.com` URLs (wire existing files; skip missing small thumb where absent)
- Privacy / sidecar disclosure in description (+ `docs/PRIVACY.md`)
- Keep Admin Cockpit author credit (Wolfgang Tödt) + Sarge
- Register admin settings in `<settings>`

### 6. Tests / fixtures

- Neutralize vitest fixtures that hardcode `10.0.0.84` / `/media/4TB` (use generic examples).
- Run `npm test`.

### 7. Docs + commit

- CHANGELOG `[1.12.0]` filled.
- README version badge.
- Commit with Claude trailer via `env -i`; **do not push**.

## Out of scope

- Re-implementing App Store install/update via private APIs
- Signing keys / publishing to apps.nextcloud.com
- Changing privileged sidecar security model (still optional host agent)

## Verification

1. Private-API grep clean under `lib/`
2. `npm test` + `npm run build` exit 0
3. Tools with empty config returns no deep-link tiles
4. Admin settings save round-trips appconfig keys
5. Generic compose has no `/media/4TB` or `10.0.0.84` literals
