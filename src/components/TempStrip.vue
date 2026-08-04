<template>
	<div class="nc-tower-temp-strip">
		<div v-for="group in groups" :key="group.chip" class="nc-tower-temp-strip__group">
			<h4 class="nc-tower-temp-strip__chip">{{ group.chip }}</h4>
			<div v-for="row in group.sensors" :key="row.label + row.chip" class="nc-tower-temp-strip__row">
				<span class="nc-tower-temp-strip__label" :title="row.label">{{ row.label }}</span>
				<div class="nc-tower-temp-strip__track">
					<div
						class="nc-tower-temp-strip__fill"
						:class="`nc-tower-temp-strip__fill--${zone(row.celsius)}`"
						:style="{ width: `${barWidth(row.celsius)}%` }" />
				</div>
				<span class="nc-tower-temp-strip__value">{{ formatTemp(row.celsius) }}</span>
			</div>
		</div>
		<p v-if="!groups.length" class="nc-tower-muted">No temperature sensors</p>
	</div>
</template>

<script>
/**
 * Color-zoned horizontal bars for hwmon sensors. House style (no gauges).
 * Green &lt;60, amber 60–79, red 80+.
 */
export default {
	name: 'TempStrip',
	props: {
		sensors: {
			type: Array,
			default: () => [],
		},
		maxC: {
			type: Number,
			default: 100,
		},
	},
	computed: {
		groups() {
			const byChip = {}
			for (const s of this.sensors || []) {
				const chip = s.chip || s.source || 'sensor'
				if (!byChip[chip]) {
					byChip[chip] = []
				}
				byChip[chip].push(s)
			}
			return Object.entries(byChip)
				.map(([chip, sensors]) => ({
					chip,
					sensors: [...sensors].sort((a, b) => Number(b.celsius || 0) - Number(a.celsius || 0)),
				}))
				.sort((a, b) => a.chip.localeCompare(b.chip))
		},
	},
	methods: {
		zone(c) {
			const n = Number(c)
			if (!Number.isFinite(n)) {
				return 'ok'
			}
			if (n >= 80) {
				return 'crit'
			}
			return n >= 60 ? 'warn' : 'ok'
		},
		barWidth(c) {
			const n = Number(c)
			if (!Number.isFinite(n)) {
				return 0
			}
			return Math.max(0, Math.min(100, (n / this.maxC) * 100))
		},
		formatTemp(c) {
			const n = Number(c)
			return Number.isFinite(n) ? `${Math.round(n)}°C` : '—'
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-temp-strip {
	display: flex;
	flex-direction: column;
	gap: 14px;

	&__group {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	&__chip {
		margin: 0 0 2px;
		font-size: 0.9em;
		color: var(--color-text-maxcontrast);
	}

	&__row {
		display: grid;
		grid-template-columns: minmax(80px, 140px) 1fr 52px;
		gap: 8px;
		align-items: center;
	}

	&__label {
		font-size: 0.85em;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	&__track {
		height: 8px;
		border-radius: 4px;
		background: var(--color-background-darker);
		overflow: hidden;
	}

	&__fill {
		height: 100%;
		border-radius: 4px;
		background: var(--color-success, #3fa35f);

		&--warn { background: var(--color-warning); }
		&--crit { background: var(--color-error); }
	}

	&__value {
		font-variant-numeric: tabular-nums;
		font-size: 0.85em;
		text-align: right;
	}
}
</style>
