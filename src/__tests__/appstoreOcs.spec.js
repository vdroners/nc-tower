import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * Pure mapping logic mirrored from listAppUpdates — keep the filter honest
 * without spinning a Nextcloud session.
 */
function pendingFromApps(apps) {
	return (Array.isArray(apps) ? apps : [])
		.filter((app) => app && app.update)
		.map((app) => ({
			id: app.id,
			name: typeof app.name === 'string' ? app.name : (app.id || ''),
			version: app.version || '',
			updateVersion: app.update,
		}))
}

describe('appstore update mapping', () => {
	it('keeps only apps with a non-empty update field', () => {
		const pending = pendingFromApps([
			{ id: 'files', name: 'Files', version: '1.0.0' },
			{ id: 'deck', name: 'Deck', version: '1.2.0', update: '1.3.0' },
			{ id: 'notes', name: 'Notes', version: '4.0.0', update: '' },
		])
		expect(pending).toHaveLength(1)
		expect(pending[0].id).toBe('deck')
		expect(pending[0].updateVersion).toBe('1.3.0')
	})

	it('tolerates a non-array payload', () => {
		expect(pendingFromApps(null)).toEqual([])
		expect(pendingFromApps({})).toEqual([])
	})
})

describe('widget all-clear honesty', () => {
	beforeEach(() => {
		vi.resetModules()
	})

	it('assess with empty payloads stays ok (caller must gate All clear on fetchOk)', async () => {
		const { assess, OK } = await import('../services/health.js')
		const result = assess({})
		expect(result.level).toBe(OK)
		expect(result.items).toHaveLength(0)
	})
})
