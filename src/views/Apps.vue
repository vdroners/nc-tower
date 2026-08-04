<template>
	<div class="nc-tower-view">
		<h2>Apps</h2>
		<p class="nc-tower-view__lead">Enable and disable Nextcloud apps installed on this server. Store updates use the App Store API.</p>

		<Section id="apps.updates"
			title="Updates"
			:summary="updateSummary"
			:severity="(updates.apps || []).length ? 'warn' : 'ok'"
			:loading="loading.updates"
			:error="errors.updates"
			default-open
			@refresh="refresh('updates')">
			<NcNoteCard v-if="updates.available === false" type="info">
				{{ updates.message || 'App update listing is not available here.' }}
				Use <strong>Settings → Apps</strong> for store updates.
			</NcNoteCard>
			<DataTable
				:columns="updateTableColumns"
				:rows="updates.apps || []"
				row-key="id"
				:empty-text="updatesEmptyText">
				<template #cell-name="{ row }">
					<span class="nc-tower-app"><img v-if="row.icon" :src="row.icon" alt="" class="nc-tower-app__icon">{{ appLabel(row) }}</span>
				</template>
				<template v-if="updates.available !== false" #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton type="primary" :disabled="busy === row.id" @click="update(row)">
							{{ busy === row.id ? 'Updating…' : `Update to ${row.updateVersion}` }}
						</NcButton>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="apps.enabled"
			title="Enabled apps"
			:summary="enabledSummary"
			:loading="loading.info"
			:error="errors.info"
			default-open
			@refresh="refresh('info')">
			<div class="nc-tower-toolbar">
				<NcTextField :value.sync="filter" label="Filter apps" placeholder="Filter by name or id" />
			</div>
			<DataTable :columns="appColumns" :rows="filtered(enabledApps)" row-key="appid" default-sort="appid" :empty-text="infoEmptyText">
				<template #cell-appid="{ row }">
					<span class="nc-tower-app"><img v-if="row.icon" :src="row.icon" alt="" class="nc-tower-app__icon">{{ appLabel(row) }}</span>
				</template>
				<template #cell-shipped="{ row }">{{ row.shipped ? 'shipped' : 'custom' }}</template>
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton v-if="!row.shipped"
							type="secondary"
							:disabled="busy === row.appid"
							@click="ask('disable', row)">
							Disable
						</NcButton>
						<span v-else class="nc-tower-muted">shipped</span>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="apps.disabled"
			title="Disabled apps"
			:summary="disabledSummary"
			:loading="loading.info"
			:error="errors.info"
			@refresh="refresh('info')">
			<DataTable :columns="appColumns" :rows="filtered(disabledApps)" row-key="appid" default-sort="appid" :empty-text="infoEmptyText">
				<template #cell-appid="{ row }">
					<span class="nc-tower-app"><img v-if="row.icon" :src="row.icon" alt="" class="nc-tower-app__icon">{{ appLabel(row) }}</span>
				</template>
				<template #cell-shipped="{ row }">{{ row.shipped ? 'shipped' : 'custom' }}</template>
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton type="primary" :disabled="busy === row.appid" @click="ask('enable', row)">Enable</NcButton>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="apps.sections"
			title="Settings sections"
			:summary="sectionsSummary"
			:loading="loading.info"
			:error="errors.info"
			@refresh="refresh('info')">
			<NcNoteCard v-if="info.settings_error" type="warning">
				Settings sections could not be enumerated: {{ info.settings_error }}
			</NcNoteCard>
			<h4 class="nc-tower-subhead">Admin</h4>
			<p class="nc-tower-muted">{{ (adminSectionNames || []).join(', ') || '—' }}</p>
			<h4 class="nc-tower-subhead">Personal</h4>
			<p class="nc-tower-muted">{{ (personalSectionNames || []).join(', ') || '—' }}</p>
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
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import NcTextField from '@nextcloud/vue/dist/Components/NcTextField.js'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import DataTable from '../components/DataTable.vue'
import Section from '../components/Section.vue'
import { get } from '../services/api.js'
import { listAppUpdates, updateApp } from '../services/appstoreOcs.js'
import Poller from '../services/poll.js'

/**
 * @param {unknown} value list-like payload
 * @return {unknown[]}
 */
function asList(value) {
	if (Array.isArray(value)) {
		return value
	}
	if (value && typeof value === 'object') {
		return Object.values(value)
	}
	return []
}

