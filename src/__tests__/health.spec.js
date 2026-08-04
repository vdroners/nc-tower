import { describe, it, expect } from 'vitest'
import { assess, worst, OK, WARN, CRIT } from '../services/health.js'

/**
 * The triage rules decide what an operator is told is critical. They are pure
 * functions over the sidecar payloads, so they are cheap to pin down — and a
 * wrong threshold here is invisible until the day it matters.
 */

const find = (result, fragment) =>
	result.items.find((item) => item.title.includes(fragment) || (item.detail || '').includes(fragment))

describe('worst', () => {
	it('returns OK for no levels', () => {
		expect(worst()).toBe(OK)
	})

	it('picks the highest severity regardless of order', () => {
		expect(worst(OK, CRIT, WARN)).toBe(CRIT)
		expect(worst(WARN, OK)).toBe(WARN)
	})
})

describe('assess — containers', () => {
	it('reports an unhealthy container as critical', () => {
		const result = assess({
			containers: { containers: [{ name: 'gcs_sitl', status: 'running', status_raw: 'Up 2 hours (unhealthy)' }] },
		})
		expect(result.level).toBe(CRIT)
		expect(find(result, 'gcs_sitl')).toBeTruthy()
	})

	it('treats a healthy container as no finding', () => {
		const result = assess({
			containers: { containers: [{ name: 'gcs_sitl', status: 'running', status_raw: 'Up 2 hours (healthy)' }] },
		})
		expect(result.level).toBe(OK)
		expect(result.items).toHaveLength(0)
	})

	it('warns on an exited container without escalating to critical', () => {
		const result = assess({
			containers: { containers: [{ name: 'gcs_adsb', status: 'exited', status_raw: 'Exited (0)' }] },
		})
		expect(result.level).toBe(WARN)
	})
})

describe('assess — disks', () => {
	it.each([
		[50, OK],
		[86, WARN],
		[96, CRIT],
	])('disk at %i%% is %s', (used, expected) => {
		const result = assess({ host: { disks: [{ path: '/data', used_pct: used }] } })
		expect(result.level).toBe(expected)
	})

	it('flags an unreadable disk as critical', () => {
		const result = assess({ host: { disks: [{ path: '/backup', error: 'permission denied' }] } })
		expect(result.level).toBe(CRIT)
	})
})

describe('assess — SMART', () => {
	it('flags a failing drive as critical', () => {
		const result = assess({ smart: { disks: [{ device: '/dev/sda', health: 'FAIL' }] } })
		expect(result.level).toBe(CRIT)
	})

	// 1.16.0: age alone is informational when SMART still PASSes.
	it('ignores age on a PASS drive with clean sector counters', () => {
		const fivePlus = assess({ smart: { disks: [{ device: '/dev/sda', health: 'PASS', power_on_hours: 50000 }] } })
		expect(fivePlus.level).toBe(OK)
		expect(find(fivePlus, 'years powered')).toBeFalsy()

		const sevenPlus = assess({ smart: { disks: [{ device: '/dev/sda', health: 'PASS', power_on_hours: 62000 }] } })
		expect(sevenPlus.level).toBe(OK)
	})

	it('still escalates age when SMART is not PASS or sectors are troubled', () => {
		const failing = assess({
			smart: { disks: [{ device: '/dev/sda', health: 'FAIL', power_on_hours: 50000 }] },
		})
		expect(find(failing, 'years powered')).toBeTruthy()

		const realloc = assess({
			smart: { disks: [{ device: '/dev/sda', health: 'PASS', power_on_hours: 50000, reallocated: 3 }] },
		})
		expect(realloc.level).toBe(WARN)
		expect(find(realloc, 'years powered')).toBeTruthy()
	})

	it('leaves a young healthy drive alone', () => {
		const result = assess({ smart: { disks: [{ device: '/dev/nvme0', health: 'PASS', power_on_hours: 3759, temp_c: 39 }] } })
		expect(result.level).toBe(OK)
	})

	it('reports an unreachable network mount', () => {
		const result = assess({ smart: { nas_mounts: [{ path: '/media/raid5', ok: false }] } })
		expect(result.level).toBe(CRIT)
	})

	it('says nothing about a healthy network mount', () => {
		const result = assess({ smart: { nas_mounts: [{ path: '/media/raid5', ok: true }] } })
		expect(result.items).toHaveLength(0)
	})
})

