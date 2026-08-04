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
 * @param {object} [data.chassisFan] /tower/chassis-fan
 * @param {object} [data.backup] /tower/backup inventory
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

	// 1.16.0: 55/65 was crying wolf at idle package temps (~56°C).
	const packageTemp = overThreshold(data.host?.package_temp_c, 70, 85)
	add(packageTemp, `CPU package ${data.host?.package_temp_c}°C`, 'CPU running hot', 'host')

	for (const disk of data.smart?.disks || []) {
		if (disk.health === 'FAIL') {
			add(CRIT, `${disk.device} SMART FAIL`, disk.model || 'drive reports failure', 'smart')
		} else if (disk.health !== 'PASS') {
			add(WARN, `${disk.device} SMART ${disk.health}`, disk.model || 'health unknown', 'smart')
		}
		// Age alone is informational when SMART is PASS and sector counters
		// are clean — otherwise a healthy 6-year drive nags forever.
		const age = overThreshold(disk.power_on_hours, HOURS_5Y, HOURS_7Y)
		const sectorTrouble = Number(disk.reallocated || 0) > 0
			|| Number(disk.pending || 0) > 0
			|| Number(disk.reallocated_sectors || 0) > 0
			|| Number(disk.pending_sectors || 0) > 0
		if (age !== OK && (disk.health !== 'PASS' || sectorTrouble)) {
			add(age, `${disk.device} ${Math.round((disk.power_on_hours || 0) / 8760 * 10) / 10} years powered on`,
				`${disk.power_on_hours} hours — past nominal service life`, 'smart')
		}
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

	for (const fan of data.chassisFan?.fans || []) {
		const role = String(fan.role || '').toLowerCase()
		if (role && role !== 'unused' && Number(fan.rpm) === 0) {
			add(WARN, `${fan.header || fan.name || fan.fan || 'fan'} stopped`,
				`role ${role} reports 0 RPM`, 'fans')
		}
		if (role === 'pump' && fan.pwm != null && Number(fan.pwm) < 255) {
			add(WARN, `${fan.header || fan.name || 'pump'} PWM below full`,
				`pump PWM ${fan.pwm} (expected 255)`, 'fans')
		}
	}

	// Prefer sidecar active_* (24 h, deduped). Fall back to raw recent for older sidecars.
	const recent = data.inbox?.inbox_recent || []
	const activeWarnings = data.inbox?.active_warnings
	const activeCritical = data.inbox?.active_critical
	const critical = activeCritical
		|| data.inbox?.critical_recent
		|| recent.filter((row) => ['crit', 'critical'].includes(String(row.status || '').toLowerCase()))
	const warns = activeWarnings
		|| recent.filter((row) => String(row.status || '').toLowerCase() === 'warn')
	const formatMonitors = (rows) => {
		const counts = {}
		for (const row of rows) {
			const key = row.monitor || row.name || '?'
			counts[key] = (counts[key] || 0) + (Number(row.count) || 1)
		}
		return Object.entries(counts)
			.map(([name, count]) => (count > 1 ? `${name} ×${count}` : name))
			.slice(0, 8)
			.join(', ')
	}
	if (critical.length) {
		const n = critical.reduce((sum, row) => sum + (Number(row.count) || 1), 0)
		add(CRIT, `${n} critical ops alert${n > 1 ? 's' : ''}`,
			formatMonitors(critical), 'inbox')
	}
	if (warns.length) {
		const n = warns.reduce((sum, row) => sum + (Number(row.count) || 1), 0)
		add(WARN, `${n} ops warning${n > 1 ? 's' : ''}`,
			formatMonitors(warns), 'inbox')
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

	const inventory = data.backup
	if (inventory && typeof inventory === 'object' && (inventory.items || inventory.count != null || inventory.newest != null)) {
		const itemsList = inventory.items || []
		const newest = inventory.newest
		const ageHours = newest?.age_hours
		if (!itemsList.length && !newest) {
			add(WARN, 'Backup inventory empty', 'no backup files found on disk', 'backup')
		} else if (ageHours != null && Number(ageHours) > 48) {
			add(WARN, 'Newest backup older than 48 h',
				`${newest.name || 'backup'} · ${ageHours} h old`, 'backup')
		}
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

	// Debug logging left on after troubleshooting grows the log unbounded.
	const loglevel = system.nc_loglevel ?? system.loglevel
	if (loglevel != null && Number(loglevel) < 2) {
		add(WARN, 'Debug logging enabled',
			`loglevel=${loglevel} — nextcloud.log will grow unbounded`, 'system')
	}

	const appUpdates = data.updates?.available === false ? 0 : (data.updates?.appscount || 0)
	if (appUpdates) {
		add(WARN, `${appUpdates} app update${appUpdates > 1 ? 's' : ''} available`,
			'Nextcloud apps have updates pending', 'apps')
	}

	// 1.15.0 — host inventory + NC admin depth
	if (data.storage?.raid?.degraded) {
		add(CRIT, 'RAID array degraded',
			(data.storage.raid.arrays || []).map((a) => a.name || a.md).filter(Boolean).join(', ') || 'mdstat reports degraded',
			'host')
	}
	if (data.hardware?.os?.taint?.hardware_tainted) {
		add(WARN, 'Kernel hardware-tainted',
			(data.hardware.os.taint.flags || []).join(', ') || 'tainted flag set',
			'host')
	}
	const ntp = data.posture?.ntp
	if (ntp && !ntp.unavailable && ntp.synchronized === false) {
		add(WARN, 'NTP not synchronized', ntp.timezone || 'clock may drift', 'host')
	}
	for (const cert of data.posture?.certs || []) {
		const days = cert.days_left
		if (days == null) {
			continue
		}
		if (days < 0) {
			add(CRIT, `TLS cert expired: ${cert.name || cert.host}`,
				`${cert.host || ''} expired`, 'host')
		} else if (days < 21) {
			add(WARN, `TLS cert expiring: ${cert.name || cert.host}`,
				`${days} day(s) remaining`, 'host')
		}
	}
	const tags = data.kernelLog?.tags_seen || []
	if (tags.includes('mce')) {
		add(CRIT, 'MCE / hardware error in kernel log (24 h)', 'check Host › Kernel log', 'host')
	}
	if (tags.includes('oom')) {
		add(WARN, 'OOM killer activity in kernel log (24 h)', 'check Host › Kernel log', 'host')
	}
	for (const row of data.smartHistory?.summary || []) {
		if (row.temp_max != null && Number(row.temp_max) >= 55) {
			add(overThreshold(row.temp_max, 55, 65),
				`${row.device || row.serial} SMART temp peaked ${row.temp_max}°C`,
				`trend window max (now ${row.temp_now ?? '—'}°C)`, 'smart')
		}
	}
	if (data.ncJobs?.stale) {
		const mins = data.ncJobs.lastcron_age_s != null
			? Math.round(data.ncJobs.lastcron_age_s / 60)
			: '?'
		add(WARN, `Nextcloud cron stale (${mins} min)`,
			`mode ${data.ncJobs.cron_mode || '?'}`, 'system')
	}
	if ((data.ncSetup?.error_count || 0) > 0) {
		add(CRIT, `${data.ncSetup.error_count} Nextcloud setup-check error(s)`,
			'see System › Setup checks', 'system')
	} else if ((data.ncSetup?.warn_count || 0) > 0) {
		add(WARN, `${data.ncSetup.warn_count} Nextcloud setup-check warning(s)`,
			'see System › Setup checks', 'system')
	}
	if ((data.ncBruteforce?.total_24h || 0) > 50) {
		add(WARN, `Bruteforce spike: ${data.ncBruteforce.total_24h} attempts / 24 h`,
			'see System › Security', 'system')
	}
	if ((data.ncShares?.passwordless_count || 0) > 0) {
		add(WARN, `${data.ncShares.passwordless_count} passwordless public share(s)`,
			'see System › Share audit', 'system')
	}

	items.sort((a, b) => RANK[b.severity] - RANK[a.severity])
	return { level: worst(...items.map((item) => item.severity)), items }
}

export default { assess, worst, OK, WARN, CRIT }
