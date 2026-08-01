<?php

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\AppFramework\Http\DataResponse;
use OCP\IConfig;
use OCP\IRequest;
use Psr\Log\LoggerInterface;

/**
 * Proxies Control Tower sidecar (RO + allowlisted mutators).
 * Never talks to docker.sock from PHP.
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

	/** @param array<string,string> $extraHeaders */
	private function requestJson(string $method, string $path, ?array $body = null): DataResponse {
		$url = $this->sidecarBase() . $path;
		$token = $this->sidecarToken();
		$headers = ['Accept: application/json'];
		if ($token !== '') {
			$headers[] = 'X-Ops-Token: ' . $token;
		}
		if ($body !== null) {
			$headers[] = 'Content-Type: application/json';
		}

		$ch = curl_init($url);
		if ($ch === false) {
			return new DataResponse(['error' => 'curl_init failed', 'ok' => false], 502);
		}
		$opts = [
			CURLOPT_RETURNTRANSFER => true,
			CURLOPT_TIMEOUT => ($method === 'POST' ? 130 : 25),
			CURLOPT_HTTPHEADER => $headers,
			CURLOPT_CUSTOMREQUEST => $method,
		];
		if ($body !== null) {
			$opts[CURLOPT_POSTFIELDS] = json_encode($body);
		}
		curl_setopt_array($ch, $opts);
		$respBody = curl_exec($ch);
		$code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
		$err = curl_error($ch);
		curl_close($ch);

		if ($respBody === false || $code < 200 || $code >= 300) {
			$this->logger->warning('Control Tower sidecar error', [
				'url' => $url,
				'http' => $code,
				'err' => $err,
				'method' => $method,
			]);
			$data = [];
			if (is_string($respBody) && $respBody !== '') {
				$decoded = json_decode($respBody, true);
				if (is_array($decoded)) {
					$data = $decoded;
				}
			}
			return new DataResponse(array_merge([
				'ok' => false,
				'error' => 'sidecar_unavailable',
				'http' => $code,
				'detail' => $err !== '' ? $err : 'non-2xx',
			], $data), $code >= 400 ? $code : 502);
		}

		$data = json_decode($respBody, true);
		if (!is_array($data)) {
			return new DataResponse(['ok' => false, 'error' => 'invalid_json'], 502);
		}
		return new DataResponse($data, $code ?: 200);
	}

	private function getJson(string $path): DataResponse {
		return $this->requestJson('GET', $path);
	}

	#[NoCSRFRequired]
	public function health(): DataResponse {
		return $this->getJson('/health');
	}

	#[NoCSRFRequired]
	public function hostSummary(): DataResponse {
		return $this->getJson('/host/summary');
	}

	#[NoCSRFRequired]
	public function hostGpu(): DataResponse {
		return $this->getJson('/host/gpu');
	}

	#[NoCSRFRequired]
	public function hostSmart(): DataResponse {
		return $this->getJson('/host/smart');
	}

	#[NoCSRFRequired]
	public function hostFan(): DataResponse {
		return $this->getJson('/host/fan');
	}

	#[NoCSRFRequired]
	public function containers(): DataResponse {
		return $this->getJson('/containers');
	}

	#[NoCSRFRequired]
	public function containerLogs(string $name): DataResponse {
		$tail = (int) $this->request->getParam('tail', '100');
		$tail = max(1, min($tail, 500));
		return $this->getJson('/containers/' . rawurlencode($name) . '/logs?tail=' . $tail);
	}

	#[NoCSRFRequired]
	public function stacks(): DataResponse {
		return $this->getJson('/stacks');
	}

	#[NoCSRFRequired]
	public function opsInbox(): DataResponse {
		return $this->getJson('/ops/inbox-summary');
	}

	/** CSRF required — mutator */
	public function containerAction(string $name, string $action): DataResponse {
		$action = strtolower($action);
		if (!in_array($action, ['start', 'stop', 'restart'], true)) {
			return new DataResponse(['ok' => false, 'error' => 'invalid_action'], 400);
		}
		return $this->requestJson('POST', '/containers/' . rawurlencode($name) . '/' . $action, []);
	}

	/** @return array<string,mixed> */
	private function jsonBody(): array {
		$raw = file_get_contents('php://input');
		if (!is_string($raw) || $raw === '') {
			return [];
		}
		$data = json_decode($raw, true);
		return is_array($data) ? $data : [];
	}

	/** CSRF required */
	public function stackUp(): DataResponse {
		$body = $this->jsonBody();
		$file = (string) ($body['file'] ?? $this->request->getParam('file', ''));
		return $this->requestJson('POST', '/stacks/up', ['file' => $file]);
	}

	/** CSRF required */
	public function stackDown(): DataResponse {
		$body = $this->jsonBody();
		$file = (string) ($body['file'] ?? $this->request->getParam('file', ''));
		return $this->requestJson('POST', '/stacks/down', ['file' => $file]);
	}

	/** CSRF required */
	public function fanSet(): DataResponse {
		$body = $this->jsonBody();
		$op = (string) ($body['op'] ?? $this->request->getParam('op', ''));
		$payload = ['op' => $op];
		$speed = $body['speed'] ?? $this->request->getParam('speed');
		$fan = $body['fan'] ?? $this->request->getParam('fan');
		if ($speed !== null && $speed !== '') {
			$payload['speed'] = (int) $speed;
		}
		if ($fan !== null && $fan !== '') {
			$payload['fan'] = (int) $fan;
		}
		return $this->requestJson('POST', '/host/fan', $payload);
	}

	#[NoCSRFRequired]
	public function tools(): DataResponse {
		$baseWebmin = 'https://10.0.0.84:10000';
		return new DataResponse([
			'groups' => [
				[
					'title' => 'Orchestration',
					'tools' => [
						['title' => 'Portainer', 'url' => 'https://10.0.0.84:9443'],
						['title' => 'Webmin', 'url' => $baseWebmin],
					],
				],
				[
					'title' => 'Host (Webmin modules)',
					'tools' => [
						['title' => 'System Health', 'url' => $baseWebmin . '/system-health/'],
						['title' => 'Docker', 'url' => $baseWebmin . '/docker/'],
						['title' => 'Docker Stacks', 'url' => $baseWebmin . '/docker-stacks/'],
						['title' => 'NVIDIA GPU', 'url' => $baseWebmin . '/nvidia-gpu/'],
						['title' => 'SMART Health', 'url' => $baseWebmin . '/smart-health/'],
						['title' => 'Backup Mgr', 'url' => $baseWebmin . '/backup-mgr/'],
						['title' => 'Fan Control (chassis)', 'url' => $baseWebmin . '/fan-control/'],
					],
				],
				[
					'title' => 'Apps',
					'tools' => [
						['title' => 'Uptime Kuma', 'url' => 'http://10.0.0.84:3100'],
						['title' => 'Caddy Proxy', 'url' => 'http://10.0.0.84:3080'],
						['title' => 'Guacamole', 'url' => 'http://10.0.0.84:8081'],
						['title' => 'WebODM', 'url' => 'http://10.0.0.84:8001'],
						['title' => 'OrcaSlicer', 'url' => 'http://10.0.0.84:3030'],
						['title' => 'ADSB Feeder', 'url' => 'http://10.0.0.84:8087'],
						['title' => 'MediaMTX', 'url' => 'http://10.0.0.84:8889'],
						['title' => 'Nextcloud', 'url' => 'http://10.0.0.84:8080'],
					],
				],
				[
					'title' => 'VPN',
					'tools' => [
						[
							'title' => 'WireGuard',
							'url' => '',
							'note' => 'Use the Nextcloud WireGuard app (not managed in Control Tower).',
						],
					],
				],
			],
			// Flat list for older callers
			'tools' => [
				['title' => 'Portainer', 'url' => 'https://10.0.0.84:9443'],
				['title' => 'Webmin', 'url' => $baseWebmin],
				['title' => 'Uptime Kuma', 'url' => 'http://10.0.0.84:3100'],
				['title' => 'Caddy Proxy', 'url' => 'http://10.0.0.84:3080'],
				['title' => 'Guacamole', 'url' => 'http://10.0.0.84:8081'],
				['title' => 'WebODM', 'url' => 'http://10.0.0.84:8001'],
				['title' => 'OrcaSlicer', 'url' => 'http://10.0.0.84:3030'],
				['title' => 'ADSB Feeder', 'url' => 'http://10.0.0.84:8087'],
				['title' => 'MediaMTX', 'url' => 'http://10.0.0.84:8889'],
				['title' => 'Nextcloud', 'url' => 'http://10.0.0.84:8080'],
			],
		]);
	}
}
