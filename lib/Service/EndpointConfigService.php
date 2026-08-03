<?php

declare(strict_types=1);

namespace OCA\NcTower\Service;

use OCA\NcTower\AppInfo\Application;
use OCP\IConfig;

/**
 * Admin-configurable deep links + sidecar base URL.
 *
 * Tool URL defaults are empty so a stock App Store install shows no lab tiles
 * until an admin fills them in Settings → Control Tower.
 */
class EndpointConfigService {
	public const KEY_SIDECAR_URL = 'sidecar_url';
	public const DEFAULT_SIDECAR_URL = 'http://nc_tower_sidecar:18765';

	/** @var list<array{key:string,title:string,group:string,path?:string}> */
	public const TOOL_DEFS = [
		['key' => 'url_portainer', 'title' => 'Portainer', 'group' => 'orchestration'],
		['key' => 'url_webmin', 'title' => 'Webmin', 'group' => 'orchestration'],
		['key' => 'url_webmin_system_health', 'title' => 'System Health', 'group' => 'host', 'path' => '/system-health/'],
		['key' => 'url_webmin_docker', 'title' => 'Docker', 'group' => 'host', 'path' => '/docker/'],
		['key' => 'url_webmin_docker_stacks', 'title' => 'Docker Stacks', 'group' => 'host', 'path' => '/docker-stacks/'],
		['key' => 'url_webmin_nvidia', 'title' => 'NVIDIA GPU', 'group' => 'host', 'path' => '/nvidia-gpu/'],
		['key' => 'url_webmin_smart', 'title' => 'SMART Health', 'group' => 'host', 'path' => '/smart-health/'],
		['key' => 'url_webmin_backup', 'title' => 'Backup Mgr', 'group' => 'host', 'path' => '/backup-mgr/'],
		['key' => 'url_webmin_fan', 'title' => 'Fan Control (chassis PWM)', 'group' => 'host', 'path' => '/fan-control/'],
		['key' => 'url_kuma', 'title' => 'Uptime Kuma', 'group' => 'apps'],
		['key' => 'url_caddy', 'title' => 'Caddy Proxy', 'group' => 'apps'],
		['key' => 'url_guacamole', 'title' => 'Guacamole', 'group' => 'apps'],
		['key' => 'url_webodm', 'title' => 'WebODM', 'group' => 'apps'],
		['key' => 'url_orcaslicer', 'title' => 'OrcaSlicer', 'group' => 'apps'],
		['key' => 'url_adsb', 'title' => 'ADSB Feeder', 'group' => 'apps'],
		['key' => 'url_mediamtx', 'title' => 'MediaMTX', 'group' => 'apps'],
		['key' => 'url_nextcloud', 'title' => 'Nextcloud', 'group' => 'apps'],
	];

	public function __construct(
		private IConfig $config,
	) {
	}

	public function getSidecarUrl(): string {
		$fromApp = trim($this->config->getAppValue(Application::APP_ID, self::KEY_SIDECAR_URL, ''));
		if ($fromApp !== '') {
			return rtrim($fromApp, '/');
		}
		// Lab installs historically used config.php system value.
		$fromSystem = trim($this->config->getSystemValueString('nc_tower_sidecar_url', ''));
		if ($fromSystem !== '') {
			return rtrim($fromSystem, '/');
		}
		return rtrim(self::DEFAULT_SIDECAR_URL, '/');
	}

	public function getToolUrl(string $key): string {
		return trim($this->config->getAppValue(Application::APP_ID, $key, ''));
	}

	/**
	 * Resolve a tool URL: explicit appconfig wins; Webmin child pages may
	 * derive from url_webmin + path when the child key is empty.
	 */
	public function resolveToolUrl(array $def): string {
		$explicit = $this->getToolUrl($def['key']);
		if ($explicit !== '') {
			return rtrim($explicit, '/');
		}
		$path = $def['path'] ?? '';
		if ($path !== '' && ($def['group'] ?? '') === 'host') {
			$base = $this->getToolUrl('url_webmin');
			if ($base !== '') {
				return rtrim($base, '/') . $path;
			}
		}
		return '';
	}

	/**
	 * @return array{groups: list<array{title:string,tools:list<array{title:string,url:string,note?:string}>}>, tools: list<array{title:string,url:string}>}
	 */
	public function buildToolsPayload(): array {
		$byGroup = [
			'orchestration' => [],
			'host' => [],
			'apps' => [],
		];
		$flat = [];

		foreach (self::TOOL_DEFS as $def) {
			$url = $this->resolveToolUrl($def);
			if ($url === '') {
				continue;
			}
			$item = ['title' => $def['title'], 'url' => $url];
			$byGroup[$def['group']][] = $item;
			if (in_array($def['group'], ['orchestration', 'apps'], true)
				|| in_array($def['key'], ['url_portainer', 'url_webmin'], true)) {
				$flat[] = $item;
			}
		}

		// Flat list: orchestration + apps only (legacy Tools consumer shape).
		$flat = [];
		foreach (array_merge($byGroup['orchestration'], $byGroup['apps']) as $item) {
			$flat[] = $item;
		}

		$groups = [];
		if ($byGroup['orchestration'] !== []) {
			$groups[] = ['title' => 'Orchestration', 'tools' => $byGroup['orchestration']];
		}
		if ($byGroup['host'] !== []) {
			$groups[] = ['title' => 'Host (Webmin break-glass)', 'tools' => $byGroup['host']];
		}
		if ($byGroup['apps'] !== []) {
			$groups[] = ['title' => 'Apps', 'tools' => $byGroup['apps']];
		}
		$groups[] = [
			'title' => 'VPN',
			'tools' => [[
				'title' => 'WireGuard',
				'url' => '',
				'note' => 'Use the Nextcloud WireGuard app (not managed in Control Tower).',
			]],
		];

		return [
			'groups' => $groups,
			'tools' => $flat,
		];
	}

	/** @return array<string,string> */
	public function allSettings(): array {
		$out = [self::KEY_SIDECAR_URL => $this->config->getAppValue(
			Application::APP_ID,
			self::KEY_SIDECAR_URL,
			self::DEFAULT_SIDECAR_URL,
		)];
		foreach (self::TOOL_DEFS as $def) {
			$out[$def['key']] = $this->getToolUrl($def['key']);
		}
		return $out;
	}

	/** @param array<string,mixed> $params */
	public function saveFromRequest(array $params): void {
		if (array_key_exists(self::KEY_SIDECAR_URL, $params)) {
			$url = trim((string)$params[self::KEY_SIDECAR_URL]);
			if ($url === '') {
				$url = self::DEFAULT_SIDECAR_URL;
			}
			$this->config->setAppValue(Application::APP_ID, self::KEY_SIDECAR_URL, $url);
		}
		foreach (self::TOOL_DEFS as $def) {
			$key = $def['key'];
			if (array_key_exists($key, $params)) {
				$this->config->setAppValue(
					Application::APP_ID,
					$key,
					trim((string)$params[$key]),
				);
			}
		}
	}
}
