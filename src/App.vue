<template>
	<div id="nc-tower-root">
		<a href="#nc-tower-main" class="tower-skip">Skip to main content</a>

		<nav class="tower-nav" aria-label="Control Tower">
			<div class="tower-nav__brand">
				<span class="tower-nav__mark" aria-hidden="true">◎</span>
				<span class="tower-nav__name">Control Tower</span>
			</div>
			<div class="tower-nav__tabs">
				<a v-for="tab in tabs"
					:key="tab.id"
					class="tower-nav__tab"
					:class="{ 'is-active': tab.id === page }"
					:href="url(tab.route)"
					:aria-current="tab.id === page ? 'page' : null">
					{{ tab.label }}
				</a>
			</div>
		</nav>

		<main id="nc-tower-main" class="tower-main">
			<component :is="view" />
		</main>
	</div>
</template>

<script>
import { generateUrl } from '@nextcloud/router'
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
	components: { Home, Apps, System, Users, Ops, Host, Tools },
	props: {
		page: {
			type: String,
			default: 'home',
		},
	},
	data() {
		return {
			tabs: [
				{ id: 'home', label: 'Home', route: '' },
				{ id: 'ops', label: 'Ops', route: 'ops' },
				{ id: 'host', label: 'Host', route: 'host' },
				{ id: 'apps', label: 'Apps', route: 'apps' },
				{ id: 'system', label: 'System', route: 'system' },
				{ id: 'users', label: 'Users', route: 'user' },
				{ id: 'tools', label: 'Tools', route: 'tools' },
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
	--tower-gap: 12px;
	height: 100%;
	overflow: auto;
	color: var(--color-main-text);
	background: var(--color-main-background);
}

.tower-skip {
	position: absolute;
	inset-inline-start: -9999px;

	&:focus {
		position: static;
		display: inline-block;
		padding: 8px;
	}
}

.tower-nav {
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
		padding: 8px 12px;
		border-radius: var(--border-radius-pill, 999px);
		text-decoration: none;
		color: var(--color-main-text);
		white-space: nowrap;
		min-height: 44px;
		display: inline-flex;
		align-items: center;

		&:hover { background: var(--color-background-hover); }

		&.is-active {
			background: var(--color-primary-element);
			color: var(--color-primary-element-text);
			font-weight: 600;
		}
	}
}

.tower-main {
	padding: 16px;
	max-width: 1400px;
	margin: 0 auto;
}

.tower-view__lead {
	margin: 0 0 var(--tower-gap);
	color: var(--color-text-maxcontrast);
}

.tower-chips {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-bottom: 8px;
}

.tower-chip {
	padding: 3px 10px;
	border-radius: var(--border-radius-pill, 999px);
	background: var(--color-background-dark);
	font-size: 0.85em;
	white-space: nowrap;
}

.tower-actions-cell {
	display: flex;
	justify-content: flex-end;
	gap: 4px;
}

.tower-muted {
	color: var(--color-text-maxcontrast);
	font-size: 0.9em;
}

@media (max-width: 720px) {
	.tower-nav {
		&__brand { width: 100%; }
	}

	.tower-main { padding: 12px 10px 40px; }
}
</style>
