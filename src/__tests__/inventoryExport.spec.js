/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest'
import { flattenDisks, flattenStorageTree, inventoryMarkdown } from '../services/inventoryExport.js'

describe('inventoryExport', () => {
	it('flattens lsblk tree to disk rows', () => {
		const rows = flattenDisks([
			{
				name: 'nvme0n1',
				type: 'disk',
				size: 1000,
				serial: 'S1',
				children: [{ name: 'nvme0n1p1', type: 'part', mountpoint: '/' }],
			},
		])
		expect(rows).toHaveLength(1)
		expect(rows[0].name).toBe('nvme0n1')
		expect(rows[0].serial).toBe('S1')
	})

	it('flattens storage tree with partitions', () => {
		const rows = flattenStorageTree([
			{
				name: 'nvme0n1',
				type: 'disk',
				size: 1000,
				serial: 'S1',
				children: [{ name: 'nvme0n1p1', type: 'part', mountpoint: '/', size: 500 }],
			},
		])
		expect(rows).toHaveLength(2)
		expect(rows[1].name).toBe('nvme0n1p1')
		expect(rows[1].depth).toBe(1)
		expect(rows[1].mountpoint).toBe('/')
	})

	it('renders markdown with board + dimm lines', () => {
		const md = inventoryMarkdown(
			{
				dmi: { board_vendor: 'ASUS', board_name: 'X', product_serial: 'SN1' },
				cpu: { model: 'AMD', cpus: '16', governor: 'powersave' },
				os: { pretty_name: 'Ubuntu', hostname: 'lab', uname: 'Linux', last_boot: 't0', taint: { flags: [] } },
				dimms: { items: [{ locator: 'DIMM1', size: '32 GB', type: 'DDR4', speed: '3200', part_number: 'P' }] },
			},
			{ lsblk: { blockdevices: [{ name: 'sda', type: 'disk', serial: 'ABC', size: 1 }] } },
		)
		expect(md).toContain('# Host inventory')
		expect(md).toContain('ASUS')
		expect(md).toContain('DIMM1')
		expect(md).toContain('sda')
	})
})
