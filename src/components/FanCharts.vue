<template>
	<div class="nc-tower-fan-charts">
		<div class="nc-tower-toolbar nc-tower-fan-charts__windows">
			<span class="nc-tower-muted">History window</span>
			<NcButton v-for="opt in windowOptions"
				:key="opt.minutes"
				:type="windowMinutes === opt.minutes ? 'primary' : 'tertiary'"
				@click="setWindow(opt.minutes)">
				{{ opt.label }}
			</NcButton>
		</div>

		<div class="nc-tower-fan-charts__gauges">
			<div v-for="fan in fans"
				:key="fanKey(fan)"
				class="nc-tower-fan-gauge"
				:class="{ 'nc-tower-fan-gauge--selected': selectedKey === fanKey(fan) }"
				role="button"
				tabindex="0"
				@click="selectedKey = fanKey(fan)"
				@keydown.enter="selectedKey = fanKey(fan)">
				<svg viewBox="0 0 64 40" class="nc-tower-fan-gauge__svg" aria-hidden="true">
					<path class="nc-tower-fan-gauge__track" d="M8 32 A24 24 0 0 1 56 32" fill="none" stroke-width="6" />
					<path class="nc-tower-fan-gauge__arc"
						:d="gaugeArc(fan.pwm_pct)"
						fill="none"
						stroke-width="6"
						stroke-linecap="round" />
				</svg>
				<span class="nc-tower-fan-gauge__label">{{ fan.header || fan.name || fanKey(fan) }}</span>
				<span class="nc-tower-fan-gauge__value">{{ formatPct(fan.pwm_pct) }}</span>
			</div>
		</div>

		<h4 class="nc-tower-subhead">RPM</h4>
		<TowerChart v-if="rpmDatasets.length"
			:datasets="rpmDatasets"
			:height="180"
			time-axis
			show-legend
			y-suffix=" rpm"
			title="Chassis fan RPM" />
		<p v-else class="nc-tower-muted">No RPM history yet — sampler writes every 30 s.</p>

		<h4 class="nc-tower-subhead">Temperatures</h4>
		<TowerChart v-if="tempDatasets.length"
			:datasets="tempDatasets"
			:height="180"
			time-axis
			show-legend
			y-suffix="°C"
			title="Temps (hwmon + GPU)" />
		<p v-else class="nc-tower-muted">No temperature history yet.</p>

		<div v-if="selectedFan" class="nc-tower-fan-op">
			<h4 class="nc-tower-subhead">
				Operating point — {{ selectedFan.header || selectedFan.name }}
			</h4>
			<svg class="nc-tower-fan-op__svg"
				viewBox="0 0 200 100"
				role="img"
				:aria-label="`Curve for ${selectedFan.header || selectedFan.name}`">
				<path class="nc-tower-fan-op__grid" d="M10 10 H190 M10 50 H190 M10 90 H190 M10 10 V90 M100 10 V90 M190 10 V90" />
				<path v-if="selectedCurvePath"
					class="nc-tower-fan-op__curve"
					:d="selectedCurvePath"
					fill="none"
					stroke-width="2" />
				<circle v-if="selectedOp"
					class="nc-tower-fan-op__dot"
					:cx="selectedOp.x"
					:cy="selectedOp.y"
					r="4" />
			</svg>
			<p class="nc-tower-muted">
				{{ relatedTempLabel }}:
				{{ relatedTempC != null ? `${relatedTempC.toFixed(1)}°C` : '—' }}
				· PWM {{ selectedFan.pwm != null ? selectedFan.pwm : '—' }}
				({{ formatPct(selectedFan.pwm_pct) }})
			</p>
		</div>
	</div>
</template>

<script>
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import TowerChart from './TowerChart.vue'
import {
	curvePath,
	historyToRpmDatasets,
	historyToTempDatasets,
	operatingPoint,
} from '../services/fanCharts.js'

const WINDOWS = [
	{ minutes: 60, label: '1h' },
	{ minutes: 360, label: '6h' },
	{ minutes: 1440, label: '24h' },
]

