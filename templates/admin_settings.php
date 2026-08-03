<?php
/** @var array $_ */
$saveUrl = htmlspecialchars((string)($_['save_url'] ?? ''), ENT_QUOTES, 'UTF-8');
$sidecarUrl = htmlspecialchars((string)($_['sidecar_url'] ?? ''), ENT_QUOTES, 'UTF-8');
/** @var list<array{key:string,title:string,group:string,value:string}> $toolDefs */
$toolDefs = $_['tool_defs'] ?? [];
?>
<div id="nc-tower-admin-settings" class="section" data-save-url="<?php echo $saveUrl; ?>">
	<h2>NC Tower</h2>
	<p class="settings-hint">
		Configure the optional host sidecar URL and deep-link tiles for external consoles.
		Leave tool URLs empty to hide those tiles. Defaults ship empty so a stock install
		does not assume a lab IP. Sidecar default uses Docker DNS
		<code>http://nc_tower_sidecar:18765</code>.
	</p>
	<p class="settings-hint">
		<strong>Privacy:</strong> the sidecar is an optional privileged host agent.
		It is not required for Nextcloud Apps enable/disable. See
		<a href="https://github.com/vdroners/nc-tower/blob/main/docs/PRIVACY.md" target="_blank" rel="noreferrer noopener">docs/PRIVACY.md</a>.
	</p>

	<form id="nc-tower-admin-form" class="nc-tower-admin-form">
		<label>
			<span>Sidecar base URL</span>
			<input type="url" name="sidecar_url" value="<?php echo $sidecarUrl; ?>" placeholder="http://nc_tower_sidecar:18765">
		</label>

		<h3>Tool deep links</h3>
		<p class="settings-hint">Empty = hidden in Services / Tools. Webmin child pages inherit from Webmin when their own URL is blank.</p>
		<?php foreach ($toolDefs as $def): ?>
			<label>
				<span><?php echo htmlspecialchars($def['title'] . ' (' . $def['group'] . ')', ENT_QUOTES, 'UTF-8'); ?></span>
				<input type="url"
					name="<?php echo htmlspecialchars($def['key'], ENT_QUOTES, 'UTF-8'); ?>"
					value="<?php echo htmlspecialchars((string)$def['value'], ENT_QUOTES, 'UTF-8'); ?>"
					placeholder="https://…">
			</label>
		<?php endforeach; ?>

		<button type="submit" class="primary">Save</button>
		<p id="nc-tower-admin-status" class="settings-hint" aria-live="polite"></p>
	</form>
</div>
<style>
.nc-tower-admin-form label { display: block; margin: 0.75rem 0; }
.nc-tower-admin-form label span { display: block; font-weight: 600; margin-bottom: 0.25rem; }
.nc-tower-admin-form input[type="url"] { width: 100%; max-width: 36rem; }
</style>
<script>
(function () {
	var root = document.getElementById('nc-tower-admin-settings');
	var form = document.getElementById('nc-tower-admin-form');
	var status = document.getElementById('nc-tower-admin-status');
	if (!root || !form) { return; }
	form.addEventListener('submit', function (ev) {
		ev.preventDefault();
		var url = root.getAttribute('data-save-url');
		var data = {};
		new FormData(form).forEach(function (value, key) { data[key] = value; });
		status.textContent = 'Saving…';
		fetch(url, {
			method: 'PUT',
			headers: {
				'Content-Type': 'application/json',
				'requesttoken': (typeof OC !== 'undefined' && OC.requestToken) ? OC.requestToken : ''
			},
			body: JSON.stringify(data),
			credentials: 'same-origin'
		}).then(function (res) {
			if (!res.ok) { throw new Error('HTTP ' + res.status); }
			return res.json();
		}).then(function () {
			status.textContent = 'Saved.';
		}).catch(function (err) {
			status.textContent = 'Save failed: ' + (err && err.message ? err.message : err);
		});
	});
})();
</script>
