<?php

declare(strict_types=1);

namespace OCA\NcTower\Middleware;

use OCA\NcTower\Exception\ForbiddenException;
use OCP\AppFramework\Http\JSONResponse;
use OCP\AppFramework\Middleware;
use OCP\IGroupManager;
use OCP\IUserSession;
use Psr\Log\LoggerInterface;

/**
 * Admin gate for every NC Tower controller.
 *
 * Nextcloud's own SecurityMiddleware only enforces admin when a method carries
 * #[AuthorizedAdminSetting]/#[SubAdminRequired]; a plain controller method is
 * reachable by any logged-in user. NC Tower drives a host-root sidecar, so it
 * must not rely on that default, nor on the app being enabled only for the
 * admin group (a boot-time side effect that `occ app:enable` can widen).
 *
 * The check lives in beforeController so it covers every action of every
 * controller with nothing to forget per method — the whole app is admin-only by
 * design. afterException renders the denial (mirrors the estate ForbiddenMiddleware).
 */
class ForbiddenMiddleware extends Middleware {
	public function __construct(
		private IUserSession $userSession,
		private IGroupManager $groupManager,
		private LoggerInterface $logger,
	) {
	}

	public function beforeController($controller, $methodName): void {
		// Core SecurityMiddleware has already rejected anonymous requests to
		// non-public routes, so a null user here means deny outright.
		$user = $this->userSession->getUser();
		if ($user === null || !$this->groupManager->isAdmin($user->getUID())) {
			throw new ForbiddenException('administrator access required');
		}
	}

	public function afterException($controller, $methodName, \Exception $exception): JSONResponse {
		if ($exception instanceof ForbiddenException) {
			$this->logger->warning('NC Tower access denied on {controller}::{method}: {msg}', [
				'controller' => get_class($controller),
				'method' => $methodName,
				'msg' => $exception->getMessage(),
				'app' => 'nc_tower',
			]);
			return new JSONResponse(['error' => 'forbidden', 'message' => $exception->getMessage()], 403);
		}
		throw $exception;
	}
}
