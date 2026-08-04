<?php

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\AppFramework\Http\DataResponse;
use OCP\DB\QueryBuilder\IQueryBuilder;
use OCP\IDBConnection;
use OCP\IConfig;
use OCP\IRequest;
use OCP\SetupCheck\ISetupCheckManager;
use OCP\SetupCheck\SetupResult;
use Psr\Log\LoggerInterface;

/**
 * Read-only Nextcloud admin depth for NC Tower System tab.
 * Uses OCP APIs and IDBConnection only — no occ, no sidecar.
 */
class NcAdminController extends Controller {
	public function __construct(
		string $appName,
		IRequest $request,
		private IConfig $config,
		private IDBConnection $db,
		private LoggerInterface $logger,
		private ?ISetupCheckManager $setupChecks = null,
	) {
		parent::__construct($appName, $request);
	}

	private function logPath(): string {
		$path = (string) $this->config->getSystemValue('logfile', '');
		if ($path === '' || !is_file($path)) {
			$path = rtrim((string) $this->config->getSystemValue('datadirectory', ''), '/') . '/nextcloud.log';
		}
		return $path;
	}

	#[NoCSRFRequired]
	public function log(): DataResponse {
		$lines = max(10, min((int) $this->request->getParam('lines', '200'), 2000));
		$level = strtolower((string) $this->request->getParam('level', ''));
		$query = (string) $this->request->getParam('query', '');
		$path = $this->logPath();
		if (!is_file($path) || !is_readable($path)) {
			return new DataResponse([
				'ok' => false,
				'unavailable' => true,
				'reason' => 'logfile_unreadable',
				'path' => $path,
				'rows' => [],
			], 404);
		}

		$raw = @file($path, FILE_IGNORE_NEW_LINES);
		if ($raw === false) {
			return new DataResponse(['ok' => false, 'error' => 'read_failed', 'rows' => []], 500);
		}
		$slice = array_slice($raw, -$lines * 3); // oversample then filter
		$rows = [];
		foreach ($slice as $line) {
			$line = trim($line);
			if ($line === '') {
				continue;
			}
			$decoded = json_decode($line, true);
			if (!is_array($decoded)) {
				$decoded = ['message' => $line, 'level' => null];
			}
			$entryLevel = strtolower((string) ($decoded['level'] ?? $decoded['levelName'] ?? ''));
			// Nextcloud uses numeric levels sometimes
			if (is_numeric($decoded['level'] ?? null)) {
				$map = [0 => 'debug', 1 => 'info', 2 => 'warning', 3 => 'error', 4 => 'fatal'];
				$entryLevel = $map[(int) $decoded['level']] ?? $entryLevel;
			}
			if ($level !== '' && $entryLevel !== '' && !str_contains($entryLevel, $level) && $level !== $entryLevel) {
				// allow warn↔warning
				if (!($level === 'warn' && str_starts_with($entryLevel, 'warn'))
					&& !($level === 'error' && (str_starts_with($entryLevel, 'error') || $entryLevel === 'fatal'))) {
					continue;
				}
			}
			if ($query !== '') {
				$hay = strtolower(json_encode($decoded, JSON_UNESCAPED_UNICODE) ?: $line);
				if (!str_contains($hay, strtolower($query))) {
					continue;
				}
			}
			$rows[] = [
				'time' => $decoded['time'] ?? null,
				'level' => $entryLevel ?: ($decoded['level'] ?? null),
				'app' => $decoded['app'] ?? null,
				'reqId' => $decoded['reqId'] ?? null,
				'user' => $decoded['user'] ?? null,
				'message' => $decoded['message'] ?? $line,
				'exception' => isset($decoded['exception']) ? (
					is_array($decoded['exception'])
						? ($decoded['exception']['Exception'] ?? $decoded['exception']['Message'] ?? 'exception')
						: (string) $decoded['exception']
				) : null,
			];
		}
		$rows = array_slice($rows, -$lines);
		return new DataResponse([
			'ok' => true,
			'path' => $path,
			'size' => filesize($path) ?: 0,
			'rows' => array_values($rows),
			'ts' => time(),
		]);
	}

