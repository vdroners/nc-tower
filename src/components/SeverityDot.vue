<template>
	<span class="nc-tower-dot" :class="`nc-tower-dot--${level}`" :title="label" role="img" :aria-label="label" />
</template>

<script>
export default {
	name: 'SeverityDot',
	props: {
		level: {
			type: String,
			default: 'ok',
			validator: (value) => ['ok', 'warn', 'crit', 'idle'].includes(value),
		},
	},
	computed: {
		label() {
			return { ok: 'OK', warn: 'Needs attention', crit: 'Critical', idle: 'Unknown' }[this.level]
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-dot {
	display: inline-block;
	width: 10px;
	height: 10px;
	border-radius: 50%;
	flex: 0 0 auto;
	background: var(--color-text-maxcontrast);

	&--ok { background: var(--color-success); }
	&--warn { background: var(--color-warning); }
	&--crit { background: var(--color-error); }
}
</style>
