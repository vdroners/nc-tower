<?php
/**
 * Control Tower API gates — run inside cloud_app against deployed tree.
 * Usage: php /var/www/html/custom_apps/nc_tower/tools/tower-api-gates.php
 */
declare(strict_types=1);

$remote = getenv('NC_TOWER_REMOTE') ?: '/var/www/html/custom_apps/nc_tower';
$fail = 0;

function gate(string $id, string $msg, bool $ok): void {
	global $fail;
	echo ($ok ? 'PASS' : 'FAIL') . " $id $msg\n";
	if (!$ok) {
		$fail = 1;
	}
}

gate('G00', 'deployed info.xml', is_file("$remote/appinfo/info.xml"));
gate('G00', 'deployed routes.php', is_file("$remote/appinfo/routes.php"));
gate('G00', 'deployed ops.php', is_file("$remote/templates/ops.php"));
gate('G00', 'deployed host.php', is_file("$remote/templates/host.php"));
gate('G00', 'deployed tools.php', is_file("$remote/templates/tools.php"));
gate('G00', 'deployed app bundle', is_file("$remote/js/nc_tower-app.js"));
gate('G00', 'deployed widget bundle', is_file("$remote/js/nc_tower-widget.js"));
gate('G08', 'info.xml readable', is_readable("$remote/appinfo/info.xml"));

$xml = @file_get_contents("$remote/appinfo/info.xml") ?: '';
gate('G09', 'id nc_tower', str_contains($xml, '<id>nc_tower</id>'));
gate('G09', 'Control Tower name', str_contains($xml, '<name>Control Tower</name>'));
gate('G09', 'version 1.8+', (bool) preg_match('/<version>1\.(8|[9]|[1-9]\d)\.\d+<\/version>/', $xml)
	|| (bool) preg_match('/<version>[2-9]\.\d+\.\d+<\/version>/', $xml));

$routes = @file_get_contents("$remote/appinfo/routes.php") ?: '';
foreach ([
	'tower#health', 'tower#tools', 'tower#hostGpu', 'tower#fanSet', 'tower#stackAction',
	'tower#containerExec', 'tower#containerRecreate', 'tower#dockerDf', 'tower#backupRun',
	'tower#systemdRestart', 'page#ops', 'page#host', 'enableapp',
] as $route) {
	gate('G10', "route $route", str_contains($routes, $route));
}

$ctrl = @file_get_contents("$remote/lib/Controller/TowerController.php") ?: '';
gate('G11', 'TowerController does not open docker.sock', !str_contains($ctrl, '/var/run/docker.sock') && !str_contains($ctrl, 'fopen('));
gate('G11', 'no changeme default token', !str_contains($ctrl, "'changeme'"));
gate('G11', 'no host-shell route string', !str_contains($routes, 'host-shell') && !str_contains($routes, 'tower#shell'));
gate('G11', 'no system prune route', !str_contains($routes, 'prune'));

$sidecar = @file_get_contents("$remote/sidecar/app.py") ?: '';
gate('G12', 'sidecar has /containers exec', str_contains($sidecar, '/exec'));
gate('G12', 'sidecar has stacks rebuild', str_contains($sidecar, 'rebuild'));
gate('G12', 'sidecar refuses empty token mutators', str_contains($sidecar, 'token_required') || str_contains($sidecar, '_post_authorized'));
gate('G12', 'sidecar fan uses host python/nsenter', str_contains($sidecar, '_fan_cmd') && str_contains($sidecar, 'HOST_FAN_HELPER'));
gate('G12', 'sidecar no system prune route', !str_contains($sidecar, 'system prune') && !str_contains($sidecar, 'volume prune'));
gate('G12', 'sidecar no host-shell route', !str_contains($sidecar, '/host/shell') && !str_contains($sidecar, 'host-shell'));
// 1.8.2: ps output exceeded the cap and _run kept the tail, discarding the
// header and the top-CPU rows the view exists to show.
gate('G12', 'sidecar ps keeps head on truncation', str_contains($sidecar, 'keep="head"'));
gate('G12', 'sidecar smart hours anchored per line', str_contains($sidecar, 'Power_On_Hours\b[^\n]'));

