/**
 * LocalStorage snooze for Ops attention items.
 *
 * Keyed on severity+title+section so a reappearing finding can be quieted
 * without fixing the underlying cause (e.g. informational nags). CRIT items
 * are never snoozable at the UI layer.
 */

const STORAGE_KEY = 'nc-tower-attention-snooze-v1'
const DEFAULT_MS = 7 * 24 * 60 * 60 * 1000

/**
 * @param {object} item attention item
 * @return {string}
 */
export function itemKey(item) {
	return `${item.severity || ''}|${item.title || ''}|${item.section || ''}`
}

/**
 * @return {Record<string, number>} key -> expiresAt ms
 */
export function loadSnoozes() {
	try {
		const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
		const now = Date.now()
		const next = {}
		for (const [key, expires] of Object.entries(raw || {})) {
			if (Number(expires) > now) {
				next[key] = Number(expires)
			}
		}
		return next
	} catch (error) {
		return {}
	}
}

/**
 * @param {Record<string, number>} map
 */
export function saveSnoozes(map) {
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
	} catch (error) {
		/* ignore quota */
	}
}

/**
 * @param {object} item
 * @param {number} [durationMs]
 */
export function snoozeItem(item, durationMs = DEFAULT_MS) {
	const map = loadSnoozes()
	map[itemKey(item)] = Date.now() + durationMs
	saveSnoozes(map)
	return map
}

/**
 * @param {object} item
 */
export function unsnoozeItem(item) {
	const map = loadSnoozes()
	delete map[itemKey(item)]
	saveSnoozes(map)
	return map
}

/**
 * @param {Array<object>} items
 * @param {Record<string, number>} [snoozes]
 * @return {{visible: Array<object>, snoozed: Array<object>}}
 */
export function partitionItems(items, snoozes) {
	const map = snoozes || loadSnoozes()
	const now = Date.now()
	const visible = []
	const snoozed = []
	for (const item of items || []) {
		const expires = map[itemKey(item)]
		if (expires && expires > now && item.severity !== 'crit') {
			snoozed.push(item)
		} else {
			visible.push(item)
		}
	}
	return { visible, snoozed }
}

export default {
	itemKey, loadSnoozes, saveSnoozes, snoozeItem, unsnoozeItem, partitionItems, DEFAULT_MS, STORAGE_KEY,
}
