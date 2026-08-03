import Vue from 'vue'
import App from './App.vue'

Vue.config.productionTip = false

/**
 * Every NC Tower page renders <div id="nc_tower" data-page="…">. The
 * bundle is shared, so which view boots is decided by that attribute.
 */
function boot() {
	const mount = document.getElementById('nc_tower')
	if (!mount) {
		return
	}
	const page = mount.dataset.page || 'home'
	// eslint-disable-next-line no-new
	new Vue({
		el: mount,
		render: (h) => h(App, { props: { page } }),
	})
}

// Scripts normally arrive deferred, i.e. before DOMContentLoaded — but one that
// lands after it would never fire the listener, leaving a blank page.
if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', boot)
} else {
	boot()
}
