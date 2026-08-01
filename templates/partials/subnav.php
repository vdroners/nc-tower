<?php

declare(strict_types=1);

use OCP\Util;

$appId = OCA\NcTower\AppInfo\Application::APP_ID;
$base = \OC::$server->getURLGenerator()->linkToRoute($appId . '.page.index');
$base = rtrim(preg_replace('#/$#', '', $base), '/');
// index route is /apps/nc_tower/ — sibling pages are under same app
$u = static function (string $path) use ($appId): string {
	return \OC::$server->getURLGenerator()->linkToRoute($appId . '.page.' . $path);
};
$current = $_SERVER['REQUEST_URI'] ?? '';
$items = [
	['id' => 'index', 'label' => 'Home', 'route' => 'index'],
	['id' => 'apps', 'label' => 'Apps', 'route' => 'apps'],
	['id' => 'system', 'label' => 'System', 'route' => 'system'],
	['id' => 'user', 'label' => 'Users', 'route' => 'user'],
	['id' => 'ops', 'label' => 'Ops', 'route' => 'ops'],
	['id' => 'host', 'label' => 'Host', 'route' => 'host'],
	['id' => 'tools', 'label' => 'Tools', 'route' => 'tools'],
];
?>
<nav class="nc-tower-subnav" aria-label="Control Tower">
	<?php foreach ($items as $item):
		$href = $u($item['route']);
		$active = str_contains($current, '/nc_tower/' . $item['id'])
			|| ($item['id'] === 'index' && preg_match('#/nc_tower/?(\?|$)#', $current));
		?>
		<a class="nc-tower-subnav__link<?= $active ? ' is-active' : '' ?>" href="<?= htmlspecialchars($href, ENT_QUOTES, 'UTF-8') ?>">
			<?= htmlspecialchars($item['label'], ENT_QUOTES, 'UTF-8') ?>
		</a>
	<?php endforeach; ?>
</nav>