export default {
	name: 'Apps',
	components: { ConfirmDialog, DataTable, Section, NcButton, NcNoteCard, NcTextField },
	data() {
		return {
			info: {},
			updates: { available: true, apps: [], appscount: 0 },
			loading: {},
			errors: {},
			filter: '',
			busy: '',
			confirm: { open: false, title: '', message: '', confirmLabel: 'Confirm', phrase: '', danger: false },
			pendingAction: null,
			appColumns: [
				{ key: 'appid', label: 'App' },
				{ key: 'version', label: 'Version' },
				{ key: 'shipped', label: 'Origin' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			updateColumns: [
				{ key: 'name', label: 'App' },
				{ key: 'version', label: 'Installed' },
				{ key: 'updateVersion', label: 'Available' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
		}
	},
	computed: {
		enabledApps() {
			return asList(this.info.thisappsenabledfull)
		},
		disabledApps() {
			return asList(this.info.thisappsdisabledfull)
		},
		adminSectionNames() {
			return asList(this.info.adminsectionsappname)
		},
		personalSectionNames() {
			return asList(this.info.personalsectionsappname)
		},
		enabledSummary() {
			if (this.loading.info && !this.enabledApps.length) {
				return 'loading…'
			}
			return `${this.enabledApps.length} enabled`
		},
		disabledSummary() {
			if (this.loading.info && !this.disabledApps.length) {
				return 'loading…'
			}
			return `${this.disabledApps.length} disabled`
		},
		sectionsSummary() {
			return `${asList(this.info.adminsections).length} admin · ${asList(this.info.personalsections).length} personal`
		},
		infoEmptyText() {
			return this.loading.info ? 'Loading…' : 'None'
		},
		updatesEmptyText() {
			if (this.updates.available === false) {
				return 'Update listing unavailable — use Nextcloud Apps'
			}
			return this.loading.updates ? 'Loading…' : 'No pending updates'
		},
		updateTableColumns() {
			if (this.updates.available === false) {
				return this.updateColumns.filter((col) => col.key !== 'actions')
			}
			return this.updateColumns
		},
		updateSummary() {
			if (this.updates.available === false) {
				return this.updates.message || 'listing unavailable — use Nextcloud Apps'
			}
			const count = (this.updates.apps || []).length
			return count ? `${count} update(s) available` : 'no pending updates listed'
		},
	},
	created() {
		this.poller = new Poller()
		this.poller.add('info', () => this.fetchInfo(), 120000)
		this.poller.add('updates', () => this.fetchUpdates(), 300000)
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
		async fetchInfo() {
			this.$set(this.loading, 'info', true)
			try {
				const payload = await get('/appsinfo')
				this.info = payload && typeof payload === 'object' ? payload : {}
				this.$set(this.errors, 'info', '')
			} catch (error) {
				this.$set(this.errors, 'info', error.message)
			} finally {
				this.$set(this.loading, 'info', false)
			}
		},
		async fetchUpdates() {
			this.$set(this.loading, 'updates', true)
			try {
				this.updates = await listAppUpdates()
				this.$set(this.errors, 'updates', '')
			} catch (error) {
				this.updates = {
					available: false,
					apps: [],
					appscount: 0,
					message: error.message || 'Could not reach the App Store API. Is the appstore app enabled?',
				}
				this.$set(this.errors, 'updates', '')
			} finally {
				this.$set(this.loading, 'updates', false)
			}
		},
		/**
		 * @param {object} row app row
		 * @return {string}
		 */
		appLabel(row) {
			const name = row?.name
			if (typeof name === 'string') {
				return name
			}
			if (name && typeof name === 'object') {
				const inner = name.name
				if (typeof inner === 'string') {
					return inner
				}
				if (inner && typeof inner === 'object') {
					return Object.values(inner)[0] || row.appid || row.id
				}
			}
			return row?.appid || row?.id || ''
		},
		/**
		 * @param {object|string|boolean} result mutator response
		 * @param {string} fallback error when ok is false
		 */
		assertOk(result, fallback) {
			if (result === false || result === 'false') {
				throw new Error(fallback)
			}
			if (result && typeof result === 'object' && result.ok === false) {
				throw new Error(result.error || fallback)
			}
		},
		filtered(rows) {
			const list = rows || []
			const query = this.filter.trim().toLowerCase()
			if (!query) {
				return list
			}
			return list.filter((row) => `${row.appid || ''} ${this.appLabel(row)}`.toLowerCase().includes(query))
		},
		ask(action, row) {
			this.confirm = {
				open: true,
				title: action === 'enable' ? 'Enable app' : 'Disable app',
				message: `${action} ${this.appLabel(row)} (${row.appid})?`,
				confirmLabel: action === 'enable' ? 'Enable' : 'Disable',
				phrase: '',
				danger: action === 'disable',
			}
			this.pendingAction = () => this.toggle(action, row.appid)
		},
		async runConfirmed() {
			const action = this.pendingAction
			this.confirm.open = false
			this.pendingAction = null
			if (action) {
				await action()
			}
		},
		async toggle(action, appid) {
			this.busy = appid
			try {
				const result = await get(`/${action}app/${encodeURIComponent(appid)}`)
				this.assertOk(result, `Could not ${action} ${appid}`)
				showSuccess(`${appid} ${action}d`)
			} catch (error) {
				showError(error.message)
			} finally {
				this.busy = ''
				await this.poller.refresh('info')
			}
		},
		async update(row) {
			this.busy = row.id
			try {
				await updateApp(row.id)
				showSuccess(`Updated ${row.id}`)
			} catch (error) {
				showError(error.message || 'Update failed')
			} finally {
				this.busy = ''
				await this.poller.refresh('updates')
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-toolbar {
	margin-bottom: 10px;
	max-width: 360px;
}

.nc-tower-subhead {
	margin: 14px 0 4px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.nc-tower-app {
	display: inline-flex;
	align-items: center;
	gap: 8px;

	&__icon {
		width: 18px;
		height: 18px;
		object-fit: contain;
	}
}
</style>
