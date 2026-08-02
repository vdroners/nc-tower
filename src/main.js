import Vue from 'vue'
import App from './App.vue'

Vue.config.productionTip = false

/**
 * Every Control Tower page renders <div id="nc_tower" data-page="…">. The
 * bundle is shared, so which view boots is decided by that attribute.
 */
document.addEventListener('DOMContentLoaded', () => {
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
})
