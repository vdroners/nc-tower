# Plan — NC Tower 1.14.0 Webmin/Portainer parity

Checked-in summary of the Cursor plan executed for 1.14.0.

## Goals

Close remaining Webmin/Portainer gaps so both tools become optional second
opinions (kept running by operator choice). Ship chassis fan control with
curves + visualizations, Portainer container/image parity, host cron/package/
SMART/backup parity, network + Ollama status, audit viewer, then scrub Admin
Cockpit branding to sole Sarge authorship with heritage in CREDITS.md.

## Delivered

- Sidecar modules `chassis_fan.py` + `parity.py`; routes wired in `app.py`
- PHP proxies in `TowerController` / `routes.php`
- UI: `FanPanel.vue`, `FanCharts.vue`, Ops sections, Tools break-glass reword,
  `health.js` warnings
- Gates G28/G29, sidecar unit tests, vitest fanCharts/health
- Provenance scrub + `docs/OPS_PANELS.md`

## Verify

- `make bump-minor` → 1.14.0; `make deploy RESTART=1`; sidecar rebuild
- Browser: fan profile + charts, rename, cleanup job, hold, SMART expand,
  Network/Ollama/Audit
- `php tools/tower-api-gates.php` inside cloud_app (G11/G12/G28/G29)
