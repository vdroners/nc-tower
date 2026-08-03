<?php
/**
 * NC Tower route-resolution gates (G25).
 *
 * Run inside cloud_app as www-data:
 *   docker exec -u www-data cloud_app php \
 *     /var/www/html/custom_apps/nc_tower/tools/tower-route-gates.php
 *
 * Grepping routes.php cannot catch route shadowing. Routes resolve in
 * declaration order, so `/tower/containers/{name}/{action}` declared ahead of
 * `/exec` and `/recreate` silently swallowed both and handed them to
 * containerAction(), which 400s on any action outside its allowlist. Exec and
 * Recreate were dead that way while every file and route gate passed. The only
 * check that catches it is asking the real router what a URL resolves to.
 */
declare(strict_types=1);

if (!defined('OC_CONSOLE')) {
	define('OC_CONSOLE', 1);
}
require_once '/var/www/html/lib/base.php';

$fail = 0;

function gate(string $id, string $msg, bool $ok): void {
	global $fail;
	echo ($ok ? 'PASS' : 'FAIL') . " $id $msg\n";
	if (!$ok) {
		$fail = 1;
	}
}

try {
	\OC_App::loadApp('nc_tower');
	$router = \OCP\Server::get(\OCP\Route\IRouter::class);
	$router->loadRoutes('nc_tower');
	$collection = $router->getRouteCollection();
} catch (\Throwable $e) {
	echo 'SKIP G25 could not load the route collection: ' . $e->getMessage() . "\n";
	exit(0);
}

/**
 * @param string $method HTTP verb
 * @param string $url absolute app URL
 * @return array{route:string,action:string}|null resolution, or null for 404
 */
function resolve(string $method, string $url): ?array {
	global $collection;
	$context = new \Symfony\Component\Routing\RequestContext('', $method);
	$matcher = new \Symfony\Component\Routing\Matcher\UrlMatcher($collection, $context);
	try {
		$match = $matcher->match($url);
	} catch (\Throwable $e) {
		return null;
	}
	return ['route' => $match['_route'], 'action' => $match['action'] ?? ''];
}

$base = '/apps/nc_tower/tower';

// Each specific mutator must reach its own handler, not the generic one.
foreach ([
	'exec' => 'nc_tower.tower.containerexec',
	'recreate' => 'nc_tower.tower.containerrecreate',
] as $verb => $expected) {
	$hit = resolve('POST', "$base/containers/gcs_probe/$verb");
	gate('G25', "container $verb reaches its own handler"
		. ($hit ? " (got {$hit['route']})" : ' (got 404)'), $hit && $hit['route'] === $expected);
}

// The four allowlisted lifecycle actions still route to containerAction.
foreach (['start', 'stop', 'restart', 'kill'] as $verb) {
	$hit = resolve('POST', "$base/containers/gcs_probe/$verb");
	gate('G25', "container $verb reaches containerAction",
		$hit && $hit['route'] === 'nc_tower.tower.containeraction' && $hit['action'] === $verb);
}

// Anything outside the allowlist must die at the router, not in the controller.
gate('G25', 'unknown container action is refused by the router',
	resolve('POST', "$base/containers/gcs_probe/destroy") === null);

// Stacks: same shape.
foreach (['up', 'down', 'restart', 'pull', 'rebuild'] as $verb) {
	$hit = resolve('POST', "$base/stacks/$verb");
	gate('G25', "stack $verb reaches stackAction",
		$hit && $hit['route'] === 'nc_tower.tower.stackaction' && $hit['action'] === $verb);
}
gate('G25', 'unknown stack action is refused by the router',
	resolve('POST', "$base/stacks/destroy") === null);

// Jobs: the GET and POST forms share a URL shape and must not collide.
$hit = resolve('GET', "$base/jobs/20260803-151145-apt-dry-run-663b0f");
gate('G25', 'job read resolves to tower#job', $hit && $hit['route'] === 'nc_tower.tower.job');
$hit = resolve('POST', "$base/jobs/apt-upgrade");
gate('G25', 'job start resolves to tower#jobstart', $hit && $hit['route'] === 'nc_tower.tower.jobstart');
gate('G25', 'unknown job kind is refused by the router',
	resolve('POST', "$base/jobs/rm-rf") === null);

// Read paths must not be shadowed either.
foreach (['logs' => 'nc_tower.tower.containerlogs', 'inspect' => 'nc_tower.tower.containerinspect'] as $verb => $expected) {
	$hit = resolve('GET', "$base/containers/gcs_probe/$verb");
	gate('G25', "container $verb resolves", $hit && $hit['route'] === $expected);
}

exit($fail);
