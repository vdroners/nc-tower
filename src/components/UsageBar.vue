<template>
	<div class="nc-tower-usage">
		<div class="nc-tower-usage__track">
			<div class="nc-tower-usage__fill" :class="`nc-tower-usage__fill--${level}`" :style="{ width: `${clamped}%` }" />
		</div>
		<span class="nc-tower-usage__label">{{ clamped }}%</span>
	</div>
</template>

<script>
export default {
	name: 'UsageBar',
	props: {
		percent: {
			type: [Number, String],
			default: 0,
		},
		warn: {
			type: Number,
			default: 85,
		},
		crit: {
			type: Number,
			default: 95,
		},
	},
	computed: {
		clamped() {
			const n = Number(this.percent)
			return Number.isFinite(n) ? Math.max(0, Math.min(100, Math.round(n * 10) / 10)) : 0
		},
		level() {
			if (this.clamped >= this.crit) {
				return 'crit'
			}
			return this.clamped >= this.warn ? 'warn' : 'ok'
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-usage {
	display: flex;
	align-items: center;
	gap: 8px;
	min-width: 120px;

	&__track {
		flex: 1 1 auto;
		height: 6px;
		border-radius: 3px;
		background: var(--color-background-darker);
		overflow: hidden;
	}

	&__fill {
		height: 100%;
		border-radius: 3px;
		background: var(--color-primary-element);
		transition: width 0.3s ease;

		&--warn { background: var(--color-warning); }
		&--crit { background: var(--color-error); }
	}

	&__label {
		font-variant-numeric: tabular-nums;
		font-size: 0.85em;
		color: var(--color-text-maxcontrast);
	}
}
</style>
