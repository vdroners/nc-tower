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
gate('G08', 'info.xml readable', is_readable("$remote/appinfo/info.xml"));

$xml = @file_get_contents("$remote/appinfo/info.xml") ?: '';
gate('G09', 'id nc_tower', str_contains($xml, '<id>nc_tower</id>'));
gate('G09', 'Control Tower name', str_contains($xml, '<name>Control Tower</name>'));

$routes = @file_get_contents("$remote/appinfo/routes.php") ?: '';
gate('G10', 'tower#health route', str_contains($routes, 'tower#health'));
gate('G10', 'tower#tools route', str_contains($routes, 'tower#tools'));
gate('G10', 'enableapp still listed', str_contains($routes, 'enableapp'));

gate('G16', 'CREDITS deployed', is_file("$remote/CREDITS.md"));
$credits = @file_get_contents("$remote/CREDITS.md") ?: '';
gate('G16', 'CREDITS Wolfgang', str_contains($credits, 'Wolfgang'));

// Ownership hint (best-effort)
$owner = posix_getpwuid(@fileowner($remote) ?: 0);
$ownerName = $owner['name'] ?? '';
gate('G08', 'tree owned by www-data (or root after cp before chown)', in_array($ownerName, ['www-data', 'root'], true));

exit($fail);