export default {
	name: 'FanCharts',
	components: { NcButton, TowerChart },
	props: {
		history: {
			type: Array,
			default: () => [],
		},
		fans: {
			type: Array,
			default: () => [],
		},
		temps: {
			type: Array,
			default: () => [],
		},
		windowMinutes: {
			type: Number,
			default: 60,
		},
	},
	data() {
		return {
			windowOptions: WINDOWS,
			selectedKey: '',
		}
	},
	computed: {
		rpmDatasets() {
			return historyToRpmDatasets(this.history)
		},
		tempDatasets() {
			return historyToTempDatasets(this.history)
		},
		selectedFan() {
			const list = this.fans || []
			if (!list.length) {
				return null
			}
			return list.find((fan) => this.fanKey(fan) === this.selectedKey) || list[0]
		},
		selectedCurve() {
			const fan = this.selectedFan
			if (!fan) {
				return []
			}
			if (Array.isArray(fan.curve) && fan.curve.length) {
				return fan.curve
			}
			return []
		},
		selectedCurvePath() {
			return curvePath(this.selectedCurve)
		},
		relatedTemp() {
			const list = this.temps || []
			if (!list.length) {
				return null
			}
			const chip = this.selectedFan?.chip
			if (chip) {
				const match = list.find((t) => t.chip === chip && t.celsius != null)
				if (match) {
					return match
				}
			}
			const cpu = list.find((t) => /cpu|package|tctl|die/i.test(String(t.label || '')) && t.celsius != null)
			return cpu || list.find((t) => t.celsius != null) || null
		},
		relatedTempC() {
			return this.relatedTemp?.celsius ?? null
		},
		relatedTempLabel() {
			return this.relatedTemp?.label || 'Temp'
		},
		selectedOp() {
			const fan = this.selectedFan
			if (!fan) {
				return null
			}
			return operatingPoint(this.selectedCurve, this.relatedTempC, fan.pwm)
		},
	},
	watch: {
		fans: {
			immediate: true,
			handler(list) {
				if (!list?.length) {
					this.selectedKey = ''
					return
				}
				if (!list.some((fan) => this.fanKey(fan) === this.selectedKey)) {
					this.selectedKey = this.fanKey(list[0])
				}
			},
		},
	},
	methods: {
		fanKey(fan) {
			return String(fan?.index ?? fan?.header ?? fan?.name ?? '')
		},
		formatPct(pct) {
			return pct != null && Number.isFinite(Number(pct)) ? `${Number(pct).toFixed(0)}%` : '—'
		},
		setWindow(minutes) {
			this.$emit('update:windowMinutes', minutes)
		},
		/**
		 * SVG arc for a semicircle gauge (0–100%).
		 * @param {number|null|undefined} pct
		 * @return {string}
		 */
		gaugeArc(pct) {
			const value = Math.min(100, Math.max(0, Number(pct) || 0))
			const angle = Math.PI * (1 - value / 100)
			const x = 32 + 24 * Math.cos(angle)
			const y = 32 - 24 * Math.sin(angle)
			const large = value > 50 ? 1 : 0
			return `M8 32 A24 24 0 ${large} 1 ${x.toFixed(1)} ${y.toFixed(1)}`
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-fan-charts {
	margin-top: 12px;
}

.nc-tower-fan-charts__windows {
	max-width: none;
}

.nc-tower-fan-charts__gauges {
	display: flex;
	flex-wrap: wrap;
	gap: 10px;
	margin: 10px 0 4px;
}

.nc-tower-fan-gauge {
	display: flex;
	flex-direction: column;
	align-items: center;
	min-width: 72px;
	padding: 6px 8px;
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
	cursor: pointer;
	background: var(--color-main-background);

	&--selected {
		border-color: var(--color-primary-element);
	}

	&__svg {
		width: 64px;
		height: 40px;
	}

	&__track {
		stroke: var(--color-border-dark, var(--color-border));
	}

	&__arc {
		stroke: var(--color-primary-element);
	}

	&__label {
		font-size: 0.75em;
		color: var(--color-text-maxcontrast);
		max-width: 80px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	&__value {
		font-weight: 600;
		font-size: 0.85em;
	}
}

.nc-tower-fan-op {
	margin-top: 8px;

	&__svg {
		width: 100%;
		max-width: 360px;
		height: 120px;
		background: var(--color-background-dark);
		border-radius: var(--border-radius, 4px);
	}

	&__grid {
		stroke: var(--color-border);
		stroke-width: 0.5;
		fill: none;
	}

	&__curve {
		stroke: var(--color-primary-element);
	}

	&__dot {
		fill: var(--color-error, #e9322d);
		stroke: var(--color-main-background);
		stroke-width: 1;
	}
}

.nc-tower-toolbar {
	display: flex;
	align-items: center;
	gap: 8px;
	flex-wrap: wrap;
	margin-bottom: 10px;
}

.nc-tower-subhead {
	margin: 16px 0 6px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.nc-tower-muted {
	color: var(--color-text-maxcontrast);
	font-size: 0.9em;
}
</style>
