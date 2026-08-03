/**
 * Display formatting shared across views. Every helper tolerates the shape
 * drift between docker CLI versions and the sidecar payloads rather than
 * assuming one field name.
 */

/**
 * @param {number|string} value byte count
 * @return {string} human size
 */
export function bytes(value) {
	let n = Number(value) || 0
	const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
	let i = 0
	while (n >= 1024 && i < units.length - 1) {
		n /= 1024
		i++
	}
	return `${n.toFixed(i ? 1 : 0)} ${units[i]}`
}

/**
 * @param {number} seconds epoch seconds
 * @return {string} localised timestamp
 */
export function time(seconds) {
	if (!seconds) {
		return '—'
	}
	try {
		return new Date(Number(seconds) * 1000).toLocaleString()
	} catch (error) {
		return String(seconds)
	}
}

/**
 * @param {number} seconds duration
 * @return {string} compact duration
 */
export function duration(seconds) {
	const n = Number(seconds) || 0
	const days = Math.floor(n / 86400)
	const hours = Math.floor((n % 86400) / 3600)
	const minutes = Math.floor((n % 3600) / 60)
	if (days) {
		return `${days}d ${hours}h`
	}
	return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

/**
 * @param {number} hours power-on hours
 * @return {string} years, one decimal
 */
export function years(hours) {
	// Number(null) and Number('') are both 0, which would render a drive of
	// unknown age as "0 y" — indistinguishable from a brand-new one.
	if (hours == null || hours === '') {
		return '—'
	}
	const n = Number(hours)
	return Number.isFinite(n) ? `${Math.round((n / 8760) * 10) / 10} y` : '—'
}

/**
 * Docker reports ports as a comma string or an array depending on version.
 *
 * @param {string|Array} value ports field
 * @return {string} short summary
 */
export function ports(value) {
	if (value == null || value === '') {
		return '—'
	}
	const parts = typeof value === 'string'
		? value.split(',').map((s) => s.trim()).filter(Boolean)
		: (Array.isArray(value) ? value.map((p) => (typeof p === 'string' ? p : JSON.stringify(p))) : [String(value)])
	if (!parts.length) {
		return '—'
	}
	return parts.slice(0, 2).join(', ') + (parts.length > 2 ? ` +${parts.length - 2}` : '')
}

/**
 * @param {object} iface interface row from `ip -j addr` or /sys fallback
 * @return {string} its v4 addresses, or all if it has none
 */
export function addresses(iface) {
	if (!iface) {
		return ''
	}
	if (typeof iface === 'string') {
		return iface
	}
	const raw = iface.addresses || iface.addrs || iface.addr || []
	if (typeof raw === 'string') {
		return raw
	}
	if (!Array.isArray(raw)) {
		return iface.address || ''
	}
	const list = raw.map((entry) => {
		if (typeof entry === 'string') {
			return entry
		}
		if (entry && entry.address) {
			return entry.prefixlen != null ? `${entry.address}/${entry.prefixlen}` : entry.address
		}
		return ''
	}).filter(Boolean)
	const v4 = list.filter((addr) => addr.includes('.') && !addr.includes(':'))
	return (v4.length ? v4 : list).slice(0, 4).join(', ')
}

/**
 * meminfo strings arrive as "16299764 kB".
 *
 * @param {string} value meminfo value
 * @return {string} human size
 */
export function meminfo(value) {
	if (!value) {
		return '—'
	}
	const match = String(value).match(/(\d+)\s*kB/i)
	return match ? bytes(Number(match[1]) * 1024) : String(value)
}

export default { bytes, time, duration, years, ports, addresses, meminfo }
