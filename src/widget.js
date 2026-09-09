import Vue from 'vue'
import Widget from './views/Widget.vue'

Vue.config.productionTip = false

/**
 * Dashboard widget entry. Nextcloud calls the registered callback with the
 * element it wants the widget rendered into.
 */
function register() {
	if (!window.OCA?.Dashboard?.register) {
		return
	}
	// Must match the backend widget id (NcTowerWidget::getId() -> 'nc_tower-widget').
	// A mismatch leaves this callback registered under an id with no server-side
	// panel, which crashes Nextcloud core's rerenderPanels (reads panels[id].id)
	// and aborts the whole widget-mount loop — taking down every other app's
	// dashboard widget too.
	window.OCA.Dashboard.register('nc_tower-widget', (element) => {
		const mount = document.createElement('div')
		element.appendChild(mount)
		// eslint-disable-next-line no-new
		new Vue({ el: mount, render: (h) => h(Widget) })
	})
}

if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', register)
} else {
	register()
}
