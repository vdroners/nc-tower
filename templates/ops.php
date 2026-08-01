<?php

declare(strict_types=1);

use OCP\Util;

Util::addScript(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-ops');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-ops');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-main');
?>
<?php include __DIR__ . '/partials/subnav.php'; ?>
<div id="nc-tower-ops" class="nc-tower-ops">
	<header class="nc-tower-ops__header">
		<h2>Ops</h2>
		<p class="nc-tower-ops__lead">Host, containers, stacks, and ops inbox (allowlisted actions via sidecar).</p>
		<div id="nc-tower-banner" class="nc-tower-ops__banner" hidden></div>
	</header>

	<section class="nc-tower-card" data-section="host">
		<h3>Host</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="gpu">
		<h3>GPU</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="smart">
		<h3>SMART</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="fan">
		<h3>GPU Fan</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="containers">
		<h3>Containers</h3>
		<div class="nc-tower-card__toolbar">
			<input type="search" id="nc-tower-container-filter" placeholder="Filter name/status…" />
		</div>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="stacks">
		<h3>Stacks</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="backup">
		<h3>Backup summary</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="inbox">
		<h3>Ops inbox</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>

	<dialog id="nc-tower-logs"><pre id="nc-tower-logs-body"></pre><form method="dialog"><button>Close</button></form></dialog>
	<div id="nc-tower-toast" class="nc-tower-toast" hidden></div>
</div>