	#[NoCSRFRequired]
	public function setupChecks(): DataResponse {
		if ($this->setupChecks === null) {
			try {
				$this->setupChecks = \OCP\Server::get(ISetupCheckManager::class);
			} catch (\Throwable $e) {
				return new DataResponse([
					'ok' => false,
					'unavailable' => true,
					'reason' => $e->getMessage(),
					'checks' => [],
				]);
			}
		}
		try {
			$all = $this->setupChecks->runAll();
		} catch (\Throwable $e) {
			$this->logger->warning('NC Tower setup checks failed', ['exception' => $e]);
			return new DataResponse(['ok' => false, 'error' => $e->getMessage(), 'checks' => []], 500);
		}
		$checks = [];
		$errorCount = 0;
		$warnCount = 0;
		foreach ($all as $category => $group) {
			if (!is_array($group)) {
				continue;
			}
			foreach ($group as $title => $result) {
				$severity = SetupResult::INFO;
				$description = null;
				$link = null;
				$name = is_string($title) ? $title : (string) $title;
				if ($result instanceof SetupResult) {
					$data = $result->jsonSerialize();
					$severity = (string) ($data['severity'] ?? SetupResult::INFO);
					$description = $data['description'] ?? null;
					$link = $data['linkToDoc'] ?? null;
					if (!empty($data['name'])) {
						$name = (string) $data['name'];
					}
				} elseif (is_array($result)) {
					$severity = (string) ($result['severity'] ?? SetupResult::INFO);
					$description = $result['description'] ?? null;
					$link = $result['linkToDoc'] ?? null;
				}
				if ($severity === SetupResult::ERROR) {
					$errorCount++;
				} elseif ($severity === SetupResult::WARNING) {
					$warnCount++;
				}
				$checks[] = [
					'category' => (string) $category,
					'name' => $name,
					'severity' => $severity,
					'description' => $description,
					'link' => $link,
				];
			}
		}
		usort($checks, static function (array $a, array $b): int {
			$rank = [SetupResult::ERROR => 0, SetupResult::WARNING => 1, SetupResult::INFO => 2, SetupResult::SUCCESS => 3];
			return ($rank[$a['severity']] ?? 9) <=> ($rank[$b['severity']] ?? 9);
		});
		return new DataResponse([
			'ok' => true,
			'checks' => $checks,
			'error_count' => $errorCount,
			'warn_count' => $warnCount,
			'ts' => time(),
		]);
	}

	#[NoCSRFRequired]
	public function jobs(): DataResponse {
		$lastCron = (int) $this->config->getAppValue('core', 'lastcron', '0');
		$cronMode = (string) $this->config->getAppValue('core', 'backgroundjobs_mode', 'ajax');
		$now = time();
		$age = $lastCron > 0 ? max(0, $now - $lastCron) : null;

		$count = 0;
		$oldest = null;
		$oldestClass = null;
		try {
			$qb = $this->db->getQueryBuilder();
			$count = (int) ($qb->select($qb->func()->count('*', 'c'))
				->from('jobs')
				->executeQuery()
				->fetchOne() ?: 0);
			$qb2 = $this->db->getQueryBuilder();
			$row = $qb2->select('class', 'last_run')
				->from('jobs')
				->where($qb2->expr()->gt('last_run', $qb2->createNamedParameter(0, IQueryBuilder::PARAM_INT)))
				->orderBy('last_run', 'ASC')
				->setMaxResults(1)
				->executeQuery()
				->fetch();
			if (is_array($row)) {
				$oldest = (int) ($row['last_run'] ?? 0);
				$oldestClass = (string) ($row['class'] ?? '');
			}
		} catch (\Throwable $e) {
			$this->logger->warning('NC Tower jobs query failed', ['exception' => $e]);
		}

		return new DataResponse([
			'ok' => true,
			'lastcron' => $lastCron ?: null,
			'lastcron_age_s' => $age,
			'cron_mode' => $cronMode,
			'job_count' => $count,
			'oldest_last_run' => $oldest,
			'oldest_class' => $oldestClass,
			'stale' => $age !== null && $age > 900,
			'ts' => $now,
		]);
	}

	#[NoCSRFRequired]
	public function bruteforce(): DataResponse {
		$since = time() - 86400;
		$rows = [];
		$total = 0;
		try {
			$qb = $this->db->getQueryBuilder();
			$result = $qb->select('ip', 'action')
				->selectAlias($qb->func()->count('*'), 'attempts')
				->selectAlias($qb->func()->max('occurred'), 'last_occurred')
				->from('bruteforce_attempts')
				->where($qb->expr()->gte('occurred', $qb->createNamedParameter($since, IQueryBuilder::PARAM_INT)))
				->groupBy('ip', 'action')
				->orderBy('attempts', 'DESC')
				->setMaxResults(100)
				->executeQuery();
			while ($row = $result->fetch()) {
				$attempts = (int) ($row['attempts'] ?? 0);
				$total += $attempts;
				$rows[] = [
					'ip' => $row['ip'] ?? null,
					'action' => $row['action'] ?? null,
					'attempts' => $attempts,
					'last_occurred' => isset($row['last_occurred']) ? (int) $row['last_occurred'] : null,
				];
			}
		} catch (\Throwable $e) {
			return new DataResponse(['ok' => false, 'error' => $e->getMessage(), 'rows' => []], 500);
		}
		return new DataResponse([
			'ok' => true,
			'rows' => $rows,
			'total_24h' => $total,
			'ts' => time(),
		]);
	}

