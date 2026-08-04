# Operator guide — Ops / Host / System panels (1.15.0)

NC Tower covers day-to-day ops that used to require Webmin or Portainer.
Webmin and Portainer stay as optional second opinions (Tools › **Break-glass —
still needed**).

## Host — hardware inventory (1.15)

- **Hardware** — board / BIOS / product+serial, CPU with live governor + MHz,
  OS/kernel, last boot, kernel taint chip, DIMM table, collapsible PCIe/USB.
  **Copy as Markdown** / **Download JSON** builds a labeled inventory report
  from hardware + storage payloads.
- **Storage** — `lsblk` tree (model/serial/UUID), RAID/mdstat chip, NVMe temps.
  Disk serial joins SMART rows.
- **Temperatures** — flat hwmon + GPU + disk table (no gauges).
- **Security** — logged-in users, recent logins (`last`), NTP sync, failed-SSH
  24 h count, TLS cert expiry for https service probes (warn < 21 days).
- **Kernel log** — `journalctl -k` warning+ tail with MCE / OOM / disk-reset tags.
- Sections hide behind sidecar `/health` capabilities when the sidecar is older
  than 1.15.0.

## System — Nextcloud admin depth (1.15)

- **Log viewer** — tail `nextcloud.log` with level chips + reqId/text filter;
  maintenance-mode **status chip only** (no toggle — enabling maintenance would
  block the request needed to turn it off; use `occ` on the host).
- **Setup checks** — same data as Settings → Overview (`ISetupCheckManager`).
- **Background jobs** — cron mode, last-cron age (stale > 15 min), job count.
- **Security** — bruteforce attempts (24 h by IP/action) + active sessions/devices
  (no token material).
- **Share audit** — public links missing password / expiry / expired.
- **Storage bloat** — trashbin / versions / previews aggregates from `oc_filecache`.

## Fans

- **GPU fans** — set-all % / set-auto / per-fan speed (20–100%).
- **Chassis PWM** — per-header mode (Manual / Thermal Cruise / BIOS auto),
  manual %, named profiles (`silent` / `balanced` / `performance`), and
  live RPM / PWM chips on each fan card (no history gauges).
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
- **SMART trend** — min/now/max temp (and latest realloc/pending) from a 10-min
  sidecar sampler (`/host/smart/history`).
- Backup inventory lists `/media/4TB/backups`; delete is typed-confirm.
  **Restore is manual** — do not one-click restore a Nextcloud backup from
  Tower. Typical restore: stop `cloud_app`, restore DB + data from the chosen
  tarball per the estate backup runbook, then start and `occ upgrade`.

## Network / Ollama / Audit

- Network is status-only (ZeroTier, WireGuard peers with redacted keys,
  interfaces, ddclient, public IP) plus **routes / DNS / listening TCP /
  NIC ethtool detail** when capability `network-depth` is present.
  Joining networks stays a CLI operation.
- Ollama lists models, pull (job-backed), delete (refuses while running unless
  forced).
- Audit tails the sidecar audit log so every Tower mutator is visible in one
  place.
