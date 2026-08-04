<template>
	<div class="nc-tower-host-inventory">
		<Section id="host.hardware"
			title="Hardware"
			:summary="hardwareSummary"
			:loading="loading.hardware"
			:error="errors.hardware"
			default-open
			@refresh="$emit('refresh', 'hardware')">
			<NcNoteCard v-if="!hasCap('hardware')" type="info">
				Sidecar update needed for hardware inventory (capability <code>hardware</code>).
			</NcNoteCard>
			<template v-else>
				<div class="nc-tower-toolbar">
					<NcButton type="secondary" @click="copyMd">Copy as Markdown</NcButton>
					<NcButton type="tertiary" @click="download">Download JSON</NcButton>
				</div>
				<dl class="nc-tower-facts">
					<dt>Board</dt><dd>{{ boardLabel }}</dd>
					<dt>BIOS</dt><dd>{{ biosLabel }}</dd>
					<dt>Product / serial</dt><dd>{{ productLabel }}</dd>
					<dt>CPU</dt><dd>{{ cpuLabel }}</dd>
					<dt>OS / kernel</dt><dd>{{ osLabel }}</dd>
					<dt>Last boot</dt><dd>{{ hardware.os?.last_boot || '—' }}</dd>
					<dt>Kernel taint</dt>
					<dd>
						<span :class="hardware.os?.taint?.hardware_tainted ? 'nc-tower-bad' : 'nc-tower-muted'">
							{{ taintLabel }}
						</span>
					</dd>
				</dl>
				<div v-if="hardware.cpu" class="nc-tower-chips nc-tower-host-inventory__cpu-chips">
					<span v-if="hardware.cpu.sockets != null" class="nc-tower-chip">{{ hardware.cpu.sockets }} socket{{ hardware.cpu.sockets === 1 ? '' : 's' }}</span>
					<span v-if="hardware.cpu.cpus != null" class="nc-tower-chip">{{ hardware.cpu.cpus }} threads</span>
					<span v-if="hardware.cpu.mhz_current_avg != null" class="nc-tower-chip">{{ hardware.cpu.mhz_current_avg }} MHz avg</span>
					<span v-if="cpuGovernorLabel" class="nc-tower-chip">gov {{ cpuGovernorLabel }}</span>
				</div>
				<h4 class="nc-tower-subhead">DIMMs</h4>
				<NcNoteCard v-if="hardware.dimms?.unavailable" type="warning">{{ hardware.dimms.reason }}</NcNoteCard>
				<div v-else class="nc-tower-dimm-grid">
					<div v-for="(slot, idx) in dimmSlots"
						:key="slot.locator || idx"
						class="nc-tower-dimm-slot"
						:class="{ 'nc-tower-dimm-slot--empty': slot.empty }">
						<div class="nc-tower-dimm-slot__locator">{{ slot.locator || `Slot ${idx + 1}` }}</div>
						<template v-if="slot.empty">
							<div class="nc-tower-dimm-slot__empty">Empty</div>
						</template>
						<template v-else>
							<div class="nc-tower-dimm-slot__size">{{ slot.size }}</div>
							<div class="nc-tower-dimm-slot__meta">{{ [slot.type, slot.speed].filter(Boolean).join(' · ') }}</div>
						</template>
					</div>
					<p v-if="!dimmSlots.length" class="nc-tower-muted">No modules</p>
				</div>
				<details class="nc-tower-details">
					<summary>DIMM table (raw)</summary>
					<DataTable :columns="dimmColumns" :rows="dimmSlots.filter((d) => !d.empty)" empty-text="No modules" />
				</details>
				<details class="nc-tower-details">
					<summary>PCIe devices ({{ (hardware.pcie?.items || []).length }})</summary>
					<DataTable :columns="pcieColumns" :rows="hardware.pcie?.items || []" empty-text="None">
						<template #cell-class="{ row }">
							<span v-if="pcieClassBadge(row.class)" class="nc-tower-chip nc-tower-chip--class">{{ pcieClassBadge(row.class) }}</span>
							<span v-else>{{ row.class || '—' }}</span>
						</template>
					</DataTable>
				</details>
				<details class="nc-tower-details">
					<summary>USB devices ({{ (hardware.usb?.items || []).length }})</summary>
					<DataTable :columns="usbColumns" :rows="hardware.usb?.items || []" empty-text="None">
						<template #cell-name="{ row }">
							<span class="nc-tower-host-inventory__usb-name">{{ row.name }}</span>
						</template>
					</DataTable>
				</details>
			</template>
		</Section>

		<Section id="host.storage-topology"
			title="Storage"
			:summary="storageSummary"
			:severity="storageSeverity"
			:loading="loading.storage"
			:error="errors.storage"
			@refresh="$emit('refresh', 'storage')">
			<NcNoteCard v-if="!hasCap('storage-topology')" type="info">
				Sidecar update needed for storage topology.
			</NcNoteCard>
			<template v-else>
				<span class="nc-tower-chip" :class="storage.raid?.degraded ? 'nc-tower-chip--warn' : 'nc-tower-chip--ok'">
					RAID {{ storage.raid?.degraded ? 'degraded' : ((storage.raid?.arrays || []).length ? 'ok' : 'none') }}
				</span>
				<div v-if="storageDiskMaps.length" class="nc-tower-storage-map">
					<div v-for="disk in storageDiskMaps" :key="disk.name" class="nc-tower-storage-disk">
						<div class="nc-tower-storage-disk__header">
							<strong>{{ disk.name }}</strong>
							<span class="nc-tower-muted">{{ disk.model || '—' }}</span>
							<span>{{ formatBytes(disk.size) }}</span>
							<span v-if="disk.isRaid" class="nc-tower-chip nc-tower-chip--class">RAID</span>
						</div>
						<div class="nc-tower-storage-disk__bar">
							<div v-for="(seg, si) in disk.segments"
								:key="`${disk.name}-${si}`"
								class="nc-tower-storage-disk__seg"
								:class="`nc-tower-storage-disk__seg--${si % 4}`"
								:style="{ flexGrow: seg.bytes }"
								:title="seg.label">
								<span v-if="seg.pct >= 8" class="nc-tower-storage-disk__seg-label">{{ seg.label }}</span>
							</div>
						</div>
					</div>
				</div>
				<DataTable :columns="diskColumns" :rows="diskRows" row-key="name" empty-text="No disks">
					<template #cell-size="{ row }">{{ row.size_h || row.size || '—' }}</template>
				</DataTable>
				<h4 v-if="(storage.nvme_temps || []).length" class="nc-tower-subhead">NVMe temps</h4>
				<DataTable v-if="(storage.nvme_temps || []).length"
					:columns="nvmeColumns"
					:rows="storage.nvme_temps || []"
					row-key="device"
					empty-text="None" />
			</template>
		</Section>

		<Section id="host.temperatures"
			title="Temperatures"
			:summary="`${(temperatures.sensors || []).length} sensor(s)`"
			:loading="loading.temperatures"
			:error="errors.temperatures"
			@refresh="$emit('refresh', 'temperatures')">
			<NcNoteCard v-if="!hasCap('temperatures')" type="info">Sidecar update needed for temperatures.</NcNoteCard>
			<template v-else>
				<TempStrip :sensors="temperatures.sensors || []" />
				<TowerChart v-if="(tempHistory.samples || []).length"
					:datasets="tempHistoryDatasets"
					:height="180"
					y-suffix="°C"
					time-axis
					title="Package temperature (24h)" />
				<details class="nc-tower-details">
					<summary>Sensor table (raw)</summary>
					<DataTable :columns="tempColumns"
						:rows="temperatures.sensors || []"
						default-sort="celsius"
						default-desc
						empty-text="No sensors" />
				</details>
			</template>
		</Section>

		<Section id="host.security"
			title="Security"
			:summary="postureSummary"
			:severity="postureSeverity"
			:loading="loading.posture"
			:error="errors.posture"
			@refresh="$emit('refresh', 'posture')">
			<NcNoteCard v-if="!hasCap('posture')" type="info">Sidecar update needed for host security posture.</NcNoteCard>
			<template v-else>
				<div class="nc-tower-chips">
					<span class="nc-tower-chip" :class="posture.ntp?.synchronized ? 'nc-tower-chip--ok' : 'nc-tower-chip--warn'">
						NTP {{ posture.ntp?.synchronized ? 'synced' : (posture.ntp?.unavailable ? 'n/a' : 'unsynced') }}
					</span>
					<span class="nc-tower-chip">failed SSH 24h: {{ posture.failed_ssh_24h ?? '—' }}</span>
				</div>
				<h4 class="nc-tower-subhead">Logged in</h4>
				<DataTable :columns="whoColumns" :rows="posture.users || []" empty-text="Nobody" />
				<h4 class="nc-tower-subhead">Recent logins</h4>
				<ul class="nc-tower-list">
					<li v-for="(row, i) in posture.recent_logins || []" :key="i"><code>{{ row.line }}</code></li>
					<li v-if="!(posture.recent_logins || []).length" class="nc-tower-muted">none</li>
				</ul>
				<h4 class="nc-tower-subhead">TLS certificates</h4>
				<DataTable :columns="certColumns" :rows="posture.certs || []" empty-text="No HTTPS targets">
					<template #cell-days_left="{ row }">
						<span :class="row.days_left != null && row.days_left < 21 ? 'nc-tower-bad' : ''">
							{{ row.days_left != null ? row.days_left : (row.error || '—') }}
						</span>
					</template>
				</DataTable>
			</template>
		</Section>

		<Section id="host.kernel-log"
			title="Kernel log"
			:summary="kernelSummary"
			:severity="kernelSeverity"
			:loading="loading.kernelLog"
			:error="errors.kernelLog"
			@refresh="$emit('refresh', 'kernelLog')">
			<NcNoteCard v-if="!hasCap('kernel-log')" type="info">Sidecar update needed for kernel log.</NcNoteCard>
			<template v-else>
				<div class="nc-tower-chips">
					<span v-for="tag in (kernelLog.tags_seen || [])" :key="tag" class="nc-tower-chip nc-tower-chip--warn">{{ tag }}</span>
				</div>
				<DataTable :columns="kernelColumns" :rows="kernelLog.rows || []" empty-text="No warnings">
					<template #cell-tags="{ row }">{{ (row.tags || []).join(', ') || '—' }}</template>
					<template #cell-message="{ row }">
						<span class="nc-tower-cmd" :title="row.message">{{ row.message }}</span>
					</template>
				</DataTable>
			</template>
		</Section>
	</div>
