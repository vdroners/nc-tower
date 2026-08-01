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
		<p class="nc-tower-ops__lead">Host, Docker day-ops, stacks, and ops inbox (allowlisted actions via sidecar).</p>
		<div id="nc-tower-banner" class="nc-tower-ops__banner" hidden></div>
	</header>

	<section class="nc-tower-card" data-section="host">
		<h3>Host summary</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="docker-engine">
		<h3>Docker engine</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="gpu">
		<h3>GPU</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="smart">
		<h3>SMART / NAS</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="fan">
		<h3>GPU Fan</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="chassis-fan">
		<h3>Chassis fans (RO)</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="containers">
		<h3>Containers</h3>
		<div class="nc-tower-card__toolbar">
			<input type="search" id="nc-tower-container-filter" placeholder="Filter name/status/project…" />
		</div>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="stacks">
		<h3>Stacks</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="images">
		<h3>Images</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="volumes">
		<h3>Volumes</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="networks">
		<h3>Networks</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="events">
		<h3>Docker events</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="backup">
		<h3>Backup</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>
	<section class="nc-tower-card" data-section="inbox">
		<h3>Ops inbox / CRITICAL</h3>
		<div class="nc-tower-card__body"><span class="nc-tower-spinner">Loading…</span></div>
	</section>

	<dialog id="nc-tower-logs">
		<form method="dialog" class="nc-tower-dialog-bar">
			<label><input type="checkbox" id="nc-tower-logs-follow" /> Follow (2s poll)</label>
			<button value="close">Close</button>
		</form>
		<pre id="nc-tower-logs-body"></pre>
	</dialog>
	<dialog id="nc-tower-exec">
		<form id="nc-tower-exec-form">
			<p>Exec in <strong id="nc-tower-exec-name"></strong> (argv JSON array)</p>
			<textarea id="nc-tower-exec-cmd" rows="3">["ls","-la"]</textarea>
			<button type="submit">Run</button>
			<button type="button" id="nc-tower-exec-close">Close</button>
		</form>
		<pre id="nc-tower-exec-out"></pre>
	</dialog>
	<dialog id="nc-tower-inspect"><pre id="nc-tower-inspect-body"></pre><form method="dialog"><button>Close</button></form></dialog>
	<div id="nc-tower-toast" class="nc-tower-toast" hidden></div>
</div>
