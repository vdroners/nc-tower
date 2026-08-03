<template>
	<div id="nc-tower-root">
		<a href="#nc-tower-main" class="nc-tower-skip">Skip to main content</a>

		<nav class="nc-tower-nav" aria-label="Control Tower">
			<div class="nc-tower-nav__brand">
				<NcTowerIcon name="radar" :size="22" class="nc-tower-nav__mark" />
				<span class="nc-tower-nav__name">Control Tower</span>
			</div>
			<div class="nc-tower-nav__tabs">
				<a v-for="tab in tabs"
					:key="tab.id"
					class="nc-tower-nav__tab"
					:class="{ 'is-active': tab.id === page }"
					:href="url(tab.route)"
					:aria-current="tab.id === page ? 'page' : null">
					<NcTowerIcon :name="tab.icon" :size="16" class="nc-tower-nav__tab-icon" />
					<span class="nc-tower-nav__tab-label">{{ tab.label }}</span>
				</a>
			</div>
		</nav>

		<main id="nc-tower-main" class="nc-tower-main">
			<component :is="view" />
		</main>
	</div>
</template>

<script>
import { generateUrl } from '@nextcloud/router'
import NcTowerIcon from './components/NcTowerIcon.vue'
import Apps from './views/Apps.vue'
import Home from './views/Home.vue'
import Host from './views/Host.vue'
import Ops from './views/Ops.vue'
import System from './views/System.vue'
import Tools from './views/Tools.vue'
import Users from './views/Users.vue'

const VIEWS = { home: Home, apps: Apps, system: System, users: Users, ops: Ops, host: Host, tools: Tools }

/**
 * Seven server-rendered routes each mount this one bundle and pass their
 * identity through data-page. Nav items stay plain anchors: deep links and
 * hard refresh keep working with no router and no catch-all route, and the
 * bundle is cached across tabs.
 */
export default {
	name: 'App',
	components: { Home, Apps, System, Users, Ops, Host, Tools, NcTowerIcon },
	props: {
		page: {
			type: String,
			default: 'home',
		},
	},
	data() {
		return {
			tabs: [
				{ id: 'home', label: 'Home', route: '', icon: 'home' },
				{ id: 'ops', label: 'Ops', route: 'ops', icon: 'activity' },
				{ id: 'host', label: 'Host', route: 'host', icon: 'server' },
				{ id: 'apps', label: 'Apps', route: 'apps', icon: 'grid' },
				{ id: 'system', label: 'System', route: 'system', icon: 'settings' },
				{ id: 'users', label: 'Users', route: 'user', icon: 'users' },
				{ id: 'tools', label: 'Tools', route: 'tools', icon: 'toolbox' },
			],
		}
	},
	computed: {
		view() {
			return VIEWS[this.page] || Home
		},
	},
	methods: {
		url(route) {
			return generateUrl(`/apps/nc_tower/${route}`)
		},
	},
}
</script>

<style lang="scss">
#nc-tower-root {
	--nc-tower-gap: 12px;
	height: 100%;
	overflow: auto;
	color: var(--color-main-text);
	background: var(--color-main-background);
}

.nc-tower-skip {
	position: absolute;
	inset-inline-start: -9999px;

	&:focus {
		position: static;
		display: inline-block;
		padding: 8px;
	}
}

.nc-tower-nav {
	display: flex;
	align-items: center;
	gap: 16px;
	flex-wrap: wrap;
	padding: 10px 16px;
	border-bottom: 1px solid var(--color-border);
	position: sticky;
	top: 0;
	z-index: 10;
	background: var(--color-main-background);

	&__brand {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 700;
	}

	&__mark {
		color: var(--color-primary-element);
		font-size: 1.2em;
	}

	&__tabs {
		display: flex;
		gap: 4px;
		overflow-x: auto;
		flex: 1 1 auto;
	}

	&__tab {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		padding: 8px 12px;
		border-radius: var(--border-radius-pill, 999px);
		text-decoration: none;
		color: var(--color-main-text);
		white-space: nowrap;
		min-height: 44px;

		&:hover { background: var(--color-background-hover); }

		&.is-active {
			background: var(--color-primary-element);
			color: var(--color-primary-element-text);
			font-weight: 600;
		}
	}
}

.nc-tower-main {
	padding: 16px;
	max-width: 1400px;
	margin: 0 auto;
}

.nc-tower-view__lead {
	margin: 0 0 var(--nc-tower-gap);
	color: var(--color-text-maxcontrast);
}

.nc-tower-chips {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-bottom: 8px;
}

.nc-tower-chip {
	padding: 3px 10px;
	border-radius: var(--border-radius-pill, 999px);
	background: var(--color-background-dark);
	font-size: 0.85em;
	white-space: nowrap;
}

.nc-tower-actions-cell {
	display: flex;
	justify-content: flex-end;
	gap: 4px;
}

.nc-tower-muted {
	color: var(--color-text-maxcontrast);
	font-size: 0.9em;
}

@media (max-width: 720px) {
	.nc-tower-nav {
		&__brand { width: 100%; }
	}

	.nc-tower-main { padding: 12px 10px 40px; }
}
</style>
