/**
 * Build a labeled Markdown inventory report from hardware + storage payloads.
 *
 * @param {object} hardware /tower/hardware
 * @param {object} storage /tower/storage
 * @return {string} markdown
 */
export function inventoryMarkdown(hardware = {}, storage = {}) {
	const dmi = hardware.dmi || {}
	const cpu = hardware.cpu || {}
	const os = hardware.os || {}
	const lines = [
		'# Host inventory',
		'',
		`Generated: ${new Date().toISOString()}`,
		'',
		'## System',
		`- Product: ${dmi.sys_vendor || ''} ${dmi.product_name || ''}`.trim(),
		`- Serial: ${dmi.product_serial || '—'}`,
		`- Board: ${dmi.board_vendor || ''} ${dmi.board_name || ''} ${dmi.board_version || ''}`.trim(),
		`- BIOS: ${dmi.bios_vendor || ''} ${dmi.bios_version || ''} (${dmi.bios_date || '—'})`,
		`- CPU: ${cpu.model || '—'} (${cpu.cpus || '?'} threads, governor ${JSON.stringify(cpu.governor)})`,
		`- OS: ${os.pretty_name || '—'}`,
		`- Hostname: ${os.hostname || '—'}`,
		`- Kernel: ${os.uname || '—'}`,
		`- Last boot: ${os.last_boot || '—'}`,
		`- Taint: ${(os.taint && os.taint.flags || []).join(', ') || 'none'}`,
		'',
		'## Memory modules',
	]
	const dimms = (hardware.dimms && hardware.dimms.items) || []
	if (!dimms.length) {
		lines.push('_none / unavailable_')
	} else {
		for (const d of dimms) {
			lines.push(`- ${d.locator || '?'}: ${d.size || '?'} ${d.type || ''} @ ${d.speed || '?'} · ${d.part_number || d.manufacturer || ''}`)
		}
	}
	lines.push('', '## Storage')
	const disks = flattenDisks((storage.lsblk && storage.lsblk.blockdevices) || [])
	if (!disks.length) {
		lines.push('_none / unavailable_')
	} else {
		for (const d of disks) {
			lines.push(`- ${d.name}: ${d.size_h || d.size || '?'} ${d.model || ''} serial=${d.serial || '—'} ${d.tran || ''}`.trim())
		}
	}
	lines.push('', '## PCIe')
	for (const p of (hardware.pcie && hardware.pcie.items) || []) {
		lines.push(`- ${p.slot}: [${p.class}] ${p.vendor} ${p.device}`)
	}
	lines.push('', '## USB')
	for (const u of (hardware.usb && hardware.usb.items) || []) {
		lines.push(`- Bus ${u.bus} Dev ${u.device}: ${u.id} ${u.name}`)
	}
	return lines.join('\n')
}

/**
 * @param {Array<object>} nodes lsblk blockdevices
 * @return {Array<object>} disk-only rows (for export / SMART join)
 */
export function flattenDisks(nodes) {
	const out = []
	const walk = (list) => {
		for (const n of list || []) {
			if (n.type === 'disk') {
				out.push({
					...n,
					size_h: formatBytes(n.size),
				})
			}
			walk(n.children)
		}
	}
	walk(nodes)
	return out
}

/**
 * Flatten lsblk into indented disk → partition → mount rows for the Host table.
 *
 * @param {Array<object>} nodes lsblk blockdevices
 * @param {number} [depth]
 * @return {Array<object>}
 */
export function flattenStorageTree(nodes, depth = 0) {
	const out = []
	for (const n of nodes || []) {
		out.push({
			...n,
			depth,
			name_indented: `${'  '.repeat(depth)}${n.name || '?'}`,
			size_h: formatBytes(n.size),
		})
		if (n.children && n.children.length) {
			out.push(...flattenStorageTree(n.children, depth + 1))
		}
	}
	return out
}

/**
 * @param {number|string} bytes
 * @return {string}
 */
function formatBytes(bytes) {
	const n = Number(bytes)
	if (!Number.isFinite(n) || n <= 0) {
		return String(bytes || '—')
	}
	const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
	let v = n
	let i = 0
	while (v >= 1024 && i < units.length - 1) {
		v /= 1024
		i++
	}
	return `${v.toFixed(i ? 1 : 0)} ${units[i]}`
}

/**
 * Trigger a browser download of JSON.
 *
 * @param {object} payload
 * @param {string} [filename]
 */
export function downloadJson(payload, filename = 'host-inventory.json') {
	const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
	const url = URL.createObjectURL(blob)
	const a = document.createElement('a')
	a.href = url
	a.download = filename
	a.click()
	URL.revokeObjectURL(url)
}

/**
 * @param {string} text
 * @return {Promise<void>}
 */
export async function copyText(text) {
	if (navigator.clipboard && navigator.clipboard.writeText) {
		await navigator.clipboard.writeText(text)
		return
	}
	const ta = document.createElement('textarea')
	ta.value = text
	document.body.appendChild(ta)
	ta.select()
	document.execCommand('copy')
	document.body.removeChild(ta)
}
