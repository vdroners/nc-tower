<template>
	<div class="nc-tower-view">
		<h2>Users</h2>
		<p class="nc-tower-view__lead">Accounts and groups on this Nextcloud instance.</p>

		<Section id="users.list"
			title="Users"
			:summary="userSummary"
			:loading="loading.data"
			:error="errors.data"
			default-open
			@refresh="refresh('data')">
			<div class="nc-tower-toolbar">
				<NcTextField :value.sync="filter" label="Filter users" placeholder="Filter by id, name or email" />
				<NcButton type="primary" @click="openCreate">
					<template #icon><NcTowerIcon name="plus" :size="18" /></template>
					New user
				</NcButton>
			</div>
			<DataTable :columns="userColumns" :rows="filteredUsers" row-key="uid" default-sort="uid" empty-text="No users">
				<template #cell-isadmin="{ row }">
					<span v-if="row.isadmin" class="nc-tower-badge">admin</span>
					<span v-else class="nc-tower-muted">—</span>
				</template>
				<template #cell-status="{ row }">
					<span :class="row.status ? 'nc-tower-muted' : 'nc-tower-good'">{{ row.status ? 'never signed in' : 'active' }}</span>
				</template>
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcActions :aria-label="`Actions for ${row.uid}`">
							<NcActionButton @click="openEdit(row)">
								<template #icon><NcTowerIcon name="edit" :size="18" /></template>
								Edit
							</NcActionButton>
							<NcActionButton @click="openNotify(row.uid, false)">
								<template #icon><NcTowerIcon name="bell" :size="18" /></template>
								Notify
							</NcActionButton>
							<NcActionButton @click="askDelete(row)">
								<template #icon><NcTowerIcon name="trash" :size="18" /></template>
								Delete
							</NcActionButton>
						</NcActions>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="users.groups"
			title="Groups"
			:summary="`${(data.groups || []).length} group(s)`"
			:loading="loading.data"
			:error="errors.data"
			@refresh="refresh('data')">
			<div class="nc-tower-toolbar">
				<NcTextField :value.sync="newGroup" label="New group name" placeholder="group id" />
				<NcButton type="secondary" :disabled="!newGroup.trim()" @click="addGroup">Add group</NcButton>
			</div>
			<DataTable :columns="groupColumns" :rows="data.groups || []" row-key="gid" default-sort="gid" empty-text="No groups">
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcActions :aria-label="`Actions for ${row.gid}`">
							<NcActionButton @click="openNotify(row.gid, true)">
								<template #icon><NcTowerIcon name="bell" :size="18" /></template>
								Notify group
							</NcActionButton>
							<NcActionButton @click="askDeleteGroup(row)">
								<template #icon><NcTowerIcon name="trash" :size="18" /></template>
								Delete group
							</NcActionButton>
						</NcActions>
					</div>
				</template>
			</DataTable>
		</Section>

		<NcDialog :open="create.open" name="New user" size="normal" @update:open="create.open = false">
			<div class="nc-tower-form">
				<NcTextField :value.sync="create.uid" label="User ID" />
				<NcTextField :value.sync="create.displayname" label="Display name" />
				<NcTextField :value.sync="create.email" label="Email" type="email" />
				<NcTextField :value.sync="create.password" label="Password" type="password" />
				<NcTextField :value.sync="create.groups" label="Groups (comma separated)" />
				<NcTextField :value.sync="create.quota" label="Quota" placeholder="default" />
			</div>
			<template #actions>
				<NcButton type="tertiary" @click="create.open = false">Cancel</NcButton>
				<NcButton type="primary" :disabled="!create.uid.trim() || create.busy" @click="submitCreate">Create</NcButton>
			</template>
		</NcDialog>

		<NcDialog :open="edit.open" :name="`Edit ${edit.uid}`" size="normal" @update:open="edit.open = false">
			<NcLoadingIcon v-if="edit.loading" :size="28" />
			<div v-else class="nc-tower-form">
				<NcTextField :value.sync="edit.displayname" label="Display name" />
				<NcTextField :value.sync="edit.email" label="Email" type="email" />
				<NcTextField :value.sync="edit.quota" label="Quota" placeholder="default quota / unlimited / 10 GB" />
				<NcTextField :value.sync="edit.groups" label="Groups (comma separated)" />
				<NcTextField :value.sync="edit.password" label="New password" type="password" placeholder="leave blank to keep current" />
				<p class="nc-tower-muted">Storage in use: {{ edit.used || '—' }}</p>
			</div>
			<template #actions>
				<NcButton type="tertiary" @click="edit.open = false">Cancel</NcButton>
				<NcButton type="primary" :disabled="edit.busy || edit.loading" @click="submitEdit">Save</NcButton>
			</template>
		</NcDialog>

		<NcDialog :open="notify.open" :name="notify.group ? 'Notify group' : 'Notify user'" size="normal" @update:open="notify.open = false">
			<p>Send a notification to <strong>{{ notify.who }}</strong>.</p>
			<NcTextField :value.sync="notify.message" label="Message" />
			<template #actions>
				<NcButton type="tertiary" @click="notify.open = false">Cancel</NcButton>
				<NcButton type="primary" :disabled="!notify.message.trim()" @click="sendNotify">Send</NcButton>
			</template>
		</NcDialog>

		<ConfirmDialog v-bind="confirm"
			:open="confirm.open"
			@cancel="confirm.open = false"
			@confirm="runConfirmed" />
	</div>
