/**
 * Triage rules behind the Ops verdict banner.
 *
 * Pure functions over the sidecar payloads: given what the page already
 * fetched, decide whether an operator needs to do something. Ordered worst
 * first so the attention list reads top-down.
 */

export const OK = 'ok'
export const WARN = 'warn'
export const CRIT = 'crit'

const RANK = { [OK]: 0, [WARN]: 1, [CRIT]: 2 }

const HOURS_5Y = 43800
const HOURS_7Y = 61320
const LOG_WARN_BYTES = 100 * 1024 * 1024
const LOG_CRIT_BYTES = 512 * 1024 * 1024

const SIZE_UNITS = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 }

/**
 * Nextcloud reports sizes pre-formatted ("103.73 MB"), so thresholds have to
 * parse them back.
 *
 * @param {string} value formatted size
 * @return {number|null} bytes, or null when unparseable
 */
function parseSize(value) {
	const match = String(value || '').match(/([\d.]+)\s*([KMGT]?B)/i)
	if (!match) {
		return null
	}
	return parseFloat(match[1]) * (SIZE_UNITS[match[2].toUpperCase()] || 1)
}

/**
 * @param {...string} levels severities
 * @return {string} the worst of them
 */
export function worst(...levels) {
	return levels.reduce((acc, level) => (RANK[level] > RANK[acc] ? level : acc), OK)
}

/**
 * @param {number|null} value measurement
 * @param {number} warn warn threshold
 * @param {number} crit critical threshold
 * @return {string} severity
 */
function overThreshold(value, warn, crit) {
	if (value == null || Number.isNaN(Number(value))) {
		return OK
	}
	const n = Number(value)
	if (n >= crit) {
		return CRIT
	}
	return n >= warn ? WARN : OK
}

/**
 * @param {object} data collected section payloads
 * @param {object} [data.host] /tower/host
 * @param {object} [data.containers] /tower/containers
 * @param {object} [data.smart] /tower/smart
 * @param {object} [data.gpu] /tower/gpu
 * @param {object} [data.inbox] /tower/ops-inbox
 * @param {object} [data.packages] /tower/packages
 * @return {{level: string, items: Array<object>}} verdict plus findings
 */