// --- G19 front end ----------------------------------------------------------
$bundle = "$remote/js/nc_tower-app.js";
gate('G19', 'app bundle is a real build', is_file($bundle) && filesize($bundle) > 200000);
foreach (['index', 'ops', 'host', 'tools', 'apps', 'system', 'user'] as $tpl) {
	$body = @file_get_contents("$remote/templates/$tpl.php") ?: '';
	gate('G19', "template $tpl mounts the bundle",
		str_contains($body, 'nc_tower-app') && str_contains($body, 'id="nc_tower"'));
}
$js = @file_get_contents($bundle) ?: '';
gate('G19', 'bundle talks to tower routes', str_contains($js, '/tower/containers'));
// The sidecar token is host-root equivalent. PHP holds it and proxies; it must
// never be shipped to a browser. (A bare "changeme" substring check is useless
// here — bundled i18n catalogues contain the French "changements".)
gate('G19', 'bundle never sends the sidecar header', !str_contains($js, 'X-Ops-Token'));
// The token file is host-root equivalent; PHP reads the token from config.php,
// so nothing about it belongs in the deployed web-app tree.
gate('G11', 'sidecar/.env not deployed into the web root', !is_file("$remote/sidecar/.env"));

// --- G24 user storage -------------------------------------------------------
// quotaUsedLabel() used to depend on an IUser method that does not exist on
// NC 31-34, so every account displayed a dash while some held hundreds of GB.
$uc = @file_get_contents("$remote/lib/Controller/UserController.php") ?: '';
gate('G24', 'user storage read from the file cache', str_contains($uc, 'storageUsedMap'));
// Match a call, not the word: the fix documents why getQuotaUsage was dropped,
// and a bare substring check would fail on its own explanation.
gate('G24', 'no dependency on absent getQuotaUsage',
	!preg_match('/->\s*getQuotaUsage\s*\(/', $uc)
	&& !preg_match('/method_exists\s*\([^)]*getQuotaUsage/', $uc));
gate('G24', 'raw bytes exposed for sorting', str_contains($uc, 'used_bytes'));

// --- G21 admin gating -------------------------------------------------------
$stray = [];
foreach (glob("$remote/lib/Controller/*.php") ?: [] as $file) {
	foreach (file($file) ?: [] as $n => $line) {
		if (preg_match('/^\s*#\[NoAdminRequired\]/', $line)) {
			$stray[] = basename($file) . ':' . ($n + 1);
		}
	}
}
gate('G21', 'no active NoAdminRequired in any controller' . ($stray ? ' (' . implode(', ', $stray) . ')' : ''), $stray === []);

// --- G22 dead weight --------------------------------------------------------
$dead = [];
foreach (['main', 'apps', 'system', 'user', 'ops'] as $old) {
	if (is_file("$remote/js/nc_tower-$old.js")) {
		$dead[] = "nc_tower-$old.js";
	}
}
gate('G22', 'prebuilt bundles removed from deployed tree' . ($dead ? ' (' . implode(', ', $dead) . ')' : ''), $dead === []);

gate('G16', 'CREDITS deployed', is_file("$remote/CREDITS.md"));
$credits = @file_get_contents("$remote/CREDITS.md") ?: '';
gate('G16', 'CREDITS Wolfgang', str_contains($credits, 'Wolfgang'));

$matrix = @file_get_contents("$remote/docs/CAPABILITY_MATRIX.md") ?: '';
gate('G17', 'matrix mentions allowlisted exec', str_contains($matrix, 'exec'));
gate('G17', 'matrix Portainer section', str_contains($matrix, 'Portainer'));

$widget = @file_get_contents("$remote/lib/Dashboard/NcTowerWidget.php") ?: '';
gate('G18', 'widget title Control Tower', str_contains($widget, 'Control Tower'));

$owner = posix_getpwuid(@fileowner($remote) ?: 0);
$ownerName = $owner['name'] ?? '';
gate('G08', 'tree owned by www-data (or root after cp before chown)', in_array($ownerName, ['www-data', 'root'], true));

exit($fail);