describe('assess — ops inbox and backups', () => {
	it('surfaces critical inbox alerts', () => {
		const result = assess({ inbox: { critical_recent: [{ monitor: 'timescaledb' }] } })
		expect(result.level).toBe(CRIT)
	})

	it('prefers active_warnings over raw inbox_recent', () => {
		const result = assess({
			inbox: {
				inbox_recent: [
					{ monitor: 'base-station-freshness', status: 'warn' },
					{ monitor: 'container-watchdog', status: 'warn' },
				],
				active_warnings: [{ monitor: 'container-watchdog', status: 'warn', count: 2 }],
				critical_recent: [],
				active_critical: [],
			},
		})
		expect(result.level).toBe(WARN)
		expect(find(result, '2 ops warning')).toBeTruthy()
		expect(find(result, 'container-watchdog')).toBeTruthy()
		expect(find(result, 'base-station')).toBeFalsy()
	})

	it('falls back to raw warn rows when active_warnings is absent', () => {
		const result = assess({
			inbox: {
				inbox_recent: [
					{ monitor: 'base-station-freshness', status: 'warn' },
					{ monitor: 'container-watchdog', status: 'warn' },
				],
				critical_recent: [],
			},
		})
		expect(result.level).toBe(WARN)
		expect(find(result, '2 ops warning')).toBeTruthy()
	})

	it('warns when the last backup failed', () => {
		const result = assess({
			inbox: { backup: { ok: false, stale: false, status: 'warn', summary: 'TimescaleDB backup failed' } },
		})
		expect(result.level).toBe(WARN)
		expect(find(result, 'TimescaleDB backup failed')).toBeTruthy()
		expect(result.items[0].title).toBe('TimescaleDB backup failed')
	})

	it('warns when the backup is stale even if it reported ok', () => {
		const result = assess({ inbox: { backup: { ok: true, stale: true, name: 'backup.json' } } })
		expect(result.level).toBe(WARN)
	})
})

describe('assess — Nextcloud platform health', () => {
	it('reports an available Nextcloud update', () => {
		const result = assess({
			system: {
				nc_updateCheckAvailable: true,
				nc_updateAvailable: true,
				nc_updateVersion: '34.0.2.1',
				nc_currentVersionimplode: '33.0.7.1',
			},
		})
		expect(find(result, '34.0.2.1')).toBeTruthy()
	})

	it('ignores stubbed NC update checks that always report false', () => {
		const result = assess({
			system: { nc_updateCheckAvailable: false, nc_updateAvailable: false },
		})
		expect(result.items.filter((item) => /Nextcloud .* available/.test(item.title))).toHaveLength(0)
	})

	it('parses the pre-formatted log size and warns past 100 MB', () => {
		expect(assess({ system: { nc_logfile_size: '12.00 MB' } }).level).toBe(OK)
		expect(assess({ system: { nc_logfile_size: '103.73 MB' } }).level).toBe(WARN)
		expect(assess({ system: { nc_logfile_size: '1.20 GB' } }).level).toBe(CRIT)
	})

	it('ignores an unparseable log size rather than guessing', () => {
		expect(assess({ system: { nc_logfile_size: 'not available' } }).level).toBe(OK)
	})

	it('reports pending app updates', () => {
		expect(assess({ updates: { appscount: 3, available: true } }).level).toBe(WARN)
		expect(assess({ updates: { appscount: 0, available: true } }).items).toHaveLength(0)
	})

	it('does not treat stubbed app-update listing zeros as pending updates', () => {
		expect(assess({ updates: { appscount: 0, available: false } }).items).toHaveLength(0)
	})

	it('warns when a used chassis fan reports 0 RPM', () => {
		const result = assess({
			chassisFan: { fans: [{ header: 'RAD1', role: 'radiator', rpm: 0, pwm: 180 }] },
		})
		expect(result.level).toBe(WARN)
		expect(find(result, 'stopped')).toBeTruthy()
	})

	it('ignores unused chassis fans at 0 RPM', () => {
		expect(assess({
			chassisFan: { fans: [{ header: 'FAN3', role: 'unused', rpm: 0 }] },
		}).items).toHaveLength(0)
	})

	it('warns when pump PWM is below full', () => {
		const result = assess({
			chassisFan: { fans: [{ header: 'PUMP', role: 'pump', rpm: 3000, pwm: 200 }] },
		})
		expect(find(result, 'PWM below full')).toBeTruthy()
	})

	it('warns when backup inventory is empty or stale past 48 h', () => {
		expect(find(assess({ backup: { items: [], count: 0 } }), 'inventory empty')).toBeTruthy()
		expect(find(assess({
			backup: { items: [{ name: 'old.tgz', age_hours: 60 }], newest: { name: 'old.tgz', age_hours: 60 } },
		}), 'older than 48')).toBeTruthy()
		expect(assess({
			backup: { items: [{ name: 'fresh.tgz', age_hours: 2 }], newest: { name: 'fresh.tgz', age_hours: 2 } },
		}).items).toHaveLength(0)
	})
})

