import { describe, it, expect } from 'vitest'
import {
	curvePath,
	historyToRpmDatasets,
	historyToTempDatasets,
	operatingPoint,
	validateCurvePoints,
} from '../services/fanCharts.js'

describe('validateCurvePoints', () => {
	it('accepts five monotonic pairs', () => {
		const result = validateCurvePoints([
			[20, 50], [40, 100], [60, 150], [80, 200], [100, 255],
		])
		expect(result.ok).toBe(true)
		expect(result.points).toHaveLength(5)
	})

	it('rejects non-monotonic temps', () => {
		const result = validateCurvePoints([
			[40, 50], [30, 100], [60, 150], [80, 200], [100, 255],
		])
		expect(result.ok).toBe(false)
		expect(result.error).toBe('temps_must_be_monotonic')
	})

	it('rejects wrong length', () => {
		expect(validateCurvePoints([[1, 2]]).error).toBe('curve_requires_5_points')
	})

	it('accepts object form', () => {
		const result = validateCurvePoints([
			{ temp_c: 20, pwm: 50 },
			{ temp_c: 40, pwm: 100 },
			{ temp_c: 60, pwm: 150 },
			{ temp_c: 80, pwm: 200 },
			{ temp_c: 100, pwm: 255 },
		])
		expect(result.ok).toBe(true)
	})
})

describe('curvePath / operatingPoint', () => {
	const curve = [
		{ temp_c: 20, pwm: 50 },
		{ temp_c: 40, pwm: 100 },
		{ temp_c: 60, pwm: 150 },
		{ temp_c: 80, pwm: 200 },
		{ temp_c: 100, pwm: 255 },
	]

	it('builds an SVG path', () => {
		const d = curvePath(curve)
		expect(d.startsWith('M')).toBe(true)
		expect(d.includes(' L')).toBe(true)
	})

	it('places the operating point inside the viewBox', () => {
		const point = operatingPoint(curve, 60, 150)
		expect(point).not.toBeNull()
		expect(point.x).toBeGreaterThan(0)
		expect(point.x).toBeLessThan(200)
		expect(point.y).toBeGreaterThan(0)
		expect(point.y).toBeLessThan(100)
	})

	it('returns null without a temp', () => {
		expect(operatingPoint(curve, null, 150)).toBeNull()
	})
})

describe('history datasets', () => {
	const samples = [
		{
			ts: 1_700_000_000,
			fans: [
				{ index: 1, header: 'CPU_FAN', rpm: 800 },
				{ index: 2, header: 'CHA_FAN1', rpm: 600 },
			],
			temps: [{ label: 'CPU', celsius: 45, chip: 'nct6796' }],
			gpu: [{ name: 'RTX', temp_c: 55 }],
		},
		{
			ts: 1_700_000_030,
			fans: [
				{ index: 1, header: 'CPU_FAN', rpm: 820 },
				{ index: 2, header: 'CHA_FAN1', rpm: 610 },
			],
			temps: [{ label: 'CPU', celsius: 46, chip: 'nct6796' }],
			gpu: [{ name: 'RTX', temp_c: 56 }],
		},
	]

	it('splits RPM by header', () => {
		const sets = historyToRpmDatasets(samples)
		expect(sets.map((s) => s.label).sort()).toEqual(['CHA_FAN1', 'CPU_FAN'])
		expect(sets[0].data).toHaveLength(2)
		expect(sets[0].data[0].x).toBe(1_700_000_000_000)
	})

	it('merges hwmon and GPU temps', () => {
		const sets = historyToTempDatasets(samples)
		expect(sets.map((s) => s.label).sort()).toEqual(['CPU', 'GPU RTX'])
	})
})
