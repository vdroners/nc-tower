<template>
	<div class="nc-tower-view">
		<h2>Services</h2>
		<p class="nc-tower-view__lead">
			Every external console this host runs, and how much of it NC Tower has taken
			over. Anything marked superseded is here for reference — the work is done in Tower.
		</p>

		<NcNoteCard v-if="error" type="error">{{ error }}</NcNoteCard>
		<NcLoadingIcon v-else-if="loading" :size="32" />
		<NcNoteCard v-else-if="!hasConfiguredTools" type="info">
			No tool URLs configured. Set them in <strong>Settings → NC Tower</strong>.
		</NcNoteCard>

		<div v-if="!loading" class="nc-tower-chips">
			<span class="nc-tower-chip">{{ counts.up }} reachable</span>
			<span class="nc-tower-chip">{{ counts.down }} down</span>
			<span class="nc-tower-chip">{{ counts.superseded }} superseded by Tower</span>
		</div>

		<section v-for="group in groups" :key="group.title" class="nc-tower-service-group">
			<h3 class="nc-tower-service-group__title">{{ group.title }}</h3>
			<p v-if="group.blurb" class="nc-tower-muted">{{ group.blurb }}</p>
			<div class="nc-tower-service-grid">
				<component :is="row.url ? 'a' : 'div'"
					v-for="row in group.rows"
					:key="row.title"
					class="nc-tower-service"
					:class="{
						'nc-tower-service--superseded': row.supersededBy,
						'nc-tower-service--down': row.probe && !row.probe.reachable,
					}"
					:href="row.url || null"
					:target="row.url ? '_blank' : null"
					:rel="row.url ? 'noopener noreferrer' : null">
					<div class="nc-tower-service__head">
						<SeverityDot :level="dotFor(row)" />
						<span class="nc-tower-service__title">{{ row.title }}</span>
						<NcTowerIcon v-if="row.url" name="external-link" :size="14" />
					</div>
					<span v-if="row.supersededBy" class="nc-tower-service__note">
						Superseded — use {{ row.supersededBy }}
					</span>
					<span v-else-if="row.gap" class="nc-tower-service__note">Still needed for: {{ row.gap }}</span>
					<span v-else-if="row.note" class="nc-tower-service__note">{{ row.note }}</span>
					<span class="nc-tower-service__meta">{{ metaFor(row) }}</span>
				</component>
			</div>
		</section>
	</div>
</template>

<script>
import NcLoadingIcon from '@nextcloud/vue/dist/Components/NcLoadingIcon.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import NcTowerIcon from '../components/NcTowerIcon.vue'
import SeverityDot from '../components/SeverityDot.vue'
import { get } from '../services/api.js'
import Poller from '../services/poll.js'

/**
 * The old page was a flat grid of equal-looking links, which hid two things:
 * which consoles NC Tower had already replaced, and whether any of them
 * were even up. OrcaSlicer was down and the page gave no hint.
 *
 * Probe rule: any HTTP answer counts as reachable. Guacamole and MediaMTX both
 * return 404 at `/` while perfectly healthy, so only a connection failure counts
 * as down — otherwise this page would cry wolf on two working services.
 */
const ABSORBED = [
	['System Health', 'Ops › Host and storage', 'webmin'],
	['Docker', 'Ops › Containers', 'webmin'],
	['Docker Stacks', 'Ops › Stacks', 'webmin'],
	['NVIDIA GPU', 'Ops › GPU', 'webmin'],
]

const BREAK_GLASS = [
	{ title: 'Webmin', key: 'webmin', gap: 'chassis PWM writes, cron edits, package pinning' },
	{ title: 'Portainer', key: 'portainer', gap: 'env and resource editors, rename, prune' },
	{ title: 'SMART Health', key: 'webmin', gap: 'per-attribute detail' },
	{ title: 'Backup Mgr', key: 'webmin', gap: 'delete and restore — run and status are in Tower' },
	{ title: 'Fan Control (chassis PWM)', key: 'webmin', gap: 'PWM writes — GPU fans are in Tower' },
]

const APPS = [
	['Uptime Kuma', 'kuma'], ['Caddy Proxy', 'caddy'], ['Guacamole', 'guacamole'],
	['WebODM', 'webodm'], ['OrcaSlicer', 'orcaslicer'], ['ADSB Feeder', 'adsb'],
	['MediaMTX', 'mediamtx'], ['Nextcloud', 'nextcloud'],
]

