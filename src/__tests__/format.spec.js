import { describe, it, expect } from 'vitest'
import fmt from '../services/format.js'

/**
 * Every formatter here exists because a payload arrived in more than one shape.
 * The cases below are the shapes actually observed from this host's sidecar and
 * Docker CLI, not invented ones.
 */

describe('bytes', () => {
	it.each([
		[0, '0 B'],
		[1023, '1023 B'],
		[1024, '1.0 KB'],
		[1536, '1.5 KB'],
		[1073741824, '1.0 GB'],
	])('formats %i as %s', (input, expected) => {
		expect(fmt.bytes(input)).toBe(expected)
	})

	it('treats junk as zero rather than NaN', () => {
		expect(fmt.bytes(undefined)).toBe('0 B')
		expect(fmt.bytes('nonsense')).toBe('0 B')
	})
})

describe('ports', () => {
	it('summarises the docker CLI string form', () => {
		expect(fmt.ports('127.0.0.1:18791->8080/tcp')).toBe('127.0.0.1:18791->8080/tcp')
	})

	it('caps a long list and says how many are hidden', () => {
		expect(fmt.ports('1->1/tcp, 2->2/tcp, 3->3/tcp, 4->4/tcp')).toBe('1->1/tcp, 2->2/tcp +2')
	})

	it('accepts the array form some docker versions emit', () => {
		expect(fmt.ports(['8080/tcp', '9090/tcp'])).toBe('8080/tcp, 9090/tcp')
	})

	it('renders an em dash when there are no ports', () => {
		expect(fmt.ports('')).toBe('—')
		expect(fmt.ports(null)).toBe('—')
	})
})

describe('addresses', () => {
	it('prefers IPv4 from the `ip -j addr` object form', () => {
		const iface = {
			name: 'eno1',
			addresses: [
				{ family: 'inet6', address: 'fe80::1', prefixlen: 64 },
				{ family: 'inet', address: '10.0.0.84', prefixlen: 24 },
			],
		}
		expect(fmt.addresses(iface)).toBe('10.0.0.84/24')
	})

	it('falls back to all addresses when there is no IPv4', () => {
		const iface = { name: 'x', addresses: [{ address: 'fe80::1', prefixlen: 64 }] }
		expect(fmt.addresses(iface)).toBe('fe80::1/64')
	})

	it('handles an interface with no addresses', () => {
		expect(fmt.addresses({ name: 'veth123', addresses: [] })).toBe('')
		expect(fmt.addresses(null)).toBe('')
	})
})

describe('meminfo', () => {
	it('converts the /proc/meminfo kB form', () => {
		expect(fmt.meminfo('16299764 kB')).toBe('15.5 GB')
	})

	it('passes through anything it cannot parse', () => {
		expect(fmt.meminfo('')).toBe('—')
		expect(fmt.meminfo('unknown')).toBe('unknown')
	})
})

describe('duration and years', () => {
	it('formats uptime compactly', () => {
		expect(fmt.duration(90)).toBe('1m')
		expect(fmt.duration(3660)).toBe('1h 1m')
		expect(fmt.duration(90000)).toBe('1d 1h')
	})

	it('converts power-on hours to years', () => {
		expect(fmt.years(60404)).toBe('6.9 y')
		expect(fmt.years(null)).toBe('—')
	})
})
