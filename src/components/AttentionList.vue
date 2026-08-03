<template>
	<div v-if="items.length" class="nc-tower-attention">
		<h3 class="nc-tower-attention__title">Needs attention</h3>
		<ul class="nc-tower-attention__list">
			<li v-for="(item, index) in items" :key="index" class="nc-tower-attention__item">
				<SeverityDot :level="item.severity" />
				<div class="nc-tower-attention__text">
					<strong>{{ item.title }}</strong>
					<span v-if="item.detail" class="nc-tower-attention__detail">{{ item.detail }}</span>
				</div>
			</li>
		</ul>
	</div>
</template>

<script>
import SeverityDot from './SeverityDot.vue'

export default {
	name: 'AttentionList',
	components: { SeverityDot },
	props: {
		items: {
			type: Array,
			default: () => [],
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
	}

	&__detail {
		color: var(--color-text-maxcontrast);
		font-size: 0.9em;
	}
}
</style>
