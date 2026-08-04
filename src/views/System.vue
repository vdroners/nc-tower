<template>
	<div class="nc-tower-view">
		<h2>System</h2>
		<p class="nc-tower-view__lead">
			Nextcloud, PHP and database facts. Filesystem and network figures here are the
			Nextcloud container's own view — the Host tab shows the physical host.
		</p>

		<Section id="system.overview"
			title="Overview"
			:summary="overviewSummary"
			:loading="loading.info"
			:error="errors.info"
			default-open
			@refresh="refresh('info')">
			<dl class="nc-tower-facts">
				<template v-for="fact in overviewFacts">
					<dt :key="`${fact.label}-l`">{{ fact.label }}</dt>
					<dd :key="`${fact.label}-v`">{{ fact.value || '—' }}</dd>
				</template>
			</dl>
			<NcNoteCard v-if="info.nc_updateCheckAvailable === false" type="info">
				Core update check is not available via public APIs; use <strong>Settings → Overview</strong>.
			</NcNoteCard>
			<NcNoteCard v-else-if="info.nc_updateAvailable" type="warning">
				Nextcloud {{ info.nc_updateVersion }} is available (running {{ info.nc_currentVersionimplode || info.nc_version }}).
			</NcNoteCard>
		</Section>

		<Section id="system.resources"
			title="Memory and storage"
			:summary="resourceSummary"
			:loading="resourcesLoading"
			:error="resourcesError"
			default-open
			@refresh="refresh('info')">
			<div class="nc-tower-chips">
				<span class="nc-tower-chip">RAM {{ info.ram_used || '—' }} / {{ info.ram_total || '—' }}</span>
				<span class="nc-tower-chip">available {{ info.ram_available || '—' }}</span>
				<span class="nc-tower-chip">data dir {{ storageUsedLabel }} / {{ storageTotalLabel }}</span>
				<span class="nc-tower-chip">DB {{ sql.dbtyp || '—' }} {{ sql.dbversion || '' }}</span>
				<span class="nc-tower-chip">DB size {{ sql.dbsize || '—' }}</span>
			</div>
			<UsageBar :percent="ramPercent" />
			<h4 class="nc-tower-subhead">Data directory</h4>
			<p class="nc-tower-mono nc-tower-muted">{{ storagePath }}</p>
			<UsageBar :percent="storagePercent" />
			<p class="nc-tower-muted">
				{{ storageUsedLabel }} used · {{ storageFreeLabel }} free of {{ storageTotalLabel }}
			</p>
			<h4 class="nc-tower-subhead">Filesystems (as seen by the Nextcloud container)</h4>
			<DataTable :columns="diskColumns" :rows="info.diskinfo || []" row-key="Mount" default-sort="Mount" empty-text="No filesystems">
				<template #cell-Percent="{ row }"><UsageBar :percent="parseFloat(row.Percent)" /></template>
				<template #cell-UsedFormatted="{ row }">{{ row.UsedFormatted }} / {{ row.TotalFormatted }}</template>
			</DataTable>
		</Section>

		<Section id="system.php"
			title="PHP"
			:summary="info.php_version ? `PHP ${info.php_version}` : ''"
			:loading="loading.info"
			:error="errors.info"
			@refresh="refresh('info')">
			<dl class="nc-tower-facts">
				<dt>Version</dt><dd>{{ info.php_version || '—' }}</dd>
				<dt>Memory limit</dt><dd>{{ info.memory_limit || '—' }}</dd>
				<dt>Max upload</dt><dd>{{ info.max_upload_size || '—' }}</dd>
				<dt>Max execution time</dt><dd>{{ info.max_execution_time || '—' }}</dd>
				<dt>OPcache revalidate</dt><dd>{{ info.opcache_freq || '—' }}</dd>
				<dt>Web server</dt><dd>{{ info.webserver || '—' }}</dd>
			</dl>
			<h4 class="nc-tower-subhead">Extensions</h4>
			<p class="nc-tower-extensions">{{ extensionList }}</p>
		</Section>

		<Section id="system.network"
			title="Network interfaces (Nextcloud container)"
			:summary="`${(info.network || []).length} interface(s)`"
			:loading="loading.info"
			:error="errors.info"
			@refresh="refresh('info')">
			<DataTable :columns="networkColumns" :rows="info.network || []" row-key="interface" empty-text="None" />
		</Section>

		<Section id="system.log"
			title="Nextcloud log"
			:summary="logSummary"
			:loading="loading.log"
			:error="errors.log"
			default-open
			@refresh="refreshLog">
			<div class="nc-tower-chips">
				<span class="nc-tower-chip" :class="maintenance.maintenance ? 'nc-tower-chip--warn' : ''">
					maintenance {{ maintenance.maintenance ? 'ON' : 'off' }}
				</span>
				<span class="nc-tower-chip">{{ info.nc_logfile_size || '' }}</span>
			</div>
			<div class="nc-tower-toolbar">
				<NcButton v-for="lvl in ['', 'error', 'warn', 'info']"
					:key="lvl || 'all'"
					:type="logLevel === lvl ? 'primary' : 'tertiary'"
					@click="logLevel = lvl; refreshLog()">
					{{ lvl || 'all' }}
				</NcButton>
				<input v-model="logQuery"
					class="nc-tower-fan-card__num"
					style="width: 180px"
					placeholder="reqId / text"
					@keyup.enter="refreshLog" />
				<NcButton type="secondary" @click="refreshLog">Filter</NcButton>
			</div>
			<DataTable :columns="logColumns" :rows="log.rows || []" empty-text="No lines">
				<template #cell-message="{ row }">
					<span class="nc-tower-cmd" :title="row.message">{{ row.message }}</span>
					<span v-if="row.exception" class="nc-tower-bad"> · {{ row.exception }}</span>
				</template>
			</DataTable>
			<p class="nc-tower-muted nc-tower-mono">{{ log.path || info.nc_logfile }}</p>
		</Section>

		<Section id="system.setup"
			title="Setup checks"
			:summary="setupSummary"
			:severity="setupSeverity"
			:loading="loading.setup"
			:error="errors.setup"
			@refresh="refresh('setup')">
			<DataTable :columns="setupColumns" :rows="setup.checks || []" empty-text="No checks">
				<template #cell-severity="{ row }">
					<span :class="row.severity === 'error' ? 'nc-tower-bad' : (row.severity === 'warning' ? 'nc-tower-warn' : '')">
						{{ row.severity }}
					</span>
				</template>
			</DataTable>
		</Section>

		<Section id="system.jobs"
			title="Background jobs"
			:summary="jobsSummary"
			:severity="jobs.stale ? 'warn' : 'ok'"
			:loading="loading.jobs"
			:error="errors.jobs"
			@refresh="refresh('jobs')">
			<dl class="nc-tower-facts">
				<dt>Cron mode</dt><dd>{{ jobs.cron_mode || '—' }}</dd>
				<dt>Last cron age</dt>
				<dd :class="jobs.stale ? 'nc-tower-bad' : ''">
					{{ jobs.lastcron_age_s != null ? `${Math.round(jobs.lastcron_age_s / 60)} min` : '—' }}
				</dd>
				<dt>Job count</dt><dd>{{ jobs.job_count ?? '—' }}</dd>
				<dt>Oldest class</dt><dd class="nc-tower-mono">{{ jobs.oldest_class || '—' }}</dd>
			</dl>
		</Section>

		<Section id="system.nc-security"
			title="Security"
			:summary="ncSecuritySummary"
			:severity="(bruteforce.total_24h || 0) > 20 ? 'warn' : 'ok'"
			:loading="loading.bruteforce || loading.sessions"
			:error="errors.bruteforce || errors.sessions"
			@refresh="refreshNcSecurity">
			<h4 class="nc-tower-subhead">Bruteforce (24 h)</h4>
			<DataTable :columns="bfColumns" :rows="bruteforce.rows || []" empty-text="No attempts" />
			<h4 class="nc-tower-subhead">Sessions / devices</h4>
			<DataTable :columns="sessionColumns" :rows="sessions.rows || []" empty-text="None">
				<template #cell-last_activity="{ row }">
					{{ row.last_activity ? new Date(row.last_activity * 1000).toISOString() : '—' }}
				</template>
			</DataTable>
		</Section>

		<Section id="system.shares"
			title="Share audit"
			:summary="shareSummary"
			:severity="(shares.passwordless_count || 0) > 0 ? 'warn' : 'ok'"
			:loading="loading.shares"
			:error="errors.shares"
			@refresh="refresh('shares')">
			<DataTable :columns="shareColumns" :rows="shares.risky || []" empty-text="No risky public links">
				<template #cell-has_password="{ row }">{{ row.has_password ? 'yes' : 'NO' }}</template>
				<template #cell-no_expiry="{ row }">{{ row.no_expiry ? 'none' : 'set' }}</template>
			</DataTable>
		</Section>

		<Section id="system.bloat"
			title="Storage bloat"
			:summary="bloatSummary"
			:loading="loading.bloat"
			:error="errors.bloat"
			@refresh="refresh('bloat')">
			<DataTable :columns="bloatColumns" :rows="bloatRows" empty-text="No data" />
		</Section>
	</div>
