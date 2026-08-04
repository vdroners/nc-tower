<template>
	<div class="nc-tower-view">
		<h2>Host</h2>
		<p class="nc-tower-view__lead">
			Physical host inventory, allowlisted service restarts, and package updates.
			Nextcloud-container facts live on the System tab.
		</p>

		<HostInventoryPanels
			:capabilities="capabilities"
			:hardware="hardware"
			:storage="storageTopo"
			:temperatures="temperatures"
			:posture="posture"
			:kernel-log="kernelLog"
			:loading="loading"
			:errors="errors"
			@refresh="refresh" />

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

		<Section id="host.updates"
			title="Updates"
			:summary="updateSummary"
			:severity="updateSeverity"
			:loading="loading.updates"
			:error="errors.updates"
			default-open
			@refresh="refresh('updates')">
			<NcNoteCard v-if="updates.unavailable" type="warning">apt is not reachable from the sidecar.</NcNoteCard>
			<template v-else>
				<NcNoteCard v-if="updates.reboot_required" type="error">
					A reboot is required{{ updates.reboot_packages.length ? ` (${updates.reboot_packages.join(', ')})` : '' }}.
					NC Tower never reboots the host — do it deliberately.
				</NcNoteCard>
				<NcNoteCard v-if="(updates.restarts_docker || []).length" type="warning">
					{{ updates.restarts_docker.join(', ') }} will restart the Docker daemon, bouncing
					<strong>every container on this host</strong> — including this app's sidecar. The
					upgrade runs detached under the host's systemd so it survives that.
				</NcNoteCard>

				<DataTable :columns="packageColumns"
					:rows="updates.packages || []"
					row-key="name"
					default-sort="name"
					empty-text="Everything up to date" />

				<div class="nc-tower-toolbar">
					<NcButton type="secondary" :disabled="jobBusy" @click="startUpdate('apt-dry-run')">
						<template #icon><NcTowerIcon name="search" :size="18" /></template>
						Dry run
					</NcButton>
					<NcButton type="error"
						:disabled="jobBusy || !(updates.packages || []).length"
						@click="askUpdate">
						<template #icon><NcTowerIcon name="download" :size="18" /></template>
						Install {{ (updates.packages || []).length }} update(s)
					</NcButton>
				</div>
				<JobPanel :job="job" @dismiss="job = null" />
			</template>
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
			<p class="nc-tower-muted">Killing processes stays out of NC Tower.</p>
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

		<Section id="host.load"
			title="Memory trend"
			:summary="historySummary"
			:loading="loading.history"
			:error="errors.history"
			@refresh="refresh('history')">
			<TowerChart :datasets="historyDatasets"
				:height="200"
				y-suffix="%"
				:y-max="100"
				time-axis
				show-legend
				title="Memory and swap" />
			<p class="nc-tower-muted">
				Recorded by the host every 15 minutes ({{ (history.samples || []).length }} samples shown).
			</p>
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
import HostInventoryPanels from '../components/HostInventoryPanels.vue'
import JobPanel from '../components/JobPanel.vue'
import TowerChart from '../components/TowerChart.vue'
import NcTowerIcon from '../components/NcTowerIcon.vue'
import DataTable from '../components/DataTable.vue'
import Section from '../components/Section.vue'
import UsageBar from '../components/UsageBar.vue'

import { get, post as postJson } from '../services/api.js'
import { runJob } from '../services/jobs.js'
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
	components: {
		ConfirmDialog, DataTable, HostInventoryPanels, JobPanel, NcTowerIcon,
		Section, TowerChart, UsageBar, NcButton, NcCheckboxRadioSwitch, NcNoteCard,
	},
	data() {
		return {
			fmt,
			capabilities: [],
			hardware: {},
			storageTopo: {},
			temperatures: {},
			posture: {},
			kernelLog: {},
			mounts: {},
			packages: {},
			updates: {},
			history: {},
			job: null,
			jobBusy: false,
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
		updateSummary() {
			const count = (this.updates.packages || []).length
			if (this.updates.reboot_required) {
				return `${count} pending · reboot required`
			}
			return count ? `${count} update(s) pending` : 'up to date'
		},
		updateSeverity() {
			if (this.updates.reboot_required) {
				return 'crit'
			}
			return (this.updates.packages || []).length ? 'warn' : 'ok'
		},
		historySummary() {
			const samples = this.history.samples || []
			if (!samples.length) {
				return ''
			}
			return `latest ${samples[samples.length - 1].mem_pct}% memory used`
		},
		historyDatasets() {
			const samples = this.history.samples || []
			const at = (row) => new Date(row.ts).getTime()
			return [
				{ label: 'Memory %', data: samples.map((r) => ({ x: at(r), y: r.mem_pct })), fill: true },
				{ label: 'Swap %', data: samples.map((r) => ({ x: at(r), y: r.swap_pct })) },
			]
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
		p.add('health', () => this.fetchHealthCaps(), 300000)
		p.add('hardware', () => this.fetch('hardware', '/tower/hardware'), 300000)
		p.add('storage', () => this.fetch('storageTopo', '/tower/storage', null, 'storage'), 120000)
		p.add('temperatures', () => this.fetch('temperatures', '/tower/temperatures'), 60000)
		p.add('posture', () => this.fetch('posture', '/tower/posture'), 120000)
		p.add('kernelLog', () => this.fetch('kernelLog', '/tower/kernel-log', { minutes: 60 }), 120000)
		p.add('proc', () => this.fetch('proc', '/tower/proc'), 15000)
		p.add('systemd', () => this.fetch('systemd', '/tower/systemd'), 30000)
		p.add('net', () => this.fetch('net', '/tower/net'), 60000)
		p.add('mounts', () => this.fetch('mounts', '/tower/mounts'), 60000)
		p.add('cron', () => this.fetch('cron', '/tower/cron'), 300000)
		p.add('updates', () => this.fetch('updates', '/tower/updates'), 300000)
		p.add('history', () => this.fetch('history', '/tower/history?limit=900'), 300000)
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
		async fetch(key, path, params, loadingKey) {
			const lk = loadingKey || key
			this.$set(this.loading, lk, true)
			try {
				this[key] = await get(path, params)
				this.$set(this.errors, lk, '')
			} catch (error) {
				this.$set(this.errors, lk, error.message)
			} finally {
				this.$set(this.loading, lk, false)
			}
		},
		async fetchHealthCaps() {
			try {
				const health = await get('/tower/health')
				this.capabilities = health.capabilities || []
			} catch (error) {
				this.capabilities = []
			}
		},
		askUpdate() {
			const docker = (this.updates.restarts_docker || []).length
			this.confirm = {
				open: true,
				title: 'Install host updates',
				message: docker
					? `Install ${(this.updates.packages || []).length} update(s)? This restarts the Docker daemon and every container on this host.`
					: `Install ${(this.updates.packages || []).length} update(s) on the host?`,
				confirmLabel: 'Install updates',
				phrase: 'UPDATE',
				danger: true,
			}
			this.pendingAction = () => this.startUpdate('apt-upgrade')
		},
		async startUpdate(kind) {
			this.jobBusy = true
			this.job = null
			try {
				const done = await runJob(kind, {}, (job) => {
					this.job = job
				})
				if (done.status === 'done') {
					showSuccess(kind === 'apt-upgrade' ? 'Updates installed' : 'Dry run finished')
				} else {
					showError(`${kind} failed (exit ${done.exit})`)
				}
			} catch (error) {
				showError(error.message)
			} finally {
				this.jobBusy = false
				await this.poller.refresh('updates')
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
				const result = await postJson('/tower/systemd/restart', { unit })
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
