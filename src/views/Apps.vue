<template>
	<div class="tower-view">
		<h2>Apps</h2>
		<p class="tower-view__lead">Enable, disable and update Nextcloud apps installed on this server.</p>

		<Section id="apps.updates"
			title="Updates"
			:summary="updateSummary"
			:severity="(updates.apps || []).length ? 'warn' : 'ok'"
			:loading="loading.updates"
			:error="errors.updates"
			default-open
			@refresh="poller.refresh('updates')">
			<DataTable :columns="updateColumns" :rows="updates.apps || []" row-key="id" empty-text="All apps up to date">
				<template #cell-name="{ row }">
					<span class="tower-app"><img v-if="row.icon" :src="row.icon" alt="" class="tower-app__icon">{{ appLabel(row) }}</span>
				</template>
				<template #cell-actions="{ row }">
					<div class="tower-actions-cell">
						<NcButton type="primary" :disabled="busy === row.id" @click="update(row)">
							{{ busy === row.id ? 'Updating…' : `Update to ${row.updateVersion}` }}
						</NcButton>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="apps.enabled"
			title="Enabled apps"
			:summary="`${(info.thisappsenabledfull || []).length} enabled`"
			:loading="loading.info"
			:error="errors.info"
			default-open
			@refresh="poller.refresh('info')">
			<div class="tower-toolbar">
				<NcTextField :value.sync="filter" label="Filter apps" placeholder="Filter by name or id" />
			</div>
			<DataTable :columns="appColumns" :rows="filtered(info.thisappsenabledfull)" row-key="appid" default-sort="appid" empty-text="None">
				<template #cell-appid="{ row }">
					<span class="tower-app"><img v-if="row.icon" :src="row.icon" alt="" class="tower-app__icon">{{ appLabel(row) }}</span>
				</template>
				<template #cell-shipped="{ row }">{{ row.shipped ? 'shipped' : 'custom' }}</template>
				<template #cell-actions="{ row }">
					<div class="tower-actions-cell">
						<NcButton v-if="!row.shipped"
							type="secondary"
							:disabled="busy === row.appid"
							@click="ask('disable', row)">
							Disable
						</NcButton>
						<span v-else class="tower-muted">shipped</span>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="apps.disabled"
			title="Disabled apps"
			:summary="`${(info.thisappsdisabledfull || []).length} disabled`"
			:loading="loading.info"
			:error="errors.info"
			@refresh="poller.refresh('info')">
			<DataTable :columns="appColumns" :rows="filtered(info.thisappsdisabledfull)" row-key="appid" default-sort="appid" empty-text="None">
				<template #cell-appid="{ row }">
					<span class="tower-app"><img v-if="row.icon" :src="row.icon" alt="" class="tower-app__icon">{{ appLabel(row) }}</span>
				</template>
				<template #cell-shipped="{ row }">{{ row.shipped ? 'shipped' : 'custom' }}</template>
				<template #cell-actions="{ row }">
					<div class="tower-actions-cell">
						<NcButton type="primary" :disabled="busy === row.appid" @click="ask('enable', row)">Enable</NcButton>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="apps.sections"
			title="Settings sections"
			:summary="`${(info.adminsections || []).length} admin · ${(info.personalsections || []).length} personal`"
			:loading="loading.info"
			:error="errors.info"
			@refresh="poller.refresh('info')">
			<h4 class="tower-subhead">Admin</h4>
			<p class="tower-muted">{{ (info.adminsectionsappname || []).join(', ') || '—' }}</p>
			<h4 class="tower-subhead">Personal</h4>
			<p class="tower-muted">{{ (info.personalsectionsappname || []).join(', ') || '—' }}</p>
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
import NcTextField from '@nextcloud/vue/dist/Components/NcTextField.js'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import DataTable from '../components/DataTable.vue'
import Section from '../components/Section.vue'
import { get } from '../services/api.js'
import Poller from '../services/poll.js'

export default {
	name: 'Apps',
	components: { ConfirmDialog, DataTable, Section, NcButton, NcTextField },
	data() {
		return {
			poller: new Poller(),
			info: {},
			updates: {},
			loading: {},
			errors: {},
			filter: '',
			busy: '',
			confirm: { open: false, title: '', message: '', confirmLabel: 'Confirm', phrase: '', danger: false, action: null },
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
		updateSummary() {
			const count = (this.updates.apps || []).length
			return count ? `${count} update(s) available` : 'up to date'
		},
	},
	created() {
		this.poller.add('info', () => this.fetch('info', '/appsinfo'), 120000)
		this.poller.add('updates', () => this.fetch('updates', '/appupdates'), 300000)
		this.poller.start()
	},
	beforeDestroy() {
		this.poller.stop()
	},
	methods: {
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
		/**
		 * appsfull() stores the whole appinfo array under `name`, so the display
		 * name is one level down — and null appinfo falls back to a stdClass
		 * whose name is the app id.
		 *
		 * @param {object} row app row
		 * @return {string} display label
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
				action: () => this.toggle(action, row.appid),
			}
		},
		async runConfirmed() {
			const action = this.confirm.action
			this.confirm.open = false
			if (action) {
				await action()
			}
		},
		async toggle(action, appid) {
			this.busy = appid
			try {
				await get(`/${action}app/${encodeURIComponent(appid)}`)
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
				await get(`/updateapp/${encodeURIComponent(row.id)}`)
				showSuccess(`${row.id} updated`)
			} catch (error) {
				showError(error.message)
			} finally {
				this.busy = ''
				await this.poller.refresh('updates')
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.tower-toolbar {
	margin-bottom: 10px;
	max-width: 360px;
}

.tower-subhead {
	margin: 14px 0 4px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.tower-app {
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