export function assess(data) {
	const items = []
	const add = (severity, title, detail, section) => {
		if (severity !== OK) {
			items.push({ severity, title, detail, section })
		}
	}

	const containers = data.containers?.containers || []
	const unhealthy = containers.filter((c) => /unhealthy/i.test(c.status_raw || ''))
	if (unhealthy.length) {
		add(CRIT, `${unhealthy.length} container${unhealthy.length > 1 ? 's' : ''} unhealthy`,
			unhealthy.map((c) => c.name).join(', '), 'containers')
	}
	const exited = containers.filter((c) => c.status === 'exited')
	if (exited.length) {
		add(WARN, `${exited.length} container${exited.length > 1 ? 's' : ''} exited`,
			exited.map((c) => c.name).join(', '), 'containers')
	}

	for (const disk of data.host?.disks || []) {
		if (disk.error) {
			add(CRIT, `${disk.path} unreadable`, String(disk.error), 'host')
			continue
		}
		const severity = overThreshold(disk.used_pct, 85, 95)
		add(severity, `${disk.path} ${disk.used_pct}% full`,
			`${disk.path} is running out of space`, 'host')
	}

	const packageTemp = overThreshold(data.host?.package_temp_c, 55, 65)
	add(packageTemp, `CPU package ${data.host?.package_temp_c}°C`, 'CPU running hot', 'host')

	for (const disk of data.smart?.disks || []) {
		if (disk.health === 'FAIL') {
			add(CRIT, `${disk.device} SMART FAIL`, disk.model || 'drive reports failure', 'smart')
		} else if (disk.health !== 'PASS') {
			add(WARN, `${disk.device} SMART ${disk.health}`, disk.model || 'health unknown', 'smart')
		}
		// Only meaningful since 1.8.2 — the old parser reported the next
		// attribute row's ID, so /dev/sda read as 10 h against 60404 h.
		const age = overThreshold(disk.power_on_hours, HOURS_5Y, HOURS_7Y)
		const ageDetail = disk.health === 'PASS'
			? `${disk.power_on_hours} hours — past age threshold (SMART still PASS)`
			: `${disk.power_on_hours} hours — past nominal service life`
		add(age, `${disk.device} ${Math.round((disk.power_on_hours || 0) / 8760 * 10) / 10} years powered on`,
			ageDetail, 'smart')
		add(overThreshold(disk.temp_c, 55, 65), `${disk.device} ${disk.temp_c}°C`, 'drive running hot', 'smart')
	}

	for (const nas of data.smart?.nas_mounts || []) {
		if (nas.ok === false) {
			add(CRIT, `${nas.path} unreachable`, 'network mount is down', 'smart')
		}
	}

	for (const gpu of data.gpu?.gpus || []) {
		add(overThreshold(gpu.temp_c, 80, 90), `${gpu.name} ${gpu.temp_c}°C`, 'GPU running hot', 'gpu')
	}

	const recent = data.inbox?.inbox_recent || []
	const critical = data.inbox?.critical_recent
		|| recent.filter((row) => ['crit', 'critical'].includes(String(row.status || '').toLowerCase()))
	const warns = recent.filter((row) => String(row.status || '').toLowerCase() === 'warn')
	if (critical.length) {
		add(CRIT, `${critical.length} critical ops alert${critical.length > 1 ? 's' : ''}`,
			critical.map((row) => row.monitor || row.name).join(', '), 'inbox')
	}
	if (warns.length) {
		add(WARN, `${warns.length} ops warning${warns.length > 1 ? 's' : ''}`,
			warns.map((row) => row.monitor || row.name).slice(0, 8).join(', '), 'inbox')
	}
	const backup = data.inbox?.backup
	if (backup && backup.stale) {
		add(WARN, 'Backup is stale', `${backup.name || 'no backup file'} — older than 26 h`, 'backup')
	} else if (backup && backup.ok === false) {
		const summary = backup.summary || backup.status || ''
		const title = /timescaledb/i.test(summary)
			? 'TimescaleDB backup failed'
			: (summary || 'Backup check not OK')
		add(WARN, title, summary && summary !== title ? summary : (backup.name || backup.status || ''), 'backup')
	}

	const updates = (data.packages?.packages || []).length
	if (updates) {
		add(WARN, `${updates} package update${updates > 1 ? 's' : ''} pending`,
			'host has upgradable packages', 'host-packages')
	}

	// Nextcloud's own health — otherwise only visible by opening System or Apps.
	const system = data.system || {}
	if (system.nc_updateCheckAvailable !== false && system.nc_updateAvailable) {
		add(WARN, `Nextcloud ${system.nc_updateVersion || 'update'} available`,
			`running ${system.nc_currentVersionimplode || system.nc_version || '?'}`, 'system')
	}
	const logBytes = parseSize(system.nc_logfile_size)
	add(overThreshold(logBytes, LOG_WARN_BYTES, LOG_CRIT_BYTES),
		`nextcloud.log is ${system.nc_logfile_size}`,
		'rotate or truncate the Nextcloud log', 'system')

	const appUpdates = data.updates?.available === false ? 0 : (data.updates?.appscount || 0)
	if (appUpdates) {
		add(WARN, `${appUpdates} app update${appUpdates > 1 ? 's' : ''} available`,
			'Nextcloud apps have updates pending', 'apps')
	}

	items.sort((a, b) => RANK[b.severity] - RANK[a.severity])
	return { level: worst(...items.map((item) => item.severity)), items }
}

export default { assess, worst, OK, WARN, CRIT }
