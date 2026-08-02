<template>
	<section class="tower-section" :class="{ 'tower-section--open': open }">
		<header class="tower-section__head" @click="toggle">
			<button class="tower-section__toggle"
				type="button"
				:aria-expanded="String(open)"
				:aria-controls="`tower-body-${id}`">
				<span class="tower-section__caret">{{ open ? '▾' : '▸' }}</span>
				<SeverityDot :level="severity" />
				<span class="tower-section__title">{{ title }}</span>
			</button>
			<span class="tower-section__summary">{{ error ? error : summary }}</span>
			<NcLoadingIcon v-if="loading" :size="18" class="tower-section__spinner" />
			<NcButton v-else
				type="tertiary-no-background"
				:aria-label="`Refresh ${title}`"
				title="Refresh"
				@click.stop="$emit('refresh')">
				<template #icon>
					<span class="tower-section__refresh" aria-hidden="true">↻</span>
				</template>
			</NcButton>
		</header>
		<div v-show="open" :id="`tower-body-${id}`" class="tower-section__body">
			<NcNoteCard v-if="error" type="error">{{ error }}</NcNoteCard>
			<slot v-else />
		</div>
	</section>
</template>

<script>
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcLoadingIcon from '@nextcloud/vue/dist/Components/NcLoadingIcon.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import SeverityDot from './SeverityDot.vue'

/**
 * Collapsible detail section. Collapsed by default so the Ops verdict stays
 * above the fold, but anything the triage rules flagged opens itself, and the
 * operator's own open/closed choice is remembered per page.
 */
export default {
	name: 'Section',
	components: { NcButton, NcLoadingIcon, NcNoteCard, SeverityDot },
	props: {
		id: {
			type: String,
			required: true,
		},
		title: {
			type: String,
			required: true,
		},
		summary: {
			type: String,
			default: '',
		},
		severity: {
			type: String,
			default: 'ok',
		},
		loading: {
			type: Boolean,
			default: false,
		},
		error: {
			type: String,
			default: '',
		},
		defaultOpen: {
			type: Boolean,
			default: false,
		},
	},
	data() {
		return { open: this.defaultOpen }
	},
	watch: {
		severity(level) {
			// Escalation pulls the section open once; collapsing it again sticks.
			if ((level === 'warn' || level === 'crit') && this.stored() === null) {
				this.open = true
			}
		},
	},
	created() {
		const stored = this.stored()
		if (stored !== null) {
			this.open = stored
		} else if (this.severity === 'warn' || this.severity === 'crit') {
			this.open = true
		}
	},
	methods: {
		storageKey() {
			return `nc_tower.section.${this.id}`
		},
		stored() {
			try {
				const raw = window.localStorage.getItem(this.storageKey())
				return raw === null ? null : raw === '1'
			} catch (error) {
				return null
			}
		},
		toggle() {
			this.open = !this.open
			try {
				window.localStorage.setItem(this.storageKey(), this.open ? '1' : '0')
			} catch (error) {
				// private mode / storage disabled — collapse state just won't persist
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.tower-section {
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
	background: var(--color-main-background);
	margin-bottom: 10px;

	&__head {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 10px;
		cursor: pointer;
		min-height: 44px;
	}

	&__toggle {
		display: flex;
		align-items: center;
		gap: 10px;
		background: none;
		border: none;
		padding: 0;
		margin: 0;
		font: inherit;
		color: inherit;
		cursor: pointer;
		flex: 0 0 auto;
	}

	&__caret {
		color: var(--color-text-maxcontrast);
		width: 12px;
	}

	&__title {
		font-weight: 600;
		white-space: nowrap;
	}

	&__summary {
		flex: 1 1 auto;
		color: var(--color-text-maxcontrast);
		font-size: 0.9em;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	&__refresh {
		font-size: 16px;
		line-height: 1;
	}

	&__spinner {
		flex: 0 0 auto;
		margin-inline-end: 8px;
	}

	&__body {
		padding: 4px 10px 12px;
		border-top: 1px solid var(--color-border);
	}
}

@media (max-width: 720px) {
	.tower-section__summary { display: none; }
}
</style>
