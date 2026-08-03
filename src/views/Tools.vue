<template>
	<div class="nc-tower-view">
		<h2>Tools</h2>
		<p class="nc-tower-view__lead">
			Break-glass deep links. Anything Control Tower deliberately does not do —
			host shell, firewall editors, VPN peers, prune — lives behind these.
		</p>

		<NcNoteCard v-if="error" type="error">{{ error }}</NcNoteCard>
		<NcLoadingIcon v-else-if="loading" :size="32" />

		<section v-for="group in groups" :key="group.title" class="nc-tower-tools-group">
			<h3 class="nc-tower-tools-group__title">{{ group.title }}</h3>
			<div class="nc-tower-tools-grid">
				<component :is="tool.url ? 'a' : 'div'"
					v-for="tool in group.tools"
					:key="tool.title"
					class="nc-tower-tool"
					:class="{ 'nc-tower-tool--inert': !tool.url }"
					:href="tool.url || null"
					:target="tool.url ? '_blank' : null"
					:rel="tool.url ? 'noopener noreferrer' : null">
					<span class="nc-tower-tool__title">
						<NcTowerIcon v-if="tool.url" name="external-link" :size="15" />
						{{ tool.title }}
					</span>
					<span v-if="tool.url" class="nc-tower-tool__url">{{ hostOf(tool.url) }}</span>
					<span v-if="tool.note" class="nc-tower-tool__note">{{ tool.note }}</span>
				</component>
			</div>
		</section>
	</div>
</template>

<script>
import NcLoadingIcon from '@nextcloud/vue/dist/Components/NcLoadingIcon.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import NcTowerIcon from '../components/NcTowerIcon.vue'
import { get } from '../services/api.js'

export default {
	name: 'Tools',
	components: { NcLoadingIcon, NcNoteCard, NcTowerIcon },
	data() {
		return { groups: [], loading: true, error: '' }
	},
	async created() {
		try {
			const data = await get('/tower/tools')
			this.groups = data.groups || []
		} catch (error) {
			this.error = error.message
		} finally {
			this.loading = false
		}
	},
	methods: {
		hostOf(url) {
			try {
				return new URL(url).host
			} catch (error) {
				return url
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-tools-group {
	margin-bottom: 22px;

	&__title {
		margin: 0 0 8px;
		font-size: 1em;
		color: var(--color-text-maxcontrast);
	}
}

.nc-tower-tools-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
	gap: 10px;
}

.nc-tower-tool {
	display: flex;
	flex-direction: column;
	gap: 3px;
	padding: 12px 14px;
	min-height: 66px;
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
	background: var(--color-main-background);
	text-decoration: none;
	color: var(--color-main-text);

	&:hover:not(&--inert) {
		background: var(--color-background-hover);
		border-color: var(--color-primary-element);
	}

	&--inert { opacity: 0.75; }

	&__title {
		font-weight: 600;
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}

	&__url,
	&__note {
		font-size: 0.85em;
		color: var(--color-text-maxcontrast);
	}
}
</style>
