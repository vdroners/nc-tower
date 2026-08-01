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
gate('G00', 'deployed nc_tower-ops.js', is_file("$remote/js/nc_tower-ops.js"));
gate('G08', 'info.xml readable', is_readable("$remote/appinfo/info.xml"));

$xml = @file_get_contents("$remote/appinfo/info.xml") ?: '';
gate('G09', 'id nc_tower', str_contains($xml, '<id>nc_tower</id>'));
gate('G09', 'Control Tower name', str_contains($xml, '<name>Control Tower</name>'));
gate('G09', 'version 1.8+', (bool) preg_match('/<version>1\.(8|[9]|[1-9]\d)\.\d+<\/version>/', $xml)
	|| (bool) preg_match('/<version>[2-9]\.\d+\.\d+<\/version>/', $xml));

$routes = @file_get_contents("$remote/appinfo/routes.php") ?: '';
gate('G10', 'tower#health route', str_contains($routes, 'tower#health'));
gate('G10', 'tower#tools route', str_contains($routes, 'tower#tools'));
gate('G10', 'tower#hostGpu route', str_contains($routes, 'tower#hostGpu'));
gate('G10', 'tower#fanSet route', str_contains($routes, 'tower#fanSet'));
gate('G10', 'tower#stackAction route', str_contains($routes, 'tower#stackAction'));
gate('G10', 'tower#containerExec route', str_contains($routes, 'tower#containerExec'));
gate('G10', 'tower#containerRecreate route', str_contains($routes, 'tower#containerRecreate'));
gate('G10', 'tower#dockerDf route', str_contains($routes, 'tower#dockerDf'));
gate('G10', 'tower#backupRun route', str_contains($routes, 'tower#backupRun'));
gate('G10', 'tower#systemdRestart route', str_contains($routes, 'tower#systemdRestart'));
gate('G10', 'page#ops route', str_contains($routes, 'page#ops'));
gate('G10', 'page#host route', str_contains($routes, 'page#host'));
gate('G10', 'enableapp still listed', str_contains($routes, 'enableapp'));

$ctrl = @file_get_contents("$remote/lib/Controller/TowerController.php") ?: '';
gate('G11', 'TowerController does not open docker.sock', !str_contains($ctrl, '/var/run/docker.sock') && !str_contains($ctrl, 'fopen('));
gate('G11', 'no changeme default token', !str_contains($ctrl, "'changeme'"));
gate('G11', 'no host-shell route string', !str_contains($routes, 'host-shell') && !str_contains($routes, 'tower#shell'));
gate('G11', 'no system prune route', !str_contains($routes, 'prune'));

$sidecar = @file_get_contents("$remote/sidecar/app.py") ?: '';
gate('G12', 'sidecar has /containers exec', str_contains($sidecar, '/exec'));
gate('G12', 'sidecar has stacks rebuild', str_contains($sidecar, 'rebuild'));
gate('G12', 'sidecar refuses empty token mutators', str_contains($sidecar, 'token_required') || str_contains($sidecar, '_post_authorized'));

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
