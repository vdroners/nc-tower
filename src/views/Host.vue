<template>
	<div class="nc-tower-view">
		<h2>Host</h2>
		<p class="nc-tower-view__lead">
			Read-only host glance plus allowlisted service restarts. Editing users, firewall
			rules, cron and packages stays in Webmin.
		</p>

		<Section id="host.mounts"
			title="Mounts"
			:summary="mountSummary"
			:loading="loading.mounts"
			:error="errors.mounts"
			default-open
			@refresh="refresh('mounts')">
			<h4 class="nc-tower-subhead">Watched paths</h4>
			<DataTable :columns="watchedColumns" :rows="mounts.interesting || []" row-key="path" empty-text="None">
				<template #cell-used_pct="{ row }">
					<UsageBar v-if="!row.error" :percent="row.used_pct" />
					<span v-else class="nc-tower-bad">{{ row.error }}</span>
				</template>
				<template #cell-used_b="{ row }">{{ fmt.bytes(row.used_b) }} / {{ fmt.bytes(row.total_b) }}</template>
				<template #cell-fstype="{ row }">{{ row.mount ? row.mount.fstype : '—' }}</template>
				<template #cell-device="{ row }">{{ row.mount ? row.mount.device : '—' }}</template>
			</DataTable>
			<h4 class="nc-tower-subhead">All mounts</h4>
			<div class="nc-tower-toolbar">
				<NcCheckboxRadioSwitch :checked.sync="showAllMounts" type="switch">
					Show container and pseudo filesystems ({{ (mounts.mounts || []).length }} total)
				</NcCheckboxRadioSwitch>
			</div>
			<DataTable :columns="mountColumns"
				:rows="visibleMounts"
				default-sort="mountpoint"
				empty-text="None">
				<template #cell-options="{ row }">{{ (row.options || []).slice(0, 4).join(', ') }}</template>
			</DataTable>
		</Section>

		<Section id="host.packages"
			title="Package updates"
			:summary="packageSummary"
			:severity="packages.packages && packages.packages.length ? 'warn' : 'ok'"
			:loading="loading.packages"
			:error="errors.packages"
			@refresh="refresh('packages')">
			<NcNoteCard v-if="packages.unavailable" type="warning">Unavailable: {{ packages.reason || packages.error }}</NcNoteCard>
			<DataTable v-else
				:columns="packageColumns"
				:rows="packages.packages || []"
				row-key="name"
				default-sort="name"
				empty-text="Everything up to date" />
			<p class="nc-tower-muted">Applying updates stays in Webmin → Software Packages.</p>
		</Section>

		<Section id="host.proc"
			title="Top processes"
			:summary="`top ${(proc.processes || []).length} by CPU`"
			:loading="loading.proc"
			:error="errors.proc"
			@refresh="refresh('proc')">
			<DataTable :columns="procColumns"
				:rows="proc.processes || []"
				row-key="pid"
				default-sort="cpu"
				default-desc
				empty-text="None">
				<template #cell-rss_kb="{ row }">{{ fmt.bytes((row.rss_kb || 0) * 1024) }}</template>
				<template #cell-command="{ row }">
					<span class="nc-tower-cmd" :title="row.command">{{ row.command }}</span>
				</template>
			</DataTable>
			<p class="nc-tower-muted">Killing processes stays out of Control Tower.</p>
		</Section>

		<Section id="host.systemd"
			title="Services"
			:summary="systemdSummary"
			:severity="systemdSeverity"
			:loading="loading.systemd"
			:error="errors.systemd"
			default-open
			@refresh="refresh('systemd')">
			<NcNoteCard v-if="systemd.unavailable" type="warning">Unavailable: {{ systemd.reason }}</NcNoteCard>
			<DataTable v-else :columns="systemdColumns" :rows="systemd.units || []" row-key="unit" empty-text="None">
				<template #cell-active="{ row }">
					<span :class="row.active === 'active' ? 'nc-tower-good' : 'nc-tower-bad'">{{ row.active }}</span>
				</template>
				<template #cell-user="{ row }">{{ row.user ? 'user bus' : 'system' }}</template>
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton type="secondary" @click="askRestart(row.unit)">
							<template #icon><NcTowerIcon name="refresh" :size="18" /></template>
							Restart
						</NcButton>
					</div>
				</template>
			</DataTable>
			<p class="nc-tower-muted">Only units in NC_TOWER_SYSTEMD_ALLOW can be restarted.</p>
		</Section>

		<Section id="host.cron"
			title="Cron"
			:summary="`${(cron.root_crontab || []).length} root entries · ${(cron.cron_d_files || []).length} files in /etc/cron.d`"
			:loading="loading.cron"
			:error="errors.cron"
			@refresh="refresh('cron')">
			<NcNoteCard v-if="cron.error" type="warning">{{ cron.error }}</NcNoteCard>
			<h4 class="nc-tower-subhead">root crontab</h4>
			<ul class="nc-tower-list">
				<li v-for="(line, index) in cron.root_crontab || []" :key="index"><code>{{ line }}</code></li>
				<li v-if="!(cron.root_crontab || []).length" class="nc-tower-muted">empty</li>
			</ul>
			<h4 class="nc-tower-subhead">/etc/cron.d</h4>
			<ul class="nc-tower-list">
				<li v-for="file in cron.cron_d_files || []" :key="file">{{ file }}</li>
				<li v-if="!(cron.cron_d_files || []).length" class="nc-tower-muted">none</li>
			</ul>
			<p class="nc-tower-muted">Editing cron stays in Webmin.</p>
		</Section>

		<Section id="host.net"
			title="Network"
			:summary="ifaceSummary"
			:loading="loading.net"
			:error="errors.net"
			@refresh="refresh('net')">
			<div class="nc-tower-toolbar">
				<NcCheckboxRadioSwitch :checked.sync="showAllIfaces" type="switch">
					Show container interfaces ({{ (net.ifaces || []).length }} total)
				</NcCheckboxRadioSwitch>
			</div>
			<DataTable :columns="netColumns" :rows="visibleIfaces" row-key="name" default-sort="name" empty-text="None">
				<template #cell-addresses="{ row }">{{ fmt.addresses(row) || '—' }}</template>
				<template #cell-state="{ row }">
					<span :class="row.state === 'up' ? 'nc-tower-good' : 'nc-tower-muted'">{{ row.state || '—' }}</span>
				</template>
			</DataTable>
		</Section>

		<ConfirmDialog v-bind="confirm"
			:open="confirm.open"
			@cancel="confirm.open = false"
			@confirm="runConfirmed" />
	</div>