</template>

<script>
import { showError, showSuccess } from '@nextcloud/dialogs'
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import DataTable from './DataTable.vue'
import Section from './Section.vue'
import TempStrip from './TempStrip.vue'
import TowerChart from './TowerChart.vue'
import {
	copyText,
	downloadJson,
	flattenDisks,
	flattenStorageTree,
	inventoryMarkdown,
} from '../services/inventoryExport.js'

export default {
	name: 'HostInventoryPanels',
	components: { DataTable, Section, NcButton, NcNoteCard, TempStrip, TowerChart },
	props: {
		capabilities: { type: Array, default: () => [] },
		hardware: { type: Object, default: () => ({}) },
		storage: { type: Object, default: () => ({}) },
		temperatures: { type: Object, default: () => ({}) },
		tempHistory: { type: Object, default: () => ({}) },
		posture: { type: Object, default: () => ({}) },
		kernelLog: { type: Object, default: () => ({}) },
		loading: { type: Object, default: () => ({}) },
		errors: { type: Object, default: () => ({}) },
	},
	data() {
		return {
			dimmColumns: [
				{ key: 'locator', label: 'Slot' },
				{ key: 'size', label: 'Size' },
				{ key: 'type', label: 'Type' },
				{ key: 'speed', label: 'Speed' },
				{ key: 'part_number', label: 'Part' },
				{ key: 'manufacturer', label: 'Mfr' },
			],
			pcieColumns: [
				{ key: 'slot', label: 'Slot' },
				{ key: 'class', label: 'Class' },
				{ key: 'vendor', label: 'Vendor' },
				{ key: 'device', label: 'Device' },
			],
			usbColumns: [
				{ key: 'bus', label: 'Bus' },
				{ key: 'device', label: 'Dev' },
				{ key: 'id', label: 'ID' },
				{ key: 'name', label: 'Name' },
			],
			diskColumns: [
				{ key: 'name_indented', label: 'Name' },
				{ key: 'type', label: 'Type' },
				{ key: 'size', label: 'Size' },
				{ key: 'model', label: 'Model' },
				{ key: 'serial', label: 'Serial' },
				{ key: 'uuid', label: 'UUID', mono: true },
				{ key: 'fstype', label: 'FS' },
				{ key: 'mountpoint', label: 'Mount' },
			],
			nvmeColumns: [
				{ key: 'device', label: 'Device' },
				{ key: 'model', label: 'Model' },
				{ key: 'temp_c', label: '°C', align: 'end' },
				{ key: 'serial', label: 'Serial' },
			],
			tempColumns: [
				{ key: 'source', label: 'Source' },
				{ key: 'label', label: 'Label' },
				{ key: 'chip', label: 'Chip' },
				{ key: 'celsius', label: '°C', align: 'end' },
			],
			whoColumns: [
				{ key: 'user', label: 'User' },
				{ key: 'tty', label: 'TTY' },
				{ key: 'since', label: 'Since' },
				{ key: 'host', label: 'From' },
			],
			certColumns: [
				{ key: 'name', label: 'Service' },
				{ key: 'host', label: 'Host' },
				{ key: 'days_left', label: 'Days left', align: 'end' },
				{ key: 'expires_at', label: 'Expires' },
			],
			kernelColumns: [
				{ key: 'tags', label: 'Tags' },
				{ key: 'priority', label: 'Pri' },
				{ key: 'message', label: 'Message' },
			],
		}
	},
	computed: {
		boardLabel() {
			const d = this.hardware.dmi || {}
			return [d.board_vendor, d.board_name, d.board_version].filter(Boolean).join(' ') || '—'
		},
		biosLabel() {
			const d = this.hardware.dmi || {}
			return [d.bios_vendor, d.bios_version, d.bios_date && `(${d.bios_date})`].filter(Boolean).join(' ') || '—'
		},
		productLabel() {
			const d = this.hardware.dmi || {}
			return [d.sys_vendor, d.product_name, d.product_serial && `· ${d.product_serial}`].filter(Boolean).join(' ') || '—'
		},
		cpuLabel() {
			const c = this.hardware.cpu || {}
			const gov = Array.isArray(c.governor) ? c.governor.join(',') : c.governor
			return [c.model, c.cpus && `${c.cpus} thr`, gov && `gov ${gov}`, c.mhz_current_avg != null && `${c.mhz_current_avg} MHz`]
				.filter(Boolean).join(' · ') || '—'
		},
		cpuGovernorLabel() {
			const g = this.hardware.cpu?.governor
			if (Array.isArray(g)) {
				return g.join(', ')
			}
			return g || ''
		},
		dimmSlots() {
			const items = this.hardware.dimms?.items
				?? this.hardware.memory?.dimms
				?? []
			return items.map((d) => ({ ...d, empty: this.isDimmEmpty(d) }))
		},
		raidDiskNames() {
			const names = new Set()
			for (const arr of this.storage.raid?.arrays || []) {
				if (arr.name) {
					names.add(arr.name)
				}
				for (const m of arr.members || []) {
					if (m.name) {
						names.add(m.name)
					}
				}
			}
			return names
		},
		storageDiskMaps() {
			const disks = (this.storage.lsblk?.blockdevices || []).filter((d) => d.type === 'disk')
			return disks.map((disk) => ({
				...disk,
				isRaid: this.raidDiskNames.has(disk.name),
				segments: this.diskSegments(disk),
			}))
		},
		tempHistoryDatasets() {
			const samples = this.tempHistory.samples || []
			const at = (row) => new Date(row.ts).getTime()
			return [{
				label: 'Package °C',
				data: samples
					.filter((r) => r.package_temp_c != null)
					.map((r) => ({ x: at(r), y: r.package_temp_c })),
				fill: true,
			}]
		},
		osLabel() {
			const o = this.hardware.os || {}
			return [o.pretty_name, o.hostname].filter(Boolean).join(' · ') || '—'
		},
		taintLabel() {
			const t = this.hardware.os?.taint
			if (!t || t.unavailable) {
				return '—'
			}
			return (t.flags || []).length ? t.flags.join(', ') : 'clean'
		},
		hardwareSummary() {
			if (!this.hasCap('hardware')) {
				return 'sidecar update'
			}
			return this.hardware.dmi?.board_name || this.hardware.cpu?.model || ''
		},
		diskRows() {
			return flattenStorageTree(this.storage.lsblk?.blockdevices || [])
		},
		storageSummary() {
			const disks = flattenDisks(this.storage.lsblk?.blockdevices || [])
			return disks.length ? `${disks.length} disk(s)` : ''
		},
		storageSeverity() {
			return this.storage.raid?.degraded ? 'crit' : 'ok'
		},
		postureSummary() {
			const users = (this.posture.users || []).length
			return `${users} logged in · SSH fails ${this.posture.failed_ssh_24h ?? '—'}`
		},
		postureSeverity() {
			if (this.posture.ntp && this.posture.ntp.unavailable !== true && this.posture.ntp.synchronized === false) {
				return 'warn'
			}
			const expiring = (this.posture.certs || []).some((c) => c.days_left != null && c.days_left < 21)
			return expiring ? 'warn' : 'ok'
		},
		kernelSummary() {
			const n = (this.kernelLog.rows || []).length
			const tags = (this.kernelLog.tags_seen || []).join(', ')
			return tags ? `${n} · ${tags}` : `${n} warning(s)`
		},
		kernelSeverity() {
			const tags = this.kernelLog.tags_seen || []
			if (tags.includes('mce') || tags.includes('oom')) {
				return 'crit'
			}
			return tags.length ? 'warn' : 'ok'
		},
	},
	methods: {
		hasCap(name) {
			return (this.capabilities || []).includes(name)
		},
		isDimmEmpty(d) {
			const size = String(d?.size || '').trim().toLowerCase()
			return !size
				|| size.includes('no module')
				|| size === 'unknown'
				|| size === 'empty'
				|| size === 'not installed'
		},
		pcieClassBadge(cls) {
			const c = String(cls || '').toLowerCase()
			if (/vga|3d controller|display/.test(c)) {
				return 'GPU'
			}
			if (/non-volatile|nvme/.test(c)) {
				return 'NVMe'
			}
			if (/ethernet|network controller/.test(c)) {
				return 'NIC'
			}
			return ''
		},
		formatBytes(bytes) {
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
		},
		diskSegments(disk) {
			const total = Number(disk.size) || 0
			const children = (disk.children || []).filter((c) => c.type === 'part' || c.type === 'partition')
			if (!total || !children.length) {
				return total ? [{ bytes: total, pct: 100, label: 'unpartitioned' }] : []
			}
			const segs = children.map((c) => {
				const bytes = Number(c.size) || 0
				const label = [c.fstype, c.mountpoint].filter(Boolean).join(' · ') || c.name || '?'
				return {
					bytes,
					pct: total ? (bytes / total) * 100 : 0,
					label,
				}
			})
			const used = segs.reduce((sum, s) => sum + s.bytes, 0)
			if (used < total) {
				segs.push({
					bytes: total - used,
					pct: ((total - used) / total) * 100,
					label: 'free',
				})
			}
			return segs.filter((s) => s.bytes > 0)
		},
		async copyMd() {
			try {
				await copyText(inventoryMarkdown(this.hardware, this.storage))
				showSuccess('Inventory copied as Markdown')
			} catch (err) {
				showError(err.message || 'Copy failed')
			}
		},
		download() {
			downloadJson({ hardware: this.hardware, storage: this.storage }, 'host-inventory.json')
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-details {
	margin: 10px 0;
}
.nc-tower-chip--ok {
	color: var(--color-success);
}
.nc-tower-chip--warn {
	color: var(--color-warning);
}
.nc-tower-chip--class {
	font-size: 0.8em;
	background: var(--color-background-hover);
}
.nc-tower-host-inventory__cpu-chips {
	margin: 8px 0 12px;
}
.nc-tower-host-inventory__usb-name {
	padding-left: 0.5em;
}
.nc-tower-dimm-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
	gap: 8px;
	margin-bottom: 8px;
}
.nc-tower-dimm-slot {
	padding: 10px;
	border-radius: var(--border-radius-large, 8px);
	border: 1px solid var(--color-border);
	background: var(--color-main-background);
	&--empty {
		border-style: dashed;
		background: var(--color-background-dark);
		opacity: 0.75;
	}
	&__locator {
		font-size: 0.8em;
		color: var(--color-text-maxcontrast);
		margin-bottom: 4px;
	}
	&__size {
		font-weight: 600;
	}
	&__meta {
		font-size: 0.85em;
		color: var(--color-text-maxcontrast);
	}
	&__empty {
		font-size: 0.85em;
		color: var(--color-text-maxcontrast);
		font-style: italic;
	}
}
.nc-tower-storage-map {
	display: flex;
	flex-direction: column;
	gap: 12px;
	margin: 10px 0 14px;
}
.nc-tower-storage-disk {
	&__header {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 8px;
		margin-bottom: 6px;
		font-size: 0.9em;
	}
	&__bar {
		display: flex;
		height: 28px;
		border-radius: var(--border-radius, 4px);
		overflow: hidden;
		background: var(--color-background-dark);
		border: 1px solid var(--color-border);
	}
	&__seg {
		display: flex;
		align-items: center;
		justify-content: center;
		min-width: 2px;
		overflow: hidden;
		&--0 { background: var(--color-primary-element); }
		&--1 { background: var(--color-success); }
		&--2 { background: var(--color-warning); }
		&--3 { background: var(--color-text-maxcontrast); opacity: 0.55; }
	}
	&__seg-label {
		font-size: 0.7em;
		padding: 0 4px;
		color: var(--color-primary-text, #fff);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
}
</style>