	#[NoCSRFRequired]
	public function shares(): DataResponse {
		$now = time();
		$publicType = 3; // IShare::TYPE_LINK
		$risky = [];
		$byOwner = [];
		try {
			$qb = $this->db->getQueryBuilder();
			$result = $qb->select('id', 'uid_owner', 'share_type', 'password', 'expiration', 'token', 'file_target', 'share_name', 'item_type')
				->from('share')
				->where($qb->expr()->eq('share_type', $qb->createNamedParameter($publicType, IQueryBuilder::PARAM_INT)))
				->setMaxResults(500)
				->executeQuery();
			while ($row = $result->fetch()) {
				$owner = (string) ($row['uid_owner'] ?? '');
				$byOwner[$owner] = ($byOwner[$owner] ?? 0) + 1;
				$hasPassword = !empty($row['password']);
				$expiration = $row['expiration'] ?? null;
				$expTs = null;
				if (is_string($expiration) && $expiration !== '') {
					$expTs = strtotime($expiration) ?: null;
				}
				$expired = $expTs !== null && $expTs < $now;
				$noExpiry = $expiration === null || $expiration === '';
				if (!$hasPassword || $noExpiry || $expired) {
					$risky[] = [
						'id' => (int) ($row['id'] ?? 0),
						'owner' => $owner,
						'target' => $row['file_target'] ?? $row['share_name'] ?? null,
						'item_type' => $row['item_type'] ?? null,
						'has_password' => $hasPassword,
						'no_expiry' => $noExpiry,
						'expired' => $expired,
						'expiration' => $expiration,
					];
				}
			}
		} catch (\Throwable $e) {
			return new DataResponse(['ok' => false, 'error' => $e->getMessage(), 'risky' => []], 500);
		}
		$passwordless = count(array_filter($risky, static fn (array $r) => empty($r['has_password'])));
		return new DataResponse([
			'ok' => true,
			'risky' => $risky,
			'by_owner' => $byOwner,
			'passwordless_count' => $passwordless,
			'ts' => $now,
		]);
	}

	#[NoCSRFRequired]
	public function sessions(): DataResponse {
		$rows = [];
		try {
			$qb = $this->db->getQueryBuilder();
			$result = $qb->select('id', 'uid', 'login_name', 'name', 'type', 'last_activity', 'remember')
				->from('authtoken')
				->orderBy('last_activity', 'DESC')
				->setMaxResults(200)
				->executeQuery();
			while ($row = $result->fetch()) {
				$rows[] = [
					'id' => (int) ($row['id'] ?? 0),
					'uid' => $row['uid'] ?? null,
					'login_name' => $row['login_name'] ?? null,
					'name' => $row['name'] ?? null,
					'type' => (int) ($row['type'] ?? 0),
					'last_activity' => isset($row['last_activity']) ? (int) $row['last_activity'] : null,
					'remember' => !empty($row['remember']),
				];
			}
		} catch (\Throwable $e) {
			return new DataResponse(['ok' => false, 'error' => $e->getMessage(), 'rows' => []], 500);
		}
		return new DataResponse(['ok' => true, 'rows' => $rows, 'ts' => time()]);
	}

	#[NoCSRFRequired]
	public function bloat(): DataResponse {
		$datadir = (string) $this->config->getSystemValue('datadirectory', '');
		$totalBytes = 0;
		if ($datadir !== '' && is_dir($datadir)) {
			$totalBytes = (int) (@disk_total_space($datadir) ?: 0) - (int) (@disk_free_space($datadir) ?: 0);
			if ($totalBytes < 0) {
				$totalBytes = 0;
			}
		}

		$buckets = [
			'trashbin' => ['path_like' => 'files_trashbin/%'],
			'versions' => ['path_like' => 'files_versions/%'],
			'previews' => ['path_like' => 'appdata_%/preview/%'],
		];
		$sizes = [];
		try {
			foreach ($buckets as $key => $spec) {
				$qb = $this->db->getQueryBuilder();
				$qb->selectAlias($qb->func()->sum('size'), 'bytes')
					->selectAlias($qb->func()->count('*'), 'files')
					->from('filecache')
					->where($qb->expr()->like('path', $qb->createNamedParameter($spec['path_like'])))
					->andWhere($qb->expr()->gte('size', $qb->createNamedParameter(0, IQueryBuilder::PARAM_INT)));
				$row = $qb->executeQuery()->fetch();
				$bytes = max(0, (int) ($row['bytes'] ?? 0));
				$sizes[$key] = [
					'bytes' => $bytes,
					'files' => (int) ($row['files'] ?? 0),
					'pct_of_datadir' => $totalBytes > 0 ? round(100.0 * $bytes / $totalBytes, 2) : null,
				];
			}
		} catch (\Throwable $e) {
			return new DataResponse(['ok' => false, 'error' => $e->getMessage(), 'sizes' => []], 500);
		}

		return new DataResponse([
			'ok' => true,
			'sizes' => $sizes,
			'datadir_used_approx_bytes' => $totalBytes,
			'ts' => time(),
		]);
	}

	#[NoCSRFRequired]
	public function maintenance(): DataResponse {
		$enabled = (bool) $this->config->getSystemValue('maintenance', false);
		return new DataResponse([
			'ok' => true,
			'maintenance' => $enabled,
			'note' => 'Status only — toggle via occ; enabling from Tower would lock the app out.',
			'ts' => time(),
		]);
	}
}
