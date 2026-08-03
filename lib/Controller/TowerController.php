<?php

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\AppFramework\Http\DataResponse;
use OCA\NcTower\Service\EndpointConfigService;
use OCP\IConfig;
use OCP\IRequest;
use Psr\Log\LoggerInterface;

/**
 * Proxies Control Tower sidecar (RO + allowlisted mutators).
 * Docker engine access is only via the sidecar HTTP API.
 */
class TowerController extends Controller {
	public function __construct(
		string $appName,
		IRequest $request,
		private IConfig $config,
		private LoggerInterface $logger,
		private EndpointConfigService $endpoints,
	) {
		parent::__construct($appName, $request);
	}

	private function sidecarBase(): string {
		return $this->endpoints->getSidecarUrl();
	}

	private function sidecarToken(): string {
		// Empty default — fail closed if unset in config.php
		return $this->config->getSystemValueString('nc_tower_sidecar_token', '');
	}

	/** @param array<string,string> $extraHeaders */
	private function requestJson(string $method, string $path, ?array $body = null, int $timeout = 0): DataResponse {
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
		if ($timeout <= 0) {
			$timeout = ($method === 'POST' ? 130 : 25);
		}
		$opts = [
			CURLOPT_RETURNTRANSFER => true,
			CURLOPT_TIMEOUT => $timeout,
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

	private function getJson(string $path, int $timeout = 25): DataResponse {
		return $this->requestJson('GET', $path, null, $timeout);
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
		return $this->getJson('/host/smart', 60);
	}

	#[NoCSRFRequired]
	public function hostFan(): DataResponse {
		return $this->getJson('/host/fan');
	}

	#[NoCSRFRequired]
	public function hostChassisFan(): DataResponse {
		return $this->getJson('/host/chassis-fan');
	}

	#[NoCSRFRequired]
	public function hostMounts(): DataResponse {
		return $this->getJson('/host/mounts');
	}

	#[NoCSRFRequired]
	public function hostPackages(): DataResponse {
		return $this->getJson('/host/packages', 60);
	}

	#[NoCSRFRequired]
	public function hostProc(): DataResponse {
		return $this->getJson('/host/proc');
	}

	#[NoCSRFRequired]
	public function hostNet(): DataResponse {
		return $this->getJson('/host/net');
	}

	#[NoCSRFRequired]
	public function hostSystemd(): DataResponse {
		return $this->getJson('/host/systemd');
	}

	#[NoCSRFRequired]
	public function hostCron(): DataResponse {
		return $this->getJson('/host/cron');
	}

	#[NoCSRFRequired]
	public function containers(): DataResponse {
		return $this->getJson('/containers');
	}

	#[NoCSRFRequired]
	public function containerLogs(string $name): DataResponse {
		$tail = (int) $this->request->getParam('tail', '200');
		$tail = max(1, min($tail, 2000));
		$since = (string) $this->request->getParam('since', '');
		$q = '/containers/' . rawurlencode($name) . '/logs?tail=' . $tail;
		if ($since !== '') {
			$q .= '&since=' . rawurlencode($since);
		}
		return $this->getJson($q);
	}

	#[NoCSRFRequired]
	public function containerInspect(string $name): DataResponse {
		return $this->getJson('/containers/' . rawurlencode($name) . '/inspect');
	}

	#[NoCSRFRequired]
	public function dockerInfo(): DataResponse {
		return $this->getJson('/docker/info');
	}

	#[NoCSRFRequired]
	public function dockerDf(): DataResponse {
		return $this->getJson('/docker/df');
	}

	#[NoCSRFRequired]
	public function dockerEvents(): DataResponse {
		$since = (string) $this->request->getParam('since', '15m');
		$probes = (string) $this->request->getParam('probes', '0');
		return $this->getJson(
			'/docker/events?since=' . rawurlencode($since) . '&probes=' . ($probes === '1' ? '1' : '0'),
			40
		);
	}

	#[NoCSRFRequired]
	public function dockerImages(): DataResponse {
		return $this->getJson('/docker/images', 40);
	}

	#[NoCSRFRequired]
	public function dockerVolumes(): DataResponse {
		$name = (string) $this->request->getParam('name', '');
		$path = '/docker/volumes';
		if ($name !== '') {
			$path .= '?name=' . rawurlencode($name);
		}
		return $this->getJson($path);
	}

	#[NoCSRFRequired]
	public function dockerNetworks(): DataResponse {
		$name = (string) $this->request->getParam('name', '');
		$path = '/docker/networks';
		if ($name !== '') {
			$path .= '?name=' . rawurlencode($name);
		}
		return $this->getJson($path);
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
		if (!in_array($action, ['start', 'stop', 'restart', 'kill'], true)) {
			return new DataResponse(['ok' => false, 'error' => 'invalid_action'], 400);
		}
		return $this->requestJson('POST', '/containers/' . rawurlencode($name) . '/' . $action, []);
	}

	/** CSRF required */
	public function containerRecreate(string $name): DataResponse {
		$body = $this->jsonBody();
		return $this->requestJson('POST', '/containers/' . rawurlencode($name) . '/recreate', [
			'pull' => (bool) ($body['pull'] ?? false),
		], 180);
	}

	/** CSRF required */
	public function containerExec(string $name): DataResponse {
		$body = $this->jsonBody();
		return $this->requestJson('POST', '/containers/' . rawurlencode($name) . '/exec', $body, 90);
	}

	/** CSRF required */
	public function stackAction(string $action): DataResponse {
		$action = strtolower($action);
		if (!in_array($action, ['up', 'down', 'restart', 'pull', 'rebuild'], true)) {
			return new DataResponse(['ok' => false, 'error' => 'invalid_action'], 400);
		}
		$body = $this->jsonBody();
		$file = (string) ($body['file'] ?? $this->request->getParam('file', ''));
		return $this->requestJson('POST', '/stacks/' . $action, ['file' => $file], 180);
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

	/** CSRF required */
	public function imagePull(): DataResponse {
		$body = $this->jsonBody();
		return $this->requestJson('POST', '/docker/images/pull', [
			'image' => (string) ($body['image'] ?? ''),
		], 300);
	}

	/** CSRF required */
	public function backupRun(): DataResponse {
		return $this->requestJson('POST', '/ops/backup/run', [], 600);
	}

	/** CSRF required */
	public function systemdRestart(): DataResponse {
		$body = $this->jsonBody();
		return $this->requestJson('POST', '/host/systemd/restart', [
			'unit' => (string) ($body['unit'] ?? ''),
		]);
	}

	#[NoCSRFRequired]
	public function services(): DataResponse {
		return $this->getJson('/services/probe', 60);
	}

	#[NoCSRFRequired]
	public function hostUpdates(): DataResponse {
		return $this->getJson('/host/updates', 60);
	}

	#[NoCSRFRequired]
	public function hostHistory(): DataResponse {
		$limit = (int) $this->request->getParam('limit', '900');
		$limit = max(1, min($limit, 5000));
		return $this->getJson('/host/history?limit=' . $limit, 30);
	}

	#[NoCSRFRequired]
	public function opsTimeline(): DataResponse {
		$hours = (int) $this->request->getParam('hours', '24');
		$hours = max(1, min($hours, 336));
		return $this->getJson('/ops/timeline?hours=' . $hours, 30);
	}

	#[NoCSRFRequired]
	public function jobs(): DataResponse {
		return $this->getJson('/jobs');
	}

	#[NoCSRFRequired]
	public function job(string $id): DataResponse {
		return $this->getJson('/jobs/' . rawurlencode($id));
	}

	/**
	 * CSRF required — starts detached work on the host.
	 *
	 * The sidecar hands these to systemd so they outlive both this request and
	 * the sidecar itself; an apt upgrade restarts dockerd and would otherwise
	 * kill the container running it.
	 */
	public function jobStart(string $kind): DataResponse {
		return $this->requestJson('POST', '/jobs/' . rawurlencode($kind), $this->jsonBody(), 60);
	}

	#[NoCSRFRequired]
	public function tools(): DataResponse {
		return new DataResponse($this->endpoints->buildToolsPayload());
	}
}
