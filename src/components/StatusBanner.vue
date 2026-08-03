<template>
	<div class="nc-tower-verdict" :class="`nc-tower-verdict--${level}`">
		<div class="nc-tower-verdict__headline">
			<SeverityDot :level="level" />
			<strong class="nc-tower-verdict__word">{{ headline }}</strong>
			<span v-if="subtitle" class="nc-tower-verdict__sub">{{ subtitle }}</span>
			<span class="nc-tower-verdict__spacer" />
			<span v-if="updated" class="nc-tower-verdict__stamp">updated {{ updated }}</span>
			<NcButton type="secondary" :disabled="busy" @click="$emit('refresh')">
				{{ busy ? 'Refreshing…' : 'Refresh all' }}
			</NcButton>
		</div>
		<ul v-if="facts.length" class="nc-tower-verdict__facts">
			<li v-for="fact in facts" :key="fact">{{ fact }}</li>
		</ul>
	</div>
</template>

<script>
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import SeverityDot from './SeverityDot.vue'

export default {
	name: 'StatusBanner',
	components: { NcButton, SeverityDot },
	props: {
		level: {
			type: String,
			default: 'ok',
		},
		count: {
			type: Number,
			default: 0,
		},
		facts: {
			type: Array,
			default: () => [],
		},
		updated: {
			type: String,
			default: '',
		},
		busy: {
			type: Boolean,
			default: false,
		},
	},
	computed: {
		headline() {
			return { ok: 'All clear', warn: 'Needs attention', crit: 'Critical' }[this.level] || 'Unknown'
		},
		subtitle() {
			if (this.level === 'ok') {
				return 'no issues detected'
			}
			return `${this.count} finding${this.count === 1 ? '' : 's'}`
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-verdict {
	border: 1px solid var(--color-border);
	border-inline-start: 4px solid var(--color-success);
	border-radius: var(--border-radius-large, 8px);
	background: var(--color-main-background);
	padding: 12px 14px;
	margin-bottom: 12px;

	&--warn { border-inline-start-color: var(--color-warning); }
	&--crit { border-inline-start-color: var(--color-error); }

	&__headline {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}

	&__word {
		font-size: 1.2em;
	}

	&__sub {
		color: var(--color-text-maxcontrast);
	}

	&__spacer {
		flex: 1 1 auto;
	}

	&__stamp {
		color: var(--color-text-maxcontrast);
		font-size: 0.85em;
	}

	&__facts {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 16px;
		margin: 10px 0 0;
		padding: 0;
		list-style: none;
		color: var(--color-text-maxcontrast);
		font-size: 0.9em;
	}
}
</style>
