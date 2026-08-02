<template>
	<div class="tower-view">
		<h2>System</h2>
		<p class="tower-view__lead">Nextcloud, PHP, database and host facts as this server reports them.</p>

		<Section id="system.overview"
			title="Overview"
			:summary="overviewSummary"
			:loading="loading.info"
			:error="errors.info"
			default-open
			@refresh="poller.refresh('info')">
			<dl class="tower-facts">
				<template v-for="fact in overviewFacts">
					<dt :key="`${fact.label}-l`">{{ fact.label }}</dt>
					<dd :key="`${fact.label}-v`">{{ fact.value || '—' }}</dd>
				</template>
			</dl>
			<NcNoteCard v-if="info.nc_updateAvailable" type="warning">
				Nextcloud {{ info.nc_updateVersion }} is available (running {{ info.nc_currentVersionimplode || info.nc_version }}).
			</NcNoteCard>
		</Section>

		<Section id="system.resources"
			title="Memory and storage"
			:summary="resourceSummary"
			:loading="loading.info"
			:error="errors.info"
			default-open
			@refresh="poller.refresh('info')">
			<div class="tower-chips">
				<span class="tower-chip">RAM {{ info.ram_used || '—' }} / {{ info.ram_total || '—' }}</span>
				<span class="tower-chip">available {{ info.ram_available || '—' }}</span>
				<span class="tower-chip">data dir {{ storageLabel }}</span>
				<span class="tower-chip">DB {{ sql.dbtyp || '—' }} {{ sql.dbversion || '' }}</span>
				<span class="tower-chip">DB size {{ sql.dbsize || '—' }}</span>
			</div>
			<UsageBar :percent="ramPercent" />
			<h4 class="tower-subhead">Filesystems</h4>
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
			@refresh="poller.refresh('info')">
			<dl class="tower-facts">
				<dt>Version</dt><dd>{{ info.php_version || '—' }}</dd>
				<dt>Memory limit</dt><dd>{{ info.memory_limit || '—' }}</dd>
				<dt>Max upload</dt><dd>{{ info.max_upload_size || '—' }}</dd>
				<dt>Max execution time</dt><dd>{{ info.max_execution_time || '—' }}</dd>
				<dt>OPcache revalidate</dt><dd>{{ info.opcache_freq || '—' }}</dd>
				<dt>Web server</dt><dd>{{ info.webserver || '—' }}</dd>
			</dl>
			<h4 class="tower-subhead">Extensions</h4>
			<p class="tower-extensions">{{ extensionList }}</p>
		</Section>

		<Section id="system.network"
			title="Network interfaces"
			:summary="`${(info.network || []).length} interface(s)`"
			:loading="loading.info"
			:error="errors.info"
			@refresh="poller.refresh('info')">
			<DataTable :columns="networkColumns" :rows="info.network || []" row-key="interface" empty-text="None" />
		</Section>

		<Section id="system.log"
			title="Log file"
			:summary="info.nc_logfile_size || ''"
			:loading="loading.info"
			:error="errors.info"
			@refresh="poller.refresh('info')">
			<dl class="tower-facts">
				<dt>Path</dt><dd class="tower-mono">{{ info.nc_logfile || '—' }}</dd>
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
			poller: new Poller(),
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
		storageLabel() {
			const folder = this.storage.folder
			if (folder == null || folder === -1) {
				return '—'
			}
			return typeof folder === 'number' ? fmt.bytes(folder) : String(folder)
		},
		extensionList() {
			const ext = this.info.extensions
			if (!ext) {
				return '—'
			}
			return Array.isArray(ext) ? ext.join(', ') : String(ext)
		},
	},
	created() {
		this.poller.add('info', () => Promise.all([
			this.fetch('info', '/systeminfo'),
			this.fetch('storage', '/storage', 'info'),
			this.fetch('sql', '/sqlinfo', 'info'),
		]), 60000)
		this.poller.start()
	},
	beforeDestroy() {
		this.poller.stop()
	},
	methods: {
		async fetch(key, path, loadingKey) {
			const slot = loadingKey || key
			this.$set(this.loading, slot, true)
			try {
				this[key] = await get(path)
				this.$set(this.errors, slot, '')
			} catch (error) {
				this.$set(this.errors, slot, error.message)
			} finally {
				this.$set(this.loading, slot, false)
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.tower-facts {
	display: grid;
	grid-template-columns: minmax(140px, max-content) 1fr;
	gap: 4px 16px;
	margin: 0;

	dt { color: var(--color-text-maxcontrast); }
	dd { margin: 0; overflow-wrap: anywhere; }
}

.tower-subhead {
	margin: 16px 0 6px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.tower-extensions {
	font-size: 0.85em;
	color: var(--color-text-maxcontrast);
	overflow-wrap: anywhere;
	margin: 0;
}

.tower-mono {
	font-family: var(--font-face-monospace, monospace);
	font-size: 0.9em;
}

@media (max-width: 720px) {
	.tower-facts { grid-template-columns: 1fr; }
	.tower-facts dt { margin-top: 6px; }
}
</style>
