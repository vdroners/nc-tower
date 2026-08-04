<template>
	<div v-if="visible.length || snoozed.length" class="nc-tower-attention">
		<h3 class="nc-tower-attention__title">Needs attention</h3>
		<ul v-if="visible.length" class="nc-tower-attention__list">
			<li v-for="(item, index) in visible" :key="'v-' + index" class="nc-tower-attention__item">
				<SeverityDot :level="item.severity" />
				<div class="nc-tower-attention__text">
					<strong>{{ item.title }}</strong>
					<span v-if="item.detail" class="nc-tower-attention__detail">{{ item.detail }}</span>
				</div>
				<button
					v-if="item.severity !== 'crit'"
					type="button"
					class="nc-tower-attention__snooze"
					title="Snooze for 7 days"
					@click="snooze(item)">
					Snooze
				</button>
			</li>
		</ul>
		<p v-else class="nc-tower-muted">All findings snoozed.</p>
		<div v-if="snoozed.length" class="nc-tower-attention__foot">
			<button type="button" class="nc-tower-chip" @click="showSnoozed = !showSnoozed">
				{{ snoozed.length }} snoozed
			</button>
			<ul v-if="showSnoozed" class="nc-tower-attention__list nc-tower-attention__list--snoozed">
				<li v-for="(item, index) in snoozed" :key="'s-' + index" class="nc-tower-attention__item">
					<SeverityDot :level="item.severity" />
					<div class="nc-tower-attention__text">
						<strong>{{ item.title }}</strong>
						<span v-if="item.detail" class="nc-tower-attention__detail">{{ item.detail }}</span>
					</div>
					<button type="button" class="nc-tower-attention__snooze" @click="unsnooze(item)">
						Unsnooze
					</button>
				</li>
			</ul>
		</div>
	</div>
</template>

<script>
import SeverityDot from './SeverityDot.vue'
import { loadSnoozes, partitionItems, snoozeItem, unsnoozeItem } from '../services/attentionSnooze.js'

export default {
	name: 'AttentionList',
	components: { SeverityDot },
	props: {
		items: {
			type: Array,
			default: () => [],
		},
	},
	data() {
		return {
			snoozes: loadSnoozes(),
			showSnoozed: false,
		}
	},
	computed: {
		partitioned() {
			return partitionItems(this.items, this.snoozes)
		},
		visible() {
			return this.partitioned.visible
		},
		snoozed() {
			return this.partitioned.snoozed
		},
	},
	methods: {
		snooze(item) {
			this.snoozes = { ...snoozeItem(item) }
			this.$emit('change', this.visible)
		},
		unsnooze(item) {
			this.snoozes = { ...unsnoozeItem(item) }
			this.$emit('change', this.visible)
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-attention {
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
	background: var(--color-main-background);
	padding: 10px 14px 12px;
	margin-bottom: 12px;

	&__title {
		margin: 0 0 8px;
		font-size: 1em;
		color: var(--color-text-maxcontrast);
	}

	&__list {
		margin: 0;
		padding: 0;
		list-style: none;

		&--snoozed { margin-top: 8px; opacity: 0.75; }
	}

	&__item {
		display: flex;
		align-items: baseline;
		gap: 10px;
		padding: 5px 0;
		border-bottom: 1px solid var(--color-border);

		&:last-child { border-bottom: none; }
	}

	&__text {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 10px;
		flex: 1 1 auto;
	}

	&__detail {
		color: var(--color-text-maxcontrast);
		font-size: 0.9em;
	}

	&__snooze {
		border: 0;
		background: transparent;
		color: var(--color-text-maxcontrast);
		font-size: 0.8em;
		cursor: pointer;
		text-decoration: underline;
		padding: 0;
		flex: 0 0 auto;

		&:hover { color: var(--color-main-text); }
	}

	&__foot {
		margin-top: 8px;
	}
}
</style>
