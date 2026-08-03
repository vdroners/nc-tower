<template>
	<canvas ref="canvas" class="nc-tower-sparkline" :style="{ height: `${height}px` }" :aria-label="label" role="img" />
</template>

<script>
/**
 * Tiny inline trend, drawn on canvas with no charting library — the same
 * approach as nc-print's TemperatureSparkline. A table with 46 container rows
 * cannot afford a chart.js instance per row, and a sparkline has no axes,
 * legend or interaction to justify one.
 */
export default {
	name: 'Sparkline',
	props: {
		/** Plain numbers, oldest first. */
		samples: {
			type: Array,
			default: () => [],
		},
		height: {
			type: Number,
			default: 22,
		},
		label: {
			type: String,
			default: '',
		},
		/** Fixed upper bound; omit to scale to the data. */
		max: {
			type: Number,
			default: null,
		},
	},
	watch: {
		samples: {
			deep: true,
			handler() {
				this.$nextTick(this.draw)
			},
		},
	},
	mounted() {
		this.draw()
		// Redraw on resize: the canvas is sized from its rendered width.
		this.onResize = () => this.draw()
		window.addEventListener('resize', this.onResize)
	},
	beforeDestroy() {
		window.removeEventListener('resize', this.onResize)
	},
	methods: {
		draw() {
			const canvas = this.$refs.canvas
			if (!canvas) {
				return
			}
			const ctx = canvas.getContext('2d')
			if (!ctx) {
				return
			}
			const dpr = window.devicePixelRatio || 1
			const width = canvas.clientWidth || 120
			const height = this.height
			canvas.width = Math.floor(width * dpr)
			canvas.height = Math.floor(height * dpr)
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
			ctx.clearRect(0, 0, width, height)

			const values = (this.samples || []).map(Number).filter((n) => Number.isFinite(n))
			if (values.length < 2) {
				return
			}
			const top = this.max != null ? this.max : Math.max(...values, 0.0001)
			const style = getComputedStyle(canvas)
			const stroke = style.getPropertyValue('--nc-tower-spark-colour').trim()
				|| style.color || '#0082c9'

			const x = (i) => (i / (values.length - 1)) * (width - 2) + 1
			const y = (v) => height - 1 - (Math.min(v, top) / top) * (height - 2)

			// Fill first so the line sits on top of it.
			ctx.beginPath()
			ctx.moveTo(x(0), height)
			values.forEach((v, i) => ctx.lineTo(x(i), y(v)))
			ctx.lineTo(x(values.length - 1), height)
			ctx.closePath()
			ctx.fillStyle = stroke
			ctx.globalAlpha = 0.15
			ctx.fill()

			ctx.globalAlpha = 1
			ctx.beginPath()
			values.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))))
			ctx.strokeStyle = stroke
			ctx.lineWidth = 1.5
			ctx.lineJoin = 'round'
			ctx.stroke()
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-sparkline {
	width: 100%;
	min-width: 70px;
	display: block;
	color: var(--color-primary-element);
}
</style>