describe('assess — SMART age copy', () => {
	it('does not nag age when SMART still PASS', () => {
		const result = assess({
			smart: { disks: [{ device: '/dev/sda', health: 'PASS', power_on_hours: 50000 }] },
		})
		expect(find(result, 'SMART still PASS')).toBeFalsy()
		expect(find(result, 'years powered')).toBeFalsy()
	})
})

describe('assess — CPU package temp (1.16)', () => {
	it('treats 56°C as OK and warns at 70°C', () => {
		expect(assess({ host: { package_temp_c: 56 } }).level).toBe(OK)
		expect(assess({ host: { package_temp_c: 72 } }).level).toBe(WARN)
		expect(assess({ host: { package_temp_c: 86 } }).level).toBe(CRIT)
	})
})

describe('assess — debug loglevel (1.16)', () => {
	it('warns when Nextcloud loglevel is below 2', () => {
		const result = assess({ system: { nc_loglevel: 0 } })
		expect(find(result, 'Debug logging')).toBeTruthy()
		expect(assess({ system: { nc_loglevel: 2 } }).items.filter((i) => /Debug logging/.test(i.title))).toHaveLength(0)
	})
})

describe('assess — overall', () => {
	it('is OK on empty input rather than throwing', () => {
		const result = assess({})
		expect(result.level).toBe(OK)
		expect(result.items).toEqual([])
	})

	it('orders findings worst-first', () => {
		const result = assess({
			host: { disks: [{ path: '/', used_pct: 87 }] },
			containers: { containers: [{ name: 'x', status: 'running', status_raw: 'Up (unhealthy)' }] },
		})
		expect(result.items[0].severity).toBe(CRIT)
		expect(result.level).toBe(CRIT)
	})
})

describe('assess — 1.15 inventory / NC admin', () => {
	it('flags RAID degraded', () => {
		expect(find(assess({ storage: { raid: { degraded: true, arrays: [{ name: 'md0' }] } } }), 'RAID')).toBeTruthy()
	})

	it('flags NTP unsynced', () => {
		expect(find(assess({ posture: { ntp: { synchronized: false, timezone: 'UTC' } } }), 'NTP')).toBeTruthy()
	})

	it('flags TLS cert expiring', () => {
		expect(find(assess({
			posture: { certs: [{ name: 'cloud', host: 'x', days_left: 10 }] },
		}), 'TLS cert')).toBeTruthy()
	})

	it('flags MCE / OOM kernel tags', () => {
		expect(find(assess({ kernelLog: { tags_seen: ['mce'] } }), 'MCE')).toBeTruthy()
		expect(find(assess({ kernelLog: { tags_seen: ['oom'] } }), 'OOM')).toBeTruthy()
	})

	it('flags hardware taint', () => {
		expect(find(assess({
			hardware: { os: { taint: { hardware_tainted: true, flags: ['mce'] } } },
		}), 'tainted')).toBeTruthy()
	})

	it('flags NC cron stale and setup errors', () => {
		expect(find(assess({ ncJobs: { stale: true, lastcron_age_s: 1200, cron_mode: 'cron' } }), 'cron stale')).toBeTruthy()
		expect(find(assess({ ncSetup: { error_count: 2 } }), 'setup-check')).toBeTruthy()
	})

	it('flags bruteforce spike and passwordless shares', () => {
		expect(find(assess({ ncBruteforce: { total_24h: 80 } }), 'Bruteforce')).toBeTruthy()
		expect(find(assess({ ncShares: { passwordless_count: 3 } }), 'passwordless')).toBeTruthy()
	})

	it('flags SMART trend high temp', () => {
		expect(find(assess({
			smartHistory: { summary: [{ device: '/dev/nvme0', serial: 'X', temp_max: 60, temp_now: 55 }] },
		}), 'SMART temp')).toBeTruthy()
	})
})
