# Operator guide — Ops panels (1.14.0)

NC Tower Ops now covers the day-to-day work that used to require Webmin or
Portainer. Webmin and Portainer stay running as optional second opinions.

## Fans

- **GPU fans** — set-all % / set-auto / per-fan speed (20–100%).
- **Chassis PWM** — per-header mode (Manual / Thermal Cruise / BIOS auto),
  manual %, named profiles (`silent` / `balanced` / `performance`), 5-point
  curve editor, RPM/temp history charts.
- **Safety** — mode 0 (fan off) is refused; headers with role `pump` stay at
  PWM 255; every mutate re-asserts the pump floor.
- **fancontrol.service** — if active, Tower warns when a PWM is also managed by
  `/etc/fancontrol`. Prefer one writer.
- **Reboot survival** — last applied profile / per-header state is stored in
  `/ops/state/fan-config.json` and re-applied when the sidecar starts. Use
  **Apply saved state** after a host reboot if needed.

## Containers / images

- Rename, recreate with env/memory/CPU/restart overrides, live stats, image
  remove (refused while any container references the image).
- **Cleanup** runs `/ops/bin/webmin/docker-cleanup.sh prune` as a detached job
  (dangling images, stopped >7d, unused networks — never volumes).

## Cron

- Root crontab is editable (full-text replace) after a typed confirmation.
- A timestamped backup lands in `/ops/state/cron-backups/` before every save.
- `/etc/cron.d` remains **read-only** — those files are owned by packages and
  the ops monitor install path.

## Packages / SMART / Backup

- Hold / unhold packages that appear in the upgradable or held lists.
- Expand a SMART disk row for per-attribute detail (`smartctl -x -j`).
- Backup inventory lists `/media/4TB/backups`; delete is typed-confirm.
  **Restore is manual** — do not one-click restore a Nextcloud backup from
  Tower. Typical restore: stop `cloud_app`, restore DB + data from the chosen
  tarball per the estate backup runbook, then start and `occ upgrade`.

## Network / Ollama / Audit

- Network is status-only (ZeroTier, WireGuard peers with redacted keys,
  interfaces, ddclient, public IP). Joining networks stays a CLI operation.
- Ollama lists models, pull (job-backed), delete (refuses while running unless
  forced).
- Audit tails the sidecar audit log so every Tower mutator is visible in one
  place.
