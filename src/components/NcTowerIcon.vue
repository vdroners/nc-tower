<template>
	<svg xmlns="http://www.w3.org/2000/svg"
		:width="size"
		:height="size"
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		stroke-linejoin="round"
		class="nc-tower-icon"
		aria-hidden="true"
		focusable="false"
		v-html="path" />
</template>

<script>
/**
 * Tabler-style inline SVG glyphs for NC Tower (stroke, 24 viewBox).
 *
 * Matches the estate convention set by GcsIcon.vue and NcPrintIcon.vue: no icon
 * library anywhere, one registry per app, stroke="currentColor" so icons take
 * the colour of whatever they sit in. NC Tower previously used Unicode
 * glyphs (◎ ▾ ▸ ↻ ▲ ▼), which ignore stroke weight and render differently on
 * every platform font.
 */
const ICONS = {
	// brand
	radar: '<path d="M15.51 15.56a5 5 0 1 0 -3.51 1.44"/><path d="M18.832 17.86a9 9 0 1 0 -6.832 3.14"/><path d="M12 12l6 -3"/>',

	// navigation
	home: '<path d="M5 12l-2 0l9 -9l9 9l-2 0"/><path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-7"/><path d="M9 21v-6a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v6"/>',
	activity: '<path d="M3 12h4l3 8l4 -16l3 8h4"/>',
	server: '<path d="M3 4m0 3a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3z"/><path d="M3 12m0 3a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3z"/><path d="M7 8v.01"/><path d="M7 16v.01"/>',
	grid: '<path d="M4 4h6v6h-6z"/><path d="M14 4h6v6h-6z"/><path d="M4 14h6v6h-6z"/><path d="M14 14h6v6h-6z"/>',
	settings: '<path d="M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 -.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 -2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065z"/><path d="M9 12a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/>',
	users: '<path d="M9 7m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"/><path d="M3 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M21 21v-2a4 4 0 0 0 -3 -3.85"/>',
	toolbox: '<path d="M3 10m0 2a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v6a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2z"/><path d="M8 10v-3a1 1 0 0 1 1 -1h6a1 1 0 0 1 1 1v3"/><path d="M12 15v2"/><path d="M3 14h18"/>',

	// disclosure and sorting
	'chevron-right': '<path d="M9 6l6 6l-6 6"/>',
	'chevron-down': '<path d="M6 9l6 6l6 -6"/>',
	'chevron-up': '<path d="M6 15l6 -6l6 6"/>',

	// actions
	refresh: '<path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4"/>',
	play: '<path d="M7 4v16l13 -8z"/>',
	stop: '<path d="M5 5m0 2a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2z"/>',
	x: '<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>',
	rotate: '<path d="M19.95 11a8 8 0 1 0 -.5 4m.5 5v-5h-5"/>',
	terminal: '<path d="M5 7l5 5l-5 5"/><path d="M12 19h7"/>',
	'file-text': '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2z"/><path d="M9 9l1 0"/><path d="M9 13l6 0"/><path d="M9 17l6 0"/>',
	search: '<path d="M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"/><path d="M21 21l-6 -6"/>',
	'arrow-up': '<path d="M12 5l0 14"/><path d="M18 11l-6 -6"/><path d="M6 11l6 -6"/>',
	'arrow-down': '<path d="M12 5l0 14"/><path d="M18 13l-6 6"/><path d="M6 13l6 6"/>',
	download: '<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"/><path d="M7 11l5 5l5 -5"/><path d="M12 4l0 12"/>',
	hammer: '<path d="M7 10h3v-3l-3.5 -3.5a6 6 0 0 1 8 8l6 6a2 2 0 0 1 -3 3l-6 -6a6 6 0 0 1 -8 -8l3.5 3.5"/>',
	edit: '<path d="M7 7h-1a2 2 0 0 0 -2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2 -2v-1"/><path d="M20.385 6.585a2.1 2.1 0 0 0 -2.97 -2.97l-8.415 8.385v3h3l8.385 -8.415z"/><path d="M16 5l3 3"/>',
	trash: '<path d="M4 7l16 0"/><path d="M10 11l0 6"/><path d="M14 11l0 6"/><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"/><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"/>',
	bell: '<path d="M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6"/><path d="M9 17v1a3 3 0 0 0 6 0v-1"/>',
	plus: '<path d="M12 5l0 14"/><path d="M5 12l14 0"/>',
	copy: '<path d="M8 8m0 2a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-8a2 2 0 0 1 -2 -2z"/><path d="M16 8v-2a2 2 0 0 0 -2 -2h-8a2 2 0 0 0 -2 2v8a2 2 0 0 0 2 2h2"/>',
	'external-link': '<path d="M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6"/><path d="M11 13l9 -9"/><path d="M15 4h5v5"/>',
	'player-play': '<path d="M7 4v16l13 -8z"/>',

	// fallback for an unknown name: a small dot, matching GcsIcon's behaviour
	dot: '<circle cx="12" cy="12" r="1.5"/>',
}

export default {
	name: 'NcTowerIcon',
	props: {
		name: {
			type: String,
			required: true,
		},
		size: {
			type: [Number, String],
			default: 16,
		},
	},
	computed: {
		path() {
			return ICONS[this.name] || ICONS.dot
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-icon {
	flex: 0 0 auto;
	vertical-align: middle;
}
</style>
