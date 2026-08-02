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
	window.OCA.Dashboard.register('nc_tower', (element) => {
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
