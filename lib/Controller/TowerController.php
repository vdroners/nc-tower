<?php

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\DataResponse;
use OCP\IConfig;
use OCP\IRequest;
use Psr\Log\LoggerInterface;

/**
 * Proxies read-only metrics from the Control Tower sidecar.
 * Never talks to docker.sock directly from PHP.
 */
class TowerController extends Controller {
	public function __construct(
		string $appName,
		IRequest $request,
		private IConfig $config,
		private LoggerInterface $logger,
	) {
		parent::__construct($appName, $request);
	}

	private function sidecarBase(): string {
		return rtrim($this->config->getSystemValueString(
			'nc_tower_sidecar_url',
			'http://nc_tower_sidecar:18765'
		), '/');
	}

	private function sidecarToken(): string {
		return $this->config->getSystemValueString('nc_tower_sidecar_token', 'changeme');
	}

	private function getJson(string $path): DataResponse {
		$url = $this->sidecarBase() . $path;
		$token = $this->sidecarToken();
		$headers = ['Accept: application/json'];
		if ($token !== '') {
			$headers[] = 'X-Ops-Token: ' . $token;
		}

		$ch = curl_init($url);
		if ($ch === false) {
			return new DataResponse(['error' => 'curl_init failed'], 502);
		}
		curl_setopt_array($ch, [
			CURLOPT_RETURNTRANSFER => true,
			CURLOPT_TIMEOUT => 5,
			CURLOPT_HTTPHEADER => $headers,
		]);
		$body = curl_exec($ch);
		$code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
		$err = curl_error($ch);
		curl_close($ch);

		if ($body === false || $code < 200 || $code >= 300) {
			$this->logger->warning('Control Tower sidecar error', [
				'url' => $url,
				'http' => $code,
				'err' => $err,
			]);
			return new DataResponse([
				'error' => 'sidecar_unavailable',
				'http' => $code,
				'detail' => $err !== '' ? $err : 'non-2xx',
			], 502);
		}

		$data = json_decode($body, true);
		if (!is_array($data)) {
			return new DataResponse(['error' => 'invalid_json'], 502);
		}
		return new DataResponse($data);
	}

	public function health(): DataResponse {
		return $this->getJson('/health');
	}

	public function hostSummary(): DataResponse {
		return $this->getJson('/host/summary');
	}

	public function containers(): DataResponse {
		return $this->getJson('/containers');
	}

	public function stacks(): DataResponse {
		return $this->getJson('/stacks');
	}

	public function opsInbox(): DataResponse {
		return $this->getJson('/ops/inbox-summary');
	}

	/** Static Tools deep-links (Authentic Theme ports; Guac verified at deploy). */
	public function tools(): DataResponse {
		return new DataResponse([
			'tools' => [
				['title' => 'Portainer', 'url' => 'https://10.0.0.84:9443'],
				['title' => 'Webmin', 'url' => 'https://10.0.0.84:10000'],
				['title' => 'Uptime Kuma', 'url' => 'http://10.0.0.84:3100'],
				['title' => 'Caddy Proxy', 'url' => 'http://10.0.0.84:3080'],
				['title' => 'Guacamole', 'url' => 'http://10.0.0.84:8081', 'note' => 'also Tomcat on :8280'],
				['title' => 'WebODM', 'url' => 'http://10.0.0.84:8001'],
				['title' => 'WireGuard', 'url' => 'http://10.0.0.84:51821'],
				['title' => 'OrcaSlicer', 'url' => 'http://10.0.0.84:3030'],
				['title' => 'ADSB Feeder', 'url' => 'http://10.0.0.84:8087'],
				['title' => 'MediaMTX', 'url' => 'http://10.0.0.84:8889'],
				['title' => 'Nextcloud', 'url' => 'http://10.0.0.84:8080'],
			],
		]);
	}
}
