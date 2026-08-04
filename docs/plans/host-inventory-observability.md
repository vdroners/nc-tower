# Host inventory & observability + Nextcloud admin depth (1.15.0)

## Why

Operators needed motherboard / DIMM / storage labeling without Webmin, plus
Nextcloud log / setup / jobs / share posture that previously required Settings
or occ. Fan history gauges were removed earlier; this release adds flat
read-only inventory tables instead.

## What changed

### Sidecar (`sidecar/inventory.py`)

- `GET /host/hardware` — DMI, DIMMs, CPU live governor/MHz, OS/kernel, taint, PCIe/USB
- `GET /host/storage` — lsblk tree, mdstat RAID, NVMe temps (serial join key)
- `GET /host/temperatures` — hwmon + GPU + disk temps
- `GET /host/network` depth — routes, DNS, listeners, ethtool NIC detail
- `GET /host/posture` — who/last/NTP/failed SSH/TLS expiry
- `GET /host/kernel-log` — warning+ journal with MCE/OOM/disk-reset tags
- SMART 10-min trend sampler + `GET /host/smart/history`
- Capabilities: `hardware`, `storage-topology`, `temperatures`, `network-depth`,
  `posture`, `kernel-log`, `smart-history`

### PHP

- TowerController proxies for the new host GETs
- `NcAdminController` — log tail, setup checks, jobs, bruteforce, shares,
  sessions, bloat, maintenance status chip (no toggle)

### UI

- Host tab: Hardware (export MD/JSON), Storage, Temperatures, Security, Kernel log
- System tab: NC log viewer, setup checks, jobs, security, share audit, bloat
- Ops: network depth tables + SMART trend min/now/max
- health.js: RAID / cert / NTP / MCE / taint / cron stale / setup / bruteforce /
  passwordless shares / SMART trend temp

## Verify

- `python3 sidecar/test_inventory.py`
- `npm test` (health + inventoryExport specs)
- `make deploy RESTART=1` + sidecar recreate with `inventory.py` mount
- `make gate-preflight` (G31 hardware/storage/posture, G32 ncadmin routes)
- Browser: Host + System + Ops Network/SMART sections

## Out of scope

No host mutators, no maintenance-mode toggle, no occ into `cloud_*`, no IPMI/UPS,
no share deletion / session revoke.