</template>

<script>
import { showError, showSuccess } from '@nextcloud/dialogs'
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcCheckboxRadioSwitch from '@nextcloud/vue/dist/Components/NcCheckboxRadioSwitch.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'

import ConfirmDialog from '../components/ConfirmDialog.vue'
import NcTowerIcon from '../components/NcTowerIcon.vue'
import DataTable from '../components/DataTable.vue'
import Section from '../components/Section.vue'
import UsageBar from '../components/UsageBar.vue'

import { get, post } from '../services/api.js'
import fmt from '../services/format.js'
import Poller from '../services/poll.js'

const PSEUDO_FS = new Set([
	'nsfs', 'overlay', 'squashfs', 'tmpfs', 'devtmpfs', 'proc', 'sysfs', 'cgroup', 'cgroup2',
	'devpts', 'mqueue', 'hugetlbfs', 'debugfs', 'tracefs', 'securityfs', 'pstore', 'bpf',
	'configfs', 'fusectl', 'binfmt_misc', 'autofs', 'ramfs', 'efivarfs',
])
const CONTAINER_IFACE = /^(veth|br-|docker|virbr)/

export default {
	name: 'Host',
	components: { ConfirmDialog, DataTable, NcTowerIcon, Section, UsageBar, NcButton, NcCheckboxRadioSwitch, NcNoteCard },
	data() {
		return {
			fmt,
			mounts: {},
			packages: {},
			proc: {},
			systemd: {},
			cron: {},
			net: {},
			loading: {},
			errors: {},
			showAllMounts: false,
			showAllIfaces: false,
			confirm: { open: false, title: '', message: '', confirmLabel: 'Confirm', phrase: '', danger: false },
			pendingAction: null,
			watchedColumns: [
				{ key: 'path', label: 'Path' },
				{ key: 'device', label: 'Device' },
				{ key: 'fstype', label: 'FS' },
				{ key: 'used_b', label: 'Used' },
				{ key: 'used_pct', label: 'Usage' },
			],
			mountColumns: [
				{ key: 'mountpoint', label: 'Mount point' },
				{ key: 'device', label: 'Device', mono: true },
				{ key: 'fstype', label: 'FS' },
				{ key: 'options', label: 'Options' },
			],
			packageColumns: [
				{ key: 'name', label: 'Package' },
				{ key: 'old_version', label: 'Installed' },
				{ key: 'new_version', label: 'Available' },
				{ key: 'suite', label: 'Suite' },
			],
			procColumns: [
				{ key: 'pid', label: 'PID', align: 'end' },
				{ key: 'user', label: 'User' },
				{ key: 'cpu', label: 'CPU %', align: 'end' },
				{ key: 'mem', label: 'Mem %', align: 'end' },
				{ key: 'rss_kb', label: 'RSS', align: 'end' },
				{ key: 'command', label: 'Command' },
			],
			systemdColumns: [
				{ key: 'unit', label: 'Unit' },
				{ key: 'active', label: 'Active' },
				{ key: 'enabled', label: 'Enabled' },
				{ key: 'user', label: 'Bus' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			netColumns: [
				{ key: 'name', label: 'Interface' },
				{ key: 'addresses', label: 'Addresses' },
				{ key: 'state', label: 'State' },
				{ key: 'mtu', label: 'MTU', align: 'end' },
			],
		}
	},
	computed: {
		// This host reports 213 mounts, 130 of them docker nsfs/overlay, and 70
		// interfaces, 61 of them veth/bridge. Showing everything by default made
		// both sections unreadable; the counts above the toggle keep it honest.
		visibleMounts() {
			const rows = this.mounts.mounts || []
			if (this.showAllMounts) {
				return rows
			}
			return rows.filter((row) => !PSEUDO_FS.has(row.fstype) && !String(row.fstype || '').startsWith('fuse.'))
		},
		visibleIfaces() {
			const rows = this.net.ifaces || []
			if (this.showAllIfaces) {
				return rows
			}
			return rows.filter((row) => !CONTAINER_IFACE.test(row.name || ''))
		},
		mountSummary() {
			const shown = this.visibleMounts.length
			const total = (this.mounts.mounts || []).length
			return shown === total ? `${total} filesystem(s)` : `${shown} of ${total} filesystem(s)`
		},
		ifaceSummary() {
			const shown = this.visibleIfaces.length
			const total = (this.net.ifaces || []).length
			return shown === total ? `${total} interface(s)` : `${shown} of ${total} interface(s)`
		},
		packageSummary() {
			const count = (this.packages.packages || []).length
			return count ? `${count} upgradable` : 'up to date'
		},
		systemdSummary() {
			const units = this.systemd.units || []
			return units.length ? `${units.filter((u) => u.active === 'active').length}/${units.length} active` : ''
		},
		systemdSeverity() {
			const units = this.systemd.units || []
			return units.some((u) => u.active !== 'active') ? 'warn' : 'ok'
		},
	},
	created() {
		// Not in data(): observing timer handles and a Map buys nothing.
		this.poller = new Poller()
		const p = this.poller
		p.add('proc', () => this.fetch('proc', '/tower/proc'), 15000)
		p.add('systemd', () => this.fetch('systemd', '/tower/systemd'), 30000)
		p.add('net', () => this.fetch('net', '/tower/net'), 60000)
		p.add('mounts', () => this.fetch('mounts', '/tower/mounts'), 60000)
		p.add('cron', () => this.fetch('cron', '/tower/cron'), 300000)
		p.add('packages', () => this.fetch('packages', '/tower/packages'), 300000)
		p.start()
	},
	beforeDestroy() {
		this.poller.stop()
	},
	methods: {
		/**
		 * @param {string} [name] section to refresh; omit for all
		 * @return {Promise<void>} resolves once the loaders settle
		 */
		refresh(name) {
			return this.poller.refresh(name)
		},
		async fetch(key, path) {
			this.$set(this.loading, key, true)
			try {
				this[key] = await get(path)
				this.$set(this.errors, key, '')
			} catch (error) {
				this.$set(this.errors, key, error.message)
			} finally {
				this.$set(this.loading, key, false)
			}
		},
		askRestart(unit) {
			this.confirm = {
				open: true,
				title: 'Restart service',
				message: `Restart ${unit} on the host?`,
				confirmLabel: 'Restart',
				phrase: '',
				danger: true,
			}
			this.pendingAction = () => this.restart(unit)
		},
		async runConfirmed() {
			const action = this.pendingAction
			this.confirm.open = false
			this.pendingAction = null
			if (action) {
				await action()
			}
		},
		async restart(unit) {
			try {
				const result = await post('/tower/systemd/restart', { unit })
				if (result.ok === false) {
					showError(result.error || result.stderr || 'Restart failed')
				} else {
					showSuccess(`Restarted ${unit}`)
				}
			} catch (error) {
				showError(error.message)
			} finally {
				await this.poller.refresh('systemd')
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-subhead {
	margin: 16px 0 6px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.nc-tower-list {
	margin: 0;
	padding-inline-start: 18px;

	code {
		font-size: 0.85em;
		overflow-wrap: anywhere;
	}
}

.nc-tower-cmd {
	display: inline-block;
	max-width: 46ch;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	vertical-align: bottom;
}

.nc-tower-good { color: var(--color-success); }
.nc-tower-bad { color: var(--color-error); }
</style>