</template>

<script>
import { showError, showSuccess } from '@nextcloud/dialogs'
import NcActionButton from '@nextcloud/vue/dist/Components/NcActionButton.js'
import NcActions from '@nextcloud/vue/dist/Components/NcActions.js'
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcDialog from '@nextcloud/vue/dist/Components/NcDialog.js'
import NcLoadingIcon from '@nextcloud/vue/dist/Components/NcLoadingIcon.js'
import NcTextField from '@nextcloud/vue/dist/Components/NcTextField.js'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import NcTowerIcon from '../components/NcTowerIcon.vue'
import DataTable from '../components/DataTable.vue'
import Section from '../components/Section.vue'
import { get, post } from '../services/api.js'
import Poller from '../services/poll.js'

export default {
	name: 'Users',
	components: { ConfirmDialog, DataTable, NcTowerIcon, Section, NcActionButton, NcActions, NcButton, NcDialog, NcLoadingIcon, NcTextField },
	data() {
		return {
			data: {},
			loading: {},
			errors: {},
			filter: '',
			newGroup: '',
			create: { open: false, uid: '', displayname: '', email: '', password: '', groups: '', quota: '', busy: false },
			notify: { open: false, who: '', group: false, message: '' },
			edit: {
				open: false, loading: false, busy: false, uid: '', displayname: '', email: '',
				quota: '', groups: '', password: '', admingroups: [], managerids: '', used: '',
			},
			confirm: { open: false, title: '', message: '', confirmLabel: 'Confirm', phrase: '', danger: false },
			pendingAction: null,
			userColumns: [
				{ key: 'uid', label: 'User ID' },
				{ key: 'displayname', label: 'Display name' },
				{ key: 'email', label: 'Email' },
				{ key: 'used', label: 'Used', align: 'end', sortBy: 'used_bytes' },
				{ key: 'last', label: 'Last sign-in' },
				{ key: 'isadmin', label: 'Role' },
				{ key: 'status', label: 'Status' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			groupColumns: [
				{ key: 'gid', label: 'Group' },
				{ key: 'guserscount', label: 'Members', align: 'end' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
		}
	},
	computed: {
		userSummary() {
			return this.data.userCount != null
				? `${this.data.userCount} user(s) · ${this.data.adminCount || 0} admin(s)`
				: ''
		},
		filteredUsers() {
			const list = this.data.users || []
			const query = this.filter.trim().toLowerCase()
			if (!query) {
				return list
			}
			return list.filter((row) => `${row.uid} ${row.displayname || ''} ${row.email || ''}`
				.toLowerCase().includes(query))
		},
	},
	created() {
		this.poller = new Poller()
		this.poller.add('data', () => this.fetch('data', '/usercount'), 120000)
		this.poller.start()
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
		async openEdit(row) {
			this.edit = {
				open: true, loading: true, busy: false, uid: row.uid, displayname: '', email: '',
				quota: '', groups: '', password: '', admingroups: [], managerids: '', used: '',
			}
			try {
				// edituser wraps its payload in a single-element array.
				const data = await get(`/edituser/${encodeURIComponent(row.uid)}`)
				const user = Array.isArray(data.user) ? data.user[0] : data.user
				if (!user) {
					throw new Error('user not found')
				}
				Object.assign(this.edit, {
					displayname: user.displayname || '',
					email: user.email || '',
					quota: user.quota || '',
					groups: (user.groups || []).join(', '),
					admingroups: user.admingroups || [],
					managerids: user.managerids || '',
					used: user.used || '',
				})
			} catch (error) {
				showError(error.message)
				this.edit.open = false
			} finally {
				this.edit.loading = false
			}
		},
		async submitEdit() {
			this.edit.busy = true
			try {
				await post('/saveuser', {
					uid: this.edit.uid,
					displayname: this.edit.displayname,
					// Empty password means "keep the current one" — saveuser skips it.
					password: this.edit.password,
					email: this.edit.email,
					groups: this.edit.groups.split(',').map((g) => g.trim()).filter(Boolean),
					admingroups: this.edit.admingroups,
					quota: this.edit.quota,
					managerids: this.edit.managerids,
				})
				showSuccess(`Saved ${this.edit.uid}`)
				this.edit.open = false
			} catch (error) {
				showError(error.message)
			} finally {
				this.edit.busy = false
				await this.poller.refresh('data')
			}
		},
		openCreate() {
			this.create = { open: true, uid: '', displayname: '', email: '', password: '', groups: '', quota: '', busy: false }
		},
		async submitCreate() {
			this.create.busy = true
			try {
				const uid = this.create.uid.trim()
				const exists = await get(`/userexists/${encodeURIComponent(uid)}`)
				if (exists === true || exists?.exists === true || exists?.userexists === true) {
					showError(`${uid} already exists`)
					return
				}
				await post('/newuser', {
					uid: this.create.uid.trim(),
					displayname: this.create.displayname,
					password: this.create.password,
					email: this.create.email,
					groups: this.create.groups.split(',').map((g) => g.trim()).filter(Boolean),
					admingroups: [],
					quota: this.create.quota,
					managerids: [],
				})
				showSuccess(`Created ${this.create.uid}`)
				this.create.open = false
			} catch (error) {
				showError(error.message)
			} finally {
				this.create.busy = false
				await this.poller.refresh('data')
			}
		},
		askDelete(row) {
			this.confirm = {
				open: true,
				title: 'Delete user',
				message: `Permanently delete ${row.uid} and all their files?`,
				confirmLabel: 'Delete user',
				phrase: row.uid,
				danger: true,
			}
			this.pendingAction = () => this.remove(row.uid)
		},
		askDeleteGroup(row) {
			this.confirm = {
				open: true,
				title: 'Delete group',
				message: `Delete group ${row.gid}? Members keep their accounts.`,
				confirmLabel: 'Delete group',
				phrase: '',
				danger: true,
			}
			this.pendingAction = () => this.removeGroup(row.gid)
		},
		async runConfirmed() {
			const action = this.pendingAction
			this.confirm.open = false
			this.pendingAction = null
			if (action) {
				await action()
			}
		},
		async remove(uid) {
			try {
				await get(`/deleteuser/${encodeURIComponent(uid)}`)
				showSuccess(`Deleted ${uid}`)
			} catch (error) {
				showError(error.message)
			} finally {
				await this.poller.refresh('data')
			}
		},
		async addGroup() {
			try {
				await get(`/addgroup/${encodeURIComponent(this.newGroup.trim())}`)
				showSuccess(`Added ${this.newGroup.trim()}`)
				this.newGroup = ''
			} catch (error) {
				showError(error.message)
			} finally {
				await this.poller.refresh('data')
			}
		},
		async removeGroup(gid) {
			try {
				await get(`/deletegroup/${encodeURIComponent(gid)}`)
				showSuccess(`Deleted ${gid}`)
			} catch (error) {
				showError(error.message)
			} finally {
				await this.poller.refresh('data')
			}
		},
		openNotify(who, group) {
			this.notify = { open: true, who, group, message: '' }
		},
		async sendNotify() {
			try {
				await post(this.notify.group ? '/notifygroup' : '/notifyuser', {
					who: this.notify.who,
					what: this.notify.message,
				})
				showSuccess('Notification sent')
				this.notify.open = false
			} catch (error) {
				showError(error.message)
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-toolbar {
	display: flex;
	align-items: flex-end;
	gap: 8px;
	flex-wrap: wrap;
	margin-bottom: 10px;
	max-width: 620px;
}

.nc-tower-form {
	display: flex;
	flex-direction: column;
	gap: 10px;
	padding-bottom: 6px;
}

.nc-tower-badge {
	padding: 1px 8px;
	border-radius: var(--border-radius-pill, 999px);
	background: var(--color-primary-element);
	color: var(--color-primary-element-text);
	font-size: 0.8em;
}

.nc-tower-good { color: var(--color-success); }
</style>
