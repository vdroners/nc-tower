/**
 * Pure helpers for chassis-fan charts and the 5-point curve editor.
 * validateCurvePoints mirrors sidecar/chassis_fan.py::validate_curve.
 */

/**
 * @param {unknown} points five [temp_c, pwm] pairs (or {temp_c,pwm} objects)
 * @return {{ ok: boolean, error: string|null, points: Array<[number, number]>|null }}
 */
export function validateCurvePoints(points) {
	if (!Array.isArray(points) || points.length !== 5) {
		return { ok: false, error: 'curve_requires_5_points', points: null }
	}
	const parsed = []
	let prevTemp = -1
	for (const item of points) {
		let temp
		let pwm
		if (Array.isArray(item) && item.length === 2) {
			temp = Number(item[0])
			pwm = Number(item[1])
		} else if (item && typeof item === 'object') {
			temp = Number(item.temp_c ?? item.temp)
			pwm = Number(item.pwm)
		} else {
			return { ok: false, error: 'curve_point_must_be_temp_pwm_pair', points: null }
		}
		if (!Number.isFinite(temp) || !Number.isFinite(pwm)) {
			return { ok: false, error: 'curve_point_not_int', points: null }
		}
		temp = Math.trunc(temp)
		pwm = Math.trunc(pwm)
		if (temp < 0 || temp > 120) {
			return { ok: false, error: 'temp_out_of_range', points: null }
		}
		if (pwm < 0 || pwm > 255) {
			return { ok: false, error: 'pwm_out_of_range', points: null }
		}
		if (temp < prevTemp) {
			return { ok: false, error: 'temps_must_be_monotonic', points: null }
		}
		prevTemp = temp
		parsed.push([temp, pwm])
	}
	return { ok: true, error: null, points: parsed }
}

/**
 * Map a temp/PWM pair into SVG coordinates for a fixed viewBox.
 *
 * @param {Array<[number, number]>|Array<{temp_c?: number, pwm?: number}>} curvePoints
 * @param {number|null|undefined} tempC
 * @param {number|null|undefined} pwm 0..255 (or percent if pwmIsPct)
 * @param {{ width?: number, height?: number, pad?: number, pwmIsPct?: boolean }} [opts]
 * @return {{ x: number, y: number, tempC: number|null, pwm: number|null }|null}
 */
export function operatingPoint(curvePoints, tempC, pwm, opts = {}) {
	const width = opts.width ?? 200
	const height = opts.height ?? 100
	const pad = opts.pad ?? 10
	if (tempC == null || pwm == null || tempC === '' || pwm === '') {
		return null
	}
	const t = Number(tempC)
	let p = Number(pwm)
	if (!Number.isFinite(t) || !Number.isFinite(p)) {
		return null
	}
	if (opts.pwmIsPct) {
		p = (p / 100) * 255
	}
	// Use curve extent when available so the dot sits in the same frame as the path.
	const pairs = normalisePairs(curvePoints)
	const tempMax = pairs.length ? Math.max(120, ...pairs.map((row) => row[0])) : 120
	const tempMin = pairs.length ? Math.min(0, ...pairs.map((row) => row[0])) : 0
	const span = Math.max(1, tempMax - tempMin)
	const x = pad + ((t - tempMin) / span) * (width - 2 * pad)
	const y = height - pad - (Math.min(255, Math.max(0, p)) / 255) * (height - 2 * pad)
	return { x, y, tempC: t, pwm: p }
}

/**
 * Build an SVG path for a 5-point fan curve.
 *
 * @param {Array<[number, number]>|Array<{temp_c?: number, pwm?: number}>} points
 * @param {{ width?: number, height?: number, pad?: number }} [opts]
 * @return {string}
 */
export function curvePath(points, opts = {}) {
	const width = opts.width ?? 200
	const height = opts.height ?? 100
	const pad = opts.pad ?? 10
	const pairs = normalisePairs(points)
	if (!pairs.length) {
		return ''
	}
	const tempMax = Math.max(120, ...pairs.map((row) => row[0]))
	const tempMin = Math.min(0, ...pairs.map((row) => row[0]))
	const span = Math.max(1, tempMax - tempMin)
	return pairs.map((row, index) => {
		const x = pad + ((row[0] - tempMin) / span) * (width - 2 * pad)
		const y = height - pad - (row[1] / 255) * (height - 2 * pad)
		return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
	}).join(' ')
}

/**
 * Chart.js datasets: RPM over time, one series per fan header.
 *
 * @param {Array<object>} samples history samples from /tower/chassis-fan/history
 * @return {Array<{ label: string, data: Array<{x: number, y: number|null}> }>}
 */
export function historyToRpmDatasets(samples) {
	const byKey = new Map()
	for (const sample of samples || []) {
		const ts = toMs(sample?.ts)
		if (ts == null) {
			continue
		}
		for (const fan of sample.fans || []) {
			const key = String(fan.header || fan.name || `FAN${fan.index ?? '?'}`)
			if (!byKey.has(key)) {
				byKey.set(key, [])
			}
			const rpm = fan.rpm
			byKey.get(key).push({
				x: ts,
				y: typeof rpm === 'number' && Number.isFinite(rpm) ? rpm : null,
			})
		}
	}
	return [...byKey.entries()].map(([label, data]) => ({ label, data }))
}

/**
 * Chart.js datasets: hwmon temps + GPU temps over time.
 *
 * @param {Array<object>} samples
 * @return {Array<{ label: string, data: Array<{x: number, y: number|null}> }>}
 */
export function historyToTempDatasets(samples) {
	const byKey = new Map()
	const push = (key, ts, value) => {
		if (!byKey.has(key)) {
			byKey.set(key, [])
		}
		byKey.get(key).push({
			x: ts,
			y: typeof value === 'number' && Number.isFinite(value) ? value : null,
		})
	}
	for (const sample of samples || []) {
		const ts = toMs(sample?.ts)
		if (ts == null) {
			continue
		}
		for (const temp of sample.temps || []) {
			const key = String(temp.label || `${temp.chip || 'hwmon'}:${temp.temp || '?'}`)
			push(key, ts, temp.celsius)
		}
		for (const gpu of sample.gpu || []) {
			const key = `GPU ${gpu.name || 'temp'}`
			push(key, ts, gpu.temp_c)
		}
	}
	return [...byKey.entries()].map(([label, data]) => ({ label, data }))
}

/**
 * @param {unknown} points
 * @return {Array<[number, number]>}
 */
function normalisePairs(points) {
	if (!Array.isArray(points)) {
		return []
	}
	const out = []
	for (const item of points) {
		if (Array.isArray(item) && item.length >= 2) {
			const t = Number(item[0])
			const p = Number(item[1])
			if (Number.isFinite(t) && Number.isFinite(p)) {
				out.push([t, p])
			}
		} else if (item && typeof item === 'object') {
			const t = Number(item.temp_c ?? item.temp)
			const p = Number(item.pwm)
			if (Number.isFinite(t) && Number.isFinite(p)) {
				out.push([t, p])
			}
		}
	}
	return out
}

/**
 * @param {unknown} ts unix seconds (possibly float) or ms
 * @return {number|null}
 */
function toMs(ts) {
	const n = Number(ts)
	if (!Number.isFinite(n) || n <= 0) {
		return null
	}
	// Sidecar stores unix seconds; tolerate ms if someone already converted.
	return n > 1e12 ? n : n * 1000
}

export default {
	validateCurvePoints,
	operatingPoint,
	curvePath,
	historyToRpmDatasets,
	historyToTempDatasets,
}
