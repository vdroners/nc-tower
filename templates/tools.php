<?php

declare(strict_types=1);

use OCP\Util;

Util::addScript(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-ops');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-ops');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-main');
?>
<?php include __DIR__ . '/partials/subnav.php'; ?>
<div id="nc-tower-tools" class="nc-tower-ops" data-page="tools">
	<header class="nc-tower-ops__header">
		<h2>Tools</h2>
		<p class="nc-tower-ops__lead">Break-glass deep links. WireGuard is managed in the Nextcloud WireGuard app.</p>
	</header>
	<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
</div>
