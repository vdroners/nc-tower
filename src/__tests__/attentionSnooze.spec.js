import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { itemKey, partitionItems, snoozeItem, unsnoozeItem, STORAGE_KEY } from '../services/attentionSnooze.js'

describe('attentionSnooze', () => {
	beforeEach(() => {
		localStorage.removeItem(STORAGE_KEY)
	})
	afterEach(() => {
		localStorage.removeItem(STORAGE_KEY)
	})

	it('partitions snoozed warn items but never hides crit', () => {
		const items = [
			{ severity: 'warn', title: 'old disk', section: 'smart' },
			{ severity: 'crit', title: 'RAID', section: 'host' },
		]
		snoozeItem(items[0])
		snoozeItem(items[1]) // should still show as visible because crit
		const { visible, snoozed } = partitionItems(items)
		expect(snoozed.map((i) => i.title)).toEqual(['old disk'])
		expect(visible.map((i) => i.title)).toContain('RAID')
		expect(visible.map((i) => i.title)).not.toContain('old disk')
	})

	it('unsnoozes an item', () => {
		const item = { severity: 'warn', title: 'x', section: 'host' }
		snoozeItem(item)
		expect(partitionItems([item]).snoozed).toHaveLength(1)
		unsnoozeItem(item)
		expect(partitionItems([item]).visible).toHaveLength(1)
	})

	it('builds a stable key', () => {
		expect(itemKey({ severity: 'warn', title: 'a', section: 'b' })).toBe('warn|a|b')
	})
})
