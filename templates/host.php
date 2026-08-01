<?php

declare(strict_types=1);

use OCP\Util;

Util::addScript(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-ops');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-ops');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-main');
?>
<?php include __DIR__ . '/partials/subnav.php'; ?>
<div id="nc-tower-host" class="nc-tower-ops">
	<header class="nc-tower-ops__header">
		<h2>Host</h2>
		<p class="nc-tower-ops__lead">Hybrid host glance — mounts, packages, processes, systemd (allowlisted restart), cron RO, network.</p>
		<div id="nc-tower-banner" class="nc-tower-ops__banner" hidden></div>
	</header>

	<section class="nc-tower-card" data-section="host-mounts">
		<h3>Mounts</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="host-packages">
		<h3>Package updates</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="host-proc">
		<h3>Top processes</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="host-systemd">
		<h3>Services</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="host-cron">
		<h3>Cron (RO)</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="host-net">
		<h3>Network glance</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>

	<div id="nc-tower-toast" class="nc-tower-toast" hidden></div>
</div>
