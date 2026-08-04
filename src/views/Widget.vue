<template>
	<div class="nc-tower-widget">
		<NcLoadingIcon v-if="loading" :size="24" />
		<template v-else>
			<div class="nc-tower-widget__verdict" :class="`nc-tower-widget__verdict--${displayLevel}`">
				<SeverityDot :level="displayLevel" />
				<strong>{{ headline }}</strong>
			</div>
			<ul v-if="displayItems.length" class="nc-tower-widget__items">
				<li v-for="(item, index) in displayItems.slice(0, 4)" :key="index">
					<SeverityDot :level="item.severity" />
					<span>{{ item.title }}</span>
				</li>
			</ul>
			<p v-else class="nc-tower-widget__facts">{{ facts }}</p>
			<a class="nc-tower-widget__link" :href="opsUrl">Open NC Tower →</a>
		</template>
	</div>
</template>

<script>
import { generateUrl } from '@nextcloud/router'
import NcLoadingIcon from '@nextcloud/vue/dist/Components/NcLoadingIcon.js'
import SeverityDot from '../components/SeverityDot.vue'
import { get } from '../services/api.js'
import { assess, WARN } from '../services/health.js'

export default {
	name: 'Widget',
	components: { NcLoadingIcon, SeverityDot },
	data() {
		return {
			loading: true,
			host: {},
			containers: {},
			smart: {},
			inbox: {},
			fetchOk: 0,
			fetchFail: 0,
		}
	},
	computed: {
		verdict() {
			return assess({ host: this.host, containers: this.containers, smart: this.smart, inbox: this.inbox })
		},
		sidecarDown() {
			return this.fetchOk === 0 && this.fetchFail > 0
		},
		displayLevel() {
			if (this.sidecarDown) {
				return WARN
			}
			return this.verdict.level
		},
		displayItems() {
			if (this.sidecarDown) {
				return [{ severity: WARN, title: 'NC Tower sidecar unreachable' }]
			}
			return this.verdict.items
		},
		headline() {
			if (this.sidecarDown) {
				return 'Sidecar down'
			}
			// Never claim "All clear" unless at least one fetch succeeded.
			if (this.fetchOk === 0) {
				return 'Status unknown'
			}
			return { ok: 'All clear', warn: 'Needs attention', crit: 'Critical' }[this.verdict.level]
		},
		facts() {
			if (this.sidecarDown) {
				return 'Host and Docker checks did not load'
			}
			const counts = this.containers.counts || {}
			return `${counts.running || 0}/${counts.total || 0} containers running`
		},
		opsUrl() {
			return generateUrl('/apps/nc_tower/ops')
		},
	},
	async created() {
		const load = async (key, path) => {
			try {
				this[key] = await get(path)
				this.fetchOk += 1
			} catch (error) {
				this.fetchFail += 1
			}
		}
		await Promise.all([
			load('containers', '/tower/containers'),
			load('host', '/tower/host'),
			load('inbox', '/tower/ops-inbox'),
			load('smart', '/tower/smart'),
		])
		this.loading = false
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-widget {
	display: flex;
	flex-direction: column;
	gap: 8px;
	padding: 4px 2px;

	&__verdict {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	&__items {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;

		li {
			display: flex;
			align-items: baseline;
			gap: 8px;
			font-size: 0.9em;
		}
	}

	&__facts {
		margin: 0;
		color: var(--color-text-maxcontrast);
		font-size: 0.9em;
	}

	&__link {
		font-size: 0.9em;
		color: var(--color-primary-element);
	}
}
</style>