</template>

<script>
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import DataTable from '../components/DataTable.vue'
import Section from '../components/Section.vue'
import UsageBar from '../components/UsageBar.vue'
import { get } from '../services/api.js'
import fmt from '../services/format.js'
import Poller from '../services/poll.js'

export default {
	name: 'System',
	components: { DataTable, Section, UsageBar, NcButton, NcNoteCard },
	data() {
		return {
			fmt,
			info: {},
			storage: {},
			sql: {},
			log: {},
			logLevel: 'error',
			logQuery: '',
			setup: {},
			jobs: {},
			bruteforce: {},
			sessions: {},
			shares: {},
			bloat: {},
			maintenance: {},
			loading: {},
			errors: {},
			diskColumns: [
				{ key: 'Mount', label: 'Mount' },
				{ key: 'Device', label: 'Device', mono: true },
				{ key: 'Fs', label: 'FS' },
				{ key: 'UsedFormatted', label: 'Used' },
				{ key: 'Percent', label: 'Usage' },
			],
			networkColumns: [
				{ key: 'interface', label: 'Interface' },
				{ key: 'status', label: 'Status' },
				{ key: 'speed', label: 'Speed' },
				{ key: 'IPv4', label: 'IPv4' },
				{ key: 'MAC', label: 'MAC', mono: true },
			],
			logColumns: [
				{ key: 'time', label: 'Time' },
				{ key: 'level', label: 'Level' },
				{ key: 'app', label: 'App' },
				{ key: 'reqId', label: 'ReqId', mono: true },
				{ key: 'message', label: 'Message' },
			],
			setupColumns: [
				{ key: 'severity', label: 'Sev' },
				{ key: 'category', label: 'Category' },
				{ key: 'name', label: 'Check' },
				{ key: 'description', label: 'Detail' },
			],
			bfColumns: [
				{ key: 'ip', label: 'IP' },
				{ key: 'action', label: 'Action' },
				{ key: 'attempts', label: 'Attempts', align: 'end' },
			],
			sessionColumns: [
				{ key: 'uid', label: 'User' },
				{ key: 'name', label: 'Device' },
				{ key: 'type', label: 'Type' },
				{ key: 'last_activity', label: 'Last activity' },
			],
			shareColumns: [
				{ key: 'owner', label: 'Owner' },
				{ key: 'target', label: 'Target' },
				{ key: 'has_password', label: 'Password' },
				{ key: 'no_expiry', label: 'Expiry' },
				{ key: 'expired', label: 'Expired' },
			],
			bloatColumns: [
				{ key: 'bucket', label: 'Bucket' },
				{ key: 'bytes_h', label: 'Size' },
				{ key: 'files', label: 'Files', align: 'end' },
				{ key: 'pct', label: '% of data dir', align: 'end' },
			],
		}
	},
	computed: {
		overviewSummary() {
			return this.info.nc_version ? `Nextcloud ${this.info.nc_version} on ${this.info.hostname || 'host'}` : ''
		},
		overviewFacts() {
			return [
				{ label: 'Hostname', value: this.info.hostname },
				{ label: 'Nextcloud', value: this.info.nc_version },
				{ label: 'Installation', value: this.info.nc_installation_type },
				{ label: 'Data directory', value: this.info.nc_datadirectory },
				{ label: 'Operating system', value: this.info.osname },
				{ label: 'CPU', value: this.info.cpu },
			]
		},
		resourceSummary() {
			return this.info.ram_percent ? `RAM ${this.info.ram_percent} used` : ''
		},
		ramPercent() {
			return parseFloat(String(this.info.ram_percent || '0'))
		},
		storagePath() {
			const folder = this.storage.folder
			return typeof folder === 'string' ? folder : '—'
		},
		storageUsedLabel() {
			return this.storage.folder44 || (this.storage.folder4 != null ? fmt.bytes(this.storage.folder4) : '—')
		},
		storageTotalLabel() {
			return this.storage.folder33 || (this.storage.folder3 != null ? fmt.bytes(this.storage.folder3) : '—')
		},
		storageFreeLabel() {
			return this.storage.folder22 || (this.storage.folder2 != null ? fmt.bytes(this.storage.folder2) : '—')
		},
		storagePercent() {
			const used = Number(this.storage.folder4)
			const total = Number(this.storage.folder3)
			return total > 0 ? (used / total) * 100 : 0
		},
		extensionList() {
			const ext = this.info.extensions
			if (!ext) {
				return '—'
			}
			return Array.isArray(ext) ? ext.join(', ') : String(ext)
		},
		resourcesLoading() {
			return !!(this.loading.info || this.loading.storage || this.loading.sql)
		},
		resourcesError() {
			const parts = []
			if (this.errors.storage) {
				parts.push(`storage: ${this.errors.storage}`)
			}
			if (this.errors.sql) {
				parts.push(`database: ${this.errors.sql}`)
			}
			return parts.join(' · ')
		},
		logSummary() {
			return `${(this.log.rows || []).length} line(s)`
		},
		setupSummary() {
			const e = this.setup.error_count || 0
			const w = this.setup.warn_count || 0
			return e || w ? `${e} error · ${w} warn` : `${(this.setup.checks || []).length} checks`
		},
		setupSeverity() {
			if ((this.setup.error_count || 0) > 0) {
				return 'crit'
			}
			return (this.setup.warn_count || 0) > 0 ? 'warn' : 'ok'
		},
		jobsSummary() {
			if (this.jobs.stale) {
				return 'cron stale'
			}
			return this.jobs.job_count != null ? `${this.jobs.job_count} jobs` : ''
		},
		ncSecuritySummary() {
			return `${this.bruteforce.total_24h || 0} bruteforce · ${(this.sessions.rows || []).length} sessions`
		},
		shareSummary() {
			const n = this.shares.passwordless_count || 0
			return n ? `${n} passwordless public` : `${(this.shares.risky || []).length} risky`
		},
		bloatSummary() {
			const s = this.bloat.sizes || {}
			const trash = s.trashbin?.bytes || 0
			return trash ? `trash ${fmt.bytes(trash)}` : ''
		},
		bloatRows() {
			const s = this.bloat.sizes || {}
			return Object.keys(s).map((bucket) => ({
				bucket,
				bytes_h: fmt.bytes(s[bucket].bytes || 0),
				files: s[bucket].files,
				pct: s[bucket].pct_of_datadir != null ? `${s[bucket].pct_of_datadir}%` : '—',
			}))
		},
	},
	created() {
		this.poller = new Poller()
		this.poller.add('info', () => Promise.all([
			this.fetch('info', '/systeminfo'),
			this.fetch('storage', '/storage'),
			this.fetch('sql', '/sqlinfo'),
			this.fetch('maintenance', '/ncadmin/maintenance'),
		]), 60000)
		this.poller.add('log', () => this.refreshLog(), 60000)
		this.poller.add('setup', () => this.fetch('setup', '/ncadmin/setupchecks'), 300000)
		this.poller.add('jobs', () => this.fetch('jobs', '/ncadmin/jobs'), 120000)
		this.poller.add('bruteforce', () => this.fetch('bruteforce', '/ncadmin/bruteforce'), 120000)
		this.poller.add('sessions', () => this.fetch('sessions', '/ncadmin/sessions'), 120000)
		this.poller.add('shares', () => this.fetch('shares', '/ncadmin/shares'), 300000)
		this.poller.add('bloat', () => this.fetch('bloat', '/ncadmin/bloat'), 300000)
		this.poller.start()
	},
	beforeDestroy() {
		this.poller.stop()
	},
	methods: {
		refresh(name) {
			return this.poller.refresh(name)
		},
		refreshNcSecurity() {
			return Promise.all([
				this.poller.refresh('bruteforce'),
				this.poller.refresh('sessions'),
			])
		},
		async refreshLog() {
			this.$set(this.loading, 'log', true)
			try {
				this.log = await get('/ncadmin/log', {
					lines: 200,
					level: this.logLevel || undefined,
					query: this.logQuery || undefined,
				})
				this.$set(this.errors, 'log', '')
			} catch (error) {
				this.$set(this.errors, 'log', error.message)
			} finally {
				this.$set(this.loading, 'log', false)
			}
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
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-facts {
	display: grid;
	grid-template-columns: minmax(140px, max-content) 1fr;
	gap: 4px 16px;
	margin: 0;

	dt { color: var(--color-text-maxcontrast); }
	dd { margin: 0; overflow-wrap: anywhere; }
}

.nc-tower-subhead {
	margin: 16px 0 6px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.nc-tower-extensions {
	font-size: 0.85em;
	color: var(--color-text-maxcontrast);
	overflow-wrap: anywhere;
	margin: 0;
}

.nc-tower-mono {
	font-family: var(--font-face-monospace, monospace);
	font-size: 0.9em;
}

@media (max-width: 720px) {
	.nc-tower-facts { grid-template-columns: 1fr; }
	.nc-tower-facts dt { margin-top: 6px; }
}
</style>
