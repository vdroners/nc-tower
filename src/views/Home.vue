<template>
	<div class="tower-view">
		<StatusBanner :level="verdict.level"
			:count="verdict.items.length"
			:facts="facts"
			:updated="updatedAt"
			:busy="busy"
			@refresh="refreshAll" />

		<AttentionList :items="verdict.items" />

		<div class="tower-cards">
			<a v-for="card in cards" :key="card.id" class="tower-card" :href="url(card.route)">
				<span class="tower-card__label">{{ card.label }}</span>
				<strong class="tower-card__value">{{ card.value }}</strong>
				<span class="tower-card__note">{{ card.note }}</span>
			</a>
		</div>

		<NcNoteCard v-if="sidecarDown" type="error">
			The Control Tower sidecar is not answering — host, Docker and stack views will be
			empty until it is back. Check the <code>nc_tower_sidecar</code> container and that
			<code>nc_tower_sidecar_token</code> matches <code>sidecar/.env</code>.
		</NcNoteCard>
	</div>
</template>

<script>
import { generateUrl } from '@nextcloud/router'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import AttentionList from '../components/AttentionList.vue'
import StatusBanner from '../components/StatusBanner.vue'
import { get } from '../services/api.js'
import fmt from '../services/format.js'
import { assess } from '../services/health.js'
import Poller from '../services/poll.js'

/**
 * Landing page: the same verdict Ops computes, plus one tile per area so an
 * operator can see where to go before clicking anything.
 */
export default {
	name: 'Home',
	components: { AttentionList, NcNoteCard, StatusBanner },
	data() {
		return {
			host: {},
			containers: {},
			smart: {},
			inbox: {},
			system: {},
			users: {},
			updates: {},
			busy: false,
			updatedAt: '',
			sidecarDown: false,
		}
	},
	computed: {
		verdict() {
			return assess({
				host: this.host,
				containers: this.containers,
				smart: this.smart,
				inbox: this.inbox,
			})
		},
		facts() {
			const out = []
			if (this.system.nc_version) {
				out.push(`Nextcloud ${this.system.nc_version}`)
			}
			if (this.system.ram_percent) {
				out.push(`RAM ${this.system.ram_percent}`)
			}
			if (this.host.uptime_s) {
				out.push(`up ${fmt.duration(this.host.uptime_s)}`)
			}
			return out
		},
		cards() {
			const counts = this.containers.counts || {}
			const smartDisks = this.smart.disks || []
			return [
				{
					id: 'ops',
					label: 'Containers',
					value: counts.total != null ? `${counts.running || 0}/${counts.total}` : '—',
					note: 'running',
					route: 'ops',
				},
				{
					id: 'smart',
					label: 'Drives',
					value: smartDisks.length ? `${smartDisks.filter((d) => d.health === 'PASS').length}/${smartDisks.length}` : '—',
					note: 'SMART PASS',
					route: 'ops',
				},
				{
					id: 'host',
					label: 'CPU',
					value: this.host.cpu_pct != null ? `${this.host.cpu_pct}%` : '—',
					note: this.host.package_temp_c != null ? `${this.host.package_temp_c}°C package` : 'host load',
					route: 'host',
				},
				{
					id: 'users',
					label: 'Users',
					value: this.users.userCount != null ? String(this.users.userCount) : '—',
					note: `${this.users.adminCount || 0} admin`,
					route: 'user',
				},
				{
					id: 'apps',
					label: 'App updates',
					value: this.updates.appscount != null ? String(this.updates.appscount) : '—',
					note: 'available',
					route: 'apps',
				},
				{
					id: 'inbox',
					label: 'Ops alerts',
					value: String((this.inbox.critical_recent || []).length),
					note: 'critical',
					route: 'ops',
				},
			]
		},
	},
	created() {
		// Not in data(): observing timer handles and a Map buys nothing.
		this.poller = new Poller()
		const p = this.poller
		p.add('containers', () => this.fetch('containers', '/tower/containers'), 30000)
		p.add('host', () => this.fetch('host', '/tower/host'), 30000)
		p.add('inbox', () => this.fetch('inbox', '/tower/ops-inbox'), 60000)
		p.add('system', () => this.fetch('system', '/systeminfo'), 120000)
		p.add('users', () => this.fetch('users', '/usercount'), 300000)
		p.add('updates', () => this.fetch('updates', '/appupdates'), 300000)
		p.add('smart', () => this.fetch('smart', '/tower/smart'), 300000)
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
			try {
				this[key] = await get(path)
				this.updatedAt = new Date().toLocaleTimeString()
				if (path.startsWith('/tower/')) {
					this.sidecarDown = false
				}
			} catch (error) {
				if (path.startsWith('/tower/') && (error.data?.error === 'sidecar_unavailable' || error.status === 502)) {
					this.sidecarDown = true
				}
			}
		},
		async refreshAll() {
			this.busy = true
			try {
				await this.poller.refresh()
			} finally {
				this.busy = false
			}
		},
		url(route) {
			return generateUrl(`/apps/nc_tower/${route}`)
		},
	},
}
</script>

<style lang="scss" scoped>
.tower-cards {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
	gap: 10px;
	margin-bottom: 14px;
}

.tower-card {
	display: flex;
	flex-direction: column;
	gap: 2px;
	padding: 14px;
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
	background: var(--color-main-background);
	text-decoration: none;
	color: var(--color-main-text);

	&:hover {
		background: var(--color-background-hover);
		border-color: var(--color-primary-element);
	}

	&__label {
		color: var(--color-text-maxcontrast);
		font-size: 0.85em;
	}

	&__value {
		font-size: 1.6em;
		line-height: 1.2;
	}

	&__note {
		color: var(--color-text-maxcontrast);
		font-size: 0.8em;
	}
}
</style>
