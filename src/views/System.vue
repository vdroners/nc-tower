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
			<p class="nc-tower-mono tower-muted">{{ storagePath }}</p>
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
			title="Log file"
			:summary="info.nc_logfile_size || ''"
			:loading="loading.info"
			:error="errors.info"
			@refresh="refresh('info')">
			<dl class="nc-tower-facts">
				<dt>Path</dt><dd class="nc-tower-mono">{{ info.nc_logfile || '—' }}</dd>
				<dt>Size</dt><dd>{{ info.nc_logfile_size || '—' }}</dd>
				<dt>Update channel</dt><dd>{{ info.nc_updatechannel || '—' }}</dd>
			</dl>
		</Section>
	</div>
</template>

<script>
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import DataTable from '../components/DataTable.vue'
import Section from '../components/Section.vue'
import UsageBar from '../components/UsageBar.vue'
import { get } from '../services/api.js'
import fmt from '../services/format.js'
import Poller from '../services/poll.js'

export default {
	name: 'System',
	components: { DataTable, Section, UsageBar, NcNoteCard },
	data() {
		return {
			fmt,
			info: {},
			storage: {},
			sql: {},
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
		// /storage returns the datadirectory PATH in `folder`; the byte counts
		// live in folder4/folder44 (used), folder3/folder33 (total) and
		// folder2/folder22 (free). Rendering `folder` printed a path where a
		// size was implied.
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
	},
	created() {
		this.poller = new Poller()
		this.poller.add('info', () => Promise.all([
			this.fetch('info', '/systeminfo'),
			this.fetch('storage', '/storage'),
			this.fetch('sql', '/sqlinfo'),
		]), 60000)
		this.poller.start()
	},
	beforeDestroy() {
		this.poller.stop()
	},
	methods: {
		/**
		 * @param {string} [name] section to refresh; omit for all
		 * @return {Promise<void>}
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
