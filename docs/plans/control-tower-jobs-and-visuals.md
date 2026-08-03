# Control Tower 1.11 — job runner, host updates, and visualisation

## Context

Control Tower can see the host well but shows almost everything as text, and the Tools page
is still a flat grid of deep links to the programs it was meant to replace. Two structural
gaps block progress:

1. **Long operations block a synchronous request.** Backup (600 s), image pull and stack
   rebuild all run inside one HTTP call behind a 130 s PHP proxy timeout. The browser gives
   up while the work continues server-side, so the UI reports failure for operations that
   succeeded. Any update capability makes this worse.
2. **No history.** Every sidecar endpoint is point-in-time, so nothing can be charted.

Both are fixable without new collection infrastructure: the host already writes
`/media/4TB/ops/state/memory-trend.jsonl` (6,202 samples at 15-min cadence since 30 May)
and 126 timestamped `ops/inbox` alert files.

## The self-restart trap

All three pending host updates are `docker-ce`. Running `apt upgrade` from the sidecar
restarts `dockerd`, which kills the container issuing the command **mid-request**. Any
update path must therefore be detached from the sidecar's process tree and its state must
survive the container dying.

This is why the job runner comes first and why job state lives on disk in `/ops/jobs/`,
which both the host and the sidecar can see.

## Job runner (sidecar)

`POST /jobs/{kind}` starts work and returns an id; `GET /jobs` lists; `GET /jobs/{id}`
returns status plus a log tail. State is a JSON file per job in `/ops/jobs/`, the log a
sibling `.log`. Jobs launch through the host's systemd:

```
nsenter --mount=/proc/1/ns/mnt -- systemd-run --unit=nc-tower-<id> --collect \
    /bin/sh -c '<argv> >/media/4TB/ops/jobs/<id>.log 2>&1; echo $? >…/<id>.rc'
```

systemd owns the process, so it survives both the sidecar restarting and dockerd bouncing.
The `sh -c` wrapper only ever receives a command built from a fixed per-kind template with
`shlex.quote` — never an operator string.

Kinds: `apt-upgrade`, `backup`, `image-pull`, `stack-action`. Backup, pull and
stack-action move onto this path, fixing the timeout bug they have today.

## Host updates (the capability being brought in-house)

`Host → Updates` gains: pending package list, whether any of them restart Docker, whether
`/var/run/reboot-required` is set, and an **Install updates** action.

Safety, all of it required:

- Runs as a detached job (above), so a Docker restart cannot orphan it
- Typed confirmation, and an explicit extra warning when the pending set touches `docker*`
  — every container on the box will bounce
- `apt-get` is invoked with a fixed argv (`-y -o Dpkg::Options::=--force-confold upgrade`);
  no operator input reaches the command
- **Never reboots.** `reboot-required` becomes a triage rule; acting on it stays manual
- Audited like every other mutator

## Visualisation

Two components, both copied from existing house patterns rather than invented:

- `TowerChart.vue` — chart.js line/bar, modelled on
  `/media/4TB/nc-wireguard/src/components/common/RateChart.vue`
- `Sparkline.vue` — canvas, no library, modelled on
  `/media/4TB/nc-print/src/components/TemperatureSparkline.vue`

New read endpoints: `/host/history` (parses `memory-trend.jsonl`) and `/ops/timeline`
(buckets the inbox files by hour and status).

| Where | What |
|---|---|
| Home | 24 h alert timeline strip from the inbox files |
| Ops › Containers | Per-row CPU/mem sparkline from a client ring buffer, plus a CPU-share bar |
| Ops › Host | CPU/RAM chart backed by `memory-trend.jsonl` |
| Ops › SMART | Drive-life bars against the 5 y/7 y thresholds; temperature bars |
| Ops › Docker engine | Used vs reclaimable stacked bar |
| Users | Top-10 storage bar |

## Tools → service inventory

Replace the flat grid with three groups — **absorbed into Tower** (marked superseded),
**break-glass** (still needed), **external apps** — each row showing live reachability from
a new `/services/probe` endpoint.

Probe rule: any HTTP response counts as reachable; only a connection failure is down.
Guacamole and MediaMTX both answer 404 at `/` while perfectly healthy, and a naive check
would report them down. OrcaSlicer (`:3030`) is genuinely down right now and the current
page gives no hint.

## Critical files

- `sidecar/app.py` — job runner, `/jobs*`, `/host/updates`, `/host/history`,
  `/ops/timeline`, `/services/probe`
- `appinfo/routes.php`, `lib/Controller/TowerController.php` — proxy routes
- `src/components/TowerChart.vue`, `Sparkline.vue`, `JobPanel.vue` (new)
- `src/views/Ops.vue`, `Host.vue`, `Home.vue`, `Users.vue`, `Tools.vue`

## Verification

1. `npm run build`, `npm run check:refs`, `npm run test`.
2. All gate suites (70 preflight + 58 API + 15 route), plus new cases: job endpoints
   reachable, `apt-upgrade` job kind allowlisted, no operator string reaches `sh -c`.
3. **Job survival proof**: start a long job, restart `nc_tower_sidecar` mid-run, confirm the
   job still completes and its status is still readable afterwards.
4. **Update dry run first**: `apt-get -s upgrade` through the job path, verifying output
   capture and completion, before any real upgrade.
5. Tools probe: confirm Guacamole and MediaMTX report reachable despite 404, and OrcaSlicer
   reports down.
6. Deploy, confirm 1.11.0, no container crashed.

Visual review stays the author's — there is still no authenticated browser session here.
