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

	// Only meaningful since 1.8.2: before that the parser reported the next
	// attribute row's ID, so /dev/sda read as 10 h against a true 60404 h.
	it('warns on a drive past five years and escalates past seven', () => {
		const fivePlus = assess({ smart: { disks: [{ device: '/dev/sda', health: 'PASS', power_on_hours: 50000 }] } })
		expect(fivePlus.level).toBe(WARN)

		const sevenPlus = assess({ smart: { disks: [{ device: '/dev/sda', health: 'PASS', power_on_hours: 62000 }] } })
		expect(sevenPlus.level).toBe(CRIT)
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

	it('warns when the last backup failed', () => {
		const result = assess({
			inbox: { backup: { ok: false, stale: false, status: 'warn', summary: 'TimescaleDB backup failed' } },
		})
		expect(result.level).toBe(WARN)
		expect(find(result, 'TimescaleDB backup failed')).toBeTruthy()
	})

	it('warns when the backup is stale even if it reported ok', () => {
		const result = assess({ inbox: { backup: { ok: true, stale: true, name: 'backup.json' } } })
		expect(result.level).toBe(WARN)
	})
})

describe('assess — Nextcloud platform health', () => {
	it('reports an available Nextcloud update', () => {
		const result = assess({
			system: { nc_updateAvailable: true, nc_updateVersion: '34.0.2.1', nc_currentVersionimplode: '33.0.7.1' },
		})
		expect(find(result, '34.0.2.1')).toBeTruthy()
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
		expect(assess({ updates: { appscount: 3 } }).level).toBe(WARN)
		expect(assess({ updates: { appscount: 0 } }).items).toHaveLength(0)
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