export default {
	name: 'Tools',
	components: { NcLoadingIcon, NcNoteCard, NcTowerIcon, SeverityDot },
	data() {
		return { tools: {}, probes: {}, probesLoaded: false, loading: true, error: '' }
	},
	computed: {
		hasConfiguredTools() {
			const flat = (this.tools.groups || []).flatMap((group) => group.tools || [])
			return flat.some((tool) => tool.url)
		},
		groups() {
			const flat = (this.tools.groups || []).flatMap((group) => group.tools || [])
			const urlOf = (title) => (flat.find((tool) => tool.title === title) || {}).url || ''
			const probe = (key) => this.probes[key] || null

			const filterConfigured = (rows) => rows.filter((row) => row.url || row.note)

			return [
				{
					title: 'Absorbed into NC Tower',
					blurb: 'Tower does these now. The links remain only as a second opinion.',
					rows: filterConfigured(ABSORBED.map(([title, where, key]) => ({
						title, url: urlOf(title), supersededBy: where, probe: probe(key),
					}))),
				},
				{
					title: 'Break-glass — still needed',
					blurb: 'What Tower deliberately does not do yet. Each says what it is still for.',
					rows: filterConfigured(BREAK_GLASS.map((row) => ({ ...row, url: urlOf(row.title), probe: probe(row.key) }))),
				},
				{
					title: 'External applications',
					blurb: 'Other services on this host, not administration surfaces. Configure URLs in Settings → NC Tower.',
					rows: filterConfigured(APPS.map(([title, key]) => ({ title, url: urlOf(title), probe: probe(key) }))),
				},
				{
					title: 'VPN',
					blurb: '',
					rows: [{ title: 'WireGuard', url: '', note: 'Managed in the Nextcloud WireGuard app.' }],
				},
			].filter((group) => group.rows.length > 0)
		},
		counts() {
			const rows = this.groups.flatMap((group) => group.rows)
			return {
				up: rows.filter((row) => row.probe && row.probe.reachable).length,
				down: rows.filter((row) => row.probe && !row.probe.reachable).length,
				superseded: rows.filter((row) => row.supersededBy).length,
			}
		},
	},
	created() {
		this.poller = new Poller()
		this.poller.add('services', () => this.load(), 120000)
		this.poller.start()
	},
	beforeDestroy() {
		this.poller.stop()
	},
	methods: {
		dotFor(row) {
			if (!row.probe) {
				return 'idle'
			}
			if (!row.probe.reachable) {
				return 'crit'
			}
			return row.supersededBy ? 'idle' : 'ok'
		},
		metaFor(row) {
			if (row.probe) {
				return row.probe.reachable
					? `up · HTTP ${row.probe.http} · ${row.probe.ms} ms`
					: `down · ${row.probe.detail || 'no answer'}`
			}
			if (row.url) {
				return this.probesLoaded ? 'no probe configured' : 'checking…'
			}
			return ''
		},
		async load() {
			try {
				const [tools, services] = await Promise.all([
					get('/tower/tools'),
					get('/tower/services').catch(() => ({ services: [] })),
				])
				this.tools = tools
				this.probes = Object.fromEntries((services.services || []).map((row) => [row.name, row]))
				this.probesLoaded = true
				this.error = ''
			} catch (error) {
				this.error = error.message
			} finally {
				this.loading = false
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-service-group {
	margin-bottom: 22px;

	&__title {
		margin: 0 0 2px;
		font-size: 1em;
	}
}

.nc-tower-service-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
	gap: 10px;
	margin-top: 8px;
}

.nc-tower-service {
	display: flex;
	flex-direction: column;
	gap: 3px;
	padding: 12px 14px;
	min-height: 76px;
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
	background: var(--color-main-background);
	text-decoration: none;
	color: var(--color-main-text);

	&:hover {
		background: var(--color-background-hover);
		border-color: var(--color-primary-element);
	}

	&--superseded { opacity: 0.68; }
	&--down { border-inline-start: 3px solid var(--color-error); }

	&__head {
		display: flex;
		align-items: center;
		gap: 7px;
	}

	&__title { font-weight: 600; }

	&__note,
	&__meta {
		font-size: 0.82em;
		color: var(--color-text-maxcontrast);
	}
}
</style>
