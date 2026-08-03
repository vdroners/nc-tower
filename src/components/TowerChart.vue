<template>
	<div class="nc-tower-chart" :style="{ height: `${height}px` }">
		<canvas ref="canvas" :aria-label="title" role="img" />
	</div>
</template>

<script>
import {
	Chart,
	LineController,
	BarController,
	LineElement,
	BarElement,
	PointElement,
	LinearScale,
	CategoryScale,
	TimeScale,
	Tooltip,
	Legend,
	Filler,
} from 'chart.js'
import 'chartjs-adapter-date-fns'

Chart.register(
	LineController, BarController, LineElement, BarElement, PointElement,
	LinearScale, CategoryScale, TimeScale, Tooltip, Legend, Filler,
)

/**
 * Shared chart wrapper, modelled on nc-wireguard's RateChart: chart.js is the
 * estate's charting library, and every instance should read its colours from
 * the Nextcloud theme rather than hardcoding them, so dark mode stays correct.
 */
export default {
	name: 'TowerChart',
	props: {
		type: {
			type: String,
			default: 'line',
		},
		/** chart.js datasets; colours are filled in from the theme if absent. */
		datasets: {
			type: Array,
			default: () => [],
		},
		labels: {
			type: Array,
			default: null,
		},
		height: {
			type: Number,
			default: 180,
		},
		title: {
			type: String,
			default: '',
		},
		yMax: {
			type: Number,
			default: null,
		},
		ySuffix: {
			type: String,
			default: '',
		},
		timeAxis: {
			type: Boolean,
			default: false,
		},
		showLegend: {
			type: Boolean,
			default: false,
		},
	},
	watch: {
		datasets: {
			deep: true,
			handler() {
				this.render()
			},
		},
	},
	mounted() {
		this.render()
	},
	beforeDestroy() {
		if (this.chart) {
			this.chart.destroy()
			this.chart = null
		}
	},
	methods: {
		themeColour(name, fallback) {
			const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
			return value || fallback
		},
		render() {
			const canvas = this.$refs.canvas
			if (!canvas) {
				return
			}
			if (this.chart) {
				this.chart.destroy()
				this.chart = null
			}
			const grid = this.themeColour('--color-border', '#ddd')
			const text = this.themeColour('--color-text-maxcontrast', '#767676')
			const primary = this.themeColour('--color-primary-element', '#0082c9')

			const datasets = this.datasets.map((set, index) => ({
				borderColor: primary,
				backgroundColor: primary,
				borderWidth: 2,
				pointRadius: 0,
				tension: 0.25,
				fill: false,
				...set,
				// A second series with no colour of its own would be invisible
				// against the first; nudge it rather than repeat the primary.
				...(index > 0 && !set.borderColor ? { borderColor: text, backgroundColor: text } : {}),
			}))

			this.chart = new Chart(canvas.getContext('2d'), {
				type: this.type,
				data: { labels: this.labels || undefined, datasets },
				options: {
					responsive: true,
					maintainAspectRatio: false,
					animation: false,
					interaction: { mode: 'index', intersect: false },
					plugins: {
						legend: { display: this.showLegend, labels: { color: text, boxWidth: 10 } },
						tooltip: {
							callbacks: {
								label: (item) => `${item.dataset.label || ''} ${item.formattedValue}${this.ySuffix}`.trim(),
							},
						},
					},
					scales: {
						x: {
							type: this.timeAxis ? 'time' : 'category',
							grid: { color: grid, display: false },
							ticks: { color: text, maxRotation: 0, autoSkipPadding: 24 },
							...(this.timeAxis ? { time: { tooltipFormat: 'PP p' } } : {}),
						},
						y: {
							beginAtZero: true,
							suggestedMax: this.yMax ?? undefined,
							grid: { color: grid },
							ticks: { color: text, callback: (value) => `${value}${this.ySuffix}` },
						},
					},
				},
			})
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-chart {
	position: relative;
	width: 100%;
}
</style>
