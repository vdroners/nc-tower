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
				<h4 class="nc-tower-subhead">DIMMs</h4>
				<NcNoteCard v-if="hardware.dimms?.unavailable" type="warning">{{ hardware.dimms.reason }}</NcNoteCard>
				<DataTable v-else :columns="dimmColumns" :rows="hardware.dimms?.items || []" empty-text="No modules" />
				<details class="nc-tower-details">
					<summary>PCIe devices ({{ (hardware.pcie?.items || []).length }})</summary>
					<DataTable :columns="pcieColumns" :rows="hardware.pcie?.items || []" empty-text="None" />
				</details>
				<details class="nc-tower-details">
					<summary>USB devices ({{ (hardware.usb?.items || []).length }})</summary>
					<DataTable :columns="usbColumns" :rows="hardware.usb?.items || []" empty-text="None" />
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
			<DataTable v-else
				:columns="tempColumns"
				:rows="temperatures.sensors || []"
				default-sort="celsius"
				default-desc
				empty-text="No sensors" />
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
import {
	copyText,
	downloadJson,
	flattenDisks,
	flattenStorageTree,
	inventoryMarkdown,
} from '../services/inventoryExport.js'

export default {
	name: 'HostInventoryPanels',
	components: { DataTable, Section, NcButton, NcNoteCard },
	props: {
		capabilities: { type: Array, default: () => [] },
		hardware: { type: Object, default: () => ({}) },
		storage: { type: Object, default: () => ({}) },
		temperatures: { type: Object, default: () => ({}) },
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
</style>
