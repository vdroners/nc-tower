# NC Tower 1.16.0 — Host visualizations, container UX, attention fixes

Checked-in plan for the 1.16.0 release. Cursor-side plan:
`host_viz,_containers_ux,_health_fixes_c435967b.plan.md`.

## Why

Ops attention list was noisy (CPU 56°C “hot”, healthy aged disk, 49 stale
inbox files, debug logging left on). Host inventory was tables-only. Containers
were a flat Portainer-lite table without project grouping or inline actions.
Tools still showed “Break-glass — still needed” after Tower had parity.

## What changed

### Attention / health
- CPU package warn/crit **70 / 85** (was 55 / 65)
- SMART age silent when health is PASS and sector counters clean
- Inbox `active_warnings` / `active_critical` (24 h, dedupe by monitor)
- `POST /ops/inbox/archive-stale` + Ops UI button
- `nc_loglevel` in System payload; WARN when loglevel &lt; 2
- AttentionList 7-day snooze (CRIT not snoozable); banner uses unsnoozed items

### Host visualizations
- TempStrip heat bars + 24 h package-temp history chart
- DIMM slot map, CPU topology chips, storage capacity map, PCIe class badges, NIC link chips

### Containers
- Project groups, state filter chips, inline Logs/Restart/Stop|Start
- UsageBars, clickable ports, parsed stats, inspect summary preamble
- Per-row `health` + `uptime` from sidecar

### Tools
- Single group: **Legacy consoles — superseded by Tower**

## Verify
- vitest + `python3 -m unittest sidecar.test_parity sidecar.test_inventory`
- Preflight G33/G34/G35
- Attention list clears after loglevel=2, truncate, apt upgrade of the two packages, sidecar restart
