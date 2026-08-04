<?php
/**
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * NC Tower — Nextcloud admin orchestrator (vdroners / 19labs).
 * See CREDITS.md for heritage notes.
 */

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCA\NcTower\Service\MyService;
use OCP\App\IAppManager;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\Attribute\AdminRequired;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\Http\JSONResponse;
use OCP\IConfig;
use OCP\IGroupManager;
use OCP\IL10N;
use OCP\IRequest;
use OCP\IUserManager;
use OCP\IUserSession;
use OCP\Settings\IManager;
use Psr\Log\LoggerInterface;

/**
 * Apps admin surface using public OCP APIs only.
 *
 * App Store install/update is driven from the Vue client via appstore OCS
 * (not OC\Installer in this PHP). Enable/disable stays on IAppManager.
 */
class AppsController extends Controller {
	private MyService $myService;
	private LoggerInterface $logger;
	private IConfig $config;
	private IUserManager $userManager;
	private IGroupManager $groupManager;
	private IL10N $l;
	private IAppManager $appManager;
	private IUserSession $userSession;
	private IManager $settingManager;

	public function __construct(
		string $appName,
		IRequest $request,
		MyService $myService,
		LoggerInterface $logger,
		IConfig $config,
		IAppManager $appManager,
		IUserManager $userManager,
		IGroupManager $groupManager,
		IUserSession $userSession,
		IL10N $l,
		IManager $settingManager,
	) {
		parent::__construct($appName, $request);
		$this->myService = $myService;
		$this->logger = $logger;
		$this->config = $config;
		$this->appManager = $appManager;
		$this->userManager = $userManager;
		$this->groupManager = $groupManager;
		$this->settingManager = $settingManager;
		$this->userSession = $userSession;
		$this->l = $l;
	}

	#[AdminRequired]
	#[NoCSRFRequired]
	public function appsinfo(): DataResponse {
		try {
			$thisapps = array_values($this->appManager->getAllAppsInAppsFolders());
			sort($thisapps);
			$ncinfo = $this->myService->getNCInfo();
			$parts = explode('.', $ncinfo['nc_version']);
			$version = (int)$parts[0];
			if ($version < 32) {
				$thisappsenabled = array_values($this->appManager->getEnabledAppsForUser($this->userSession->getUser()));
			} else {
				$thisappsenabled = array_values($this->appManager->getEnabledApps());
			}
			$thisappsdisabled = array_values(array_diff($thisapps, $thisappsenabled));
			// Build enable/disable lists first so a settings-section failure still
			// returns a usable Apps tab.
			$thisappsenabledfull = $this->appsfull($thisappsenabled);
			$thisappsdisabledfull = $this->appsfull($thisappsdisabled);

			$adminsections = [];
			$adminsectionsappname = [];
			$adminsectionsappicon = [];
			$personalsections = [];
			$personalsectionsappname = [];
			$personalsectionsappicon = [];
			$settingsError = null;
			try {
				$getadminsections = $this->settingManager->getAdminSections();
				$getpersonalsections = $this->settingManager->getPersonalSections();
				$i = 0;
				foreach ($getadminsections as $dummy) {
					foreach ($dummy as $adminsection) {
						if ($adminsection->getID() != 'additional') {
							$adminsections[] = $adminsection->getID();
							$adminsectionsappname[] = $adminsection->getName() ?: $adminsection->getID();
							$adminsectionsappicon[] = $adminsection->getIcon();
						}
						$i++;
					}
				}
				$i = 0;
				foreach ($getpersonalsections as $dummy) {
					foreach ($dummy as $personalsection) {
						if ($personalsection->getID() != 'calendar') {
							$personalsections[] = $personalsection->getID();
							$personalsectionsappname[] = $personalsection->getName() ?: $personalsection->getID();
							$personalsectionsappicon[] = $personalsection->getIcon();
						}
						$i++;
					}
				}
			} catch (\Throwable $e) {
				$settingsError = $e->getMessage();
				$this->logger->warning(
					'NcTower: settings section enum failed in appsinfo: ' . $e->getMessage(),
					['app' => 'nc_tower']
				);
			}

			$payload = [
				'adminsections' => array_values($adminsections),
				'adminsectionsappname' => array_values($adminsectionsappname),
				'adminsectionsappicon' => array_values($adminsectionsappicon),
				'personalsections' => array_values($personalsections),
				'personalsectionsappname' => array_values($personalsectionsappname),
				'personalsectionsappicon' => array_values($personalsectionsappicon),
				'allapps' => count($thisapps),
				'appsenabled' => count($thisappsenabled),
				'thisapps' => $thisapps,
				'thisappsenabled' => $thisappsenabled,
				'thisappsdisabled' => $thisappsdisabled,
				'thisappsdisabledfull' => array_values($thisappsdisabledfull),
				'thisappsenabledfull' => array_values($thisappsenabledfull),
			];
			if ($settingsError !== null) {
				$payload['settings_error'] = $settingsError;
			}
			return new DataResponse($payload);
		} catch (\Throwable $e) {
			$this->logger->error(
				'NcTower: FATAL ERROR or EXCEPTION in AppsController->appsinfo: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
				['app' => 'nc_tower']
			);
			return new DataResponse([
				'db' => -1,
			], 500);
		}
	}

	/**
	 * @param list<string> $apps
	 * @return list<array<string,mixed>>
	 */
	public function appsfull($apps): array {
		$i = 0;
		$wtarr = [];

		foreach ($apps as $appid) {
			$icon = $this->appManager->getAppIcon($appid, false);

			$wtarr[$i]['appid'] = $appid;
			$appinfo = $this->appManager->getAppInfo($appid, false, 'en_GB');
			$wtarr[$i]['name'] = $this->appDisplayName($appid, $appinfo);
			$wtarr[$i]['id'] = $i;
			$wtarr[$i]['icon'] = $icon ? $icon : $this->appManager->getAppWebPath('nc_tower') . '/img/dummy.svg';

			$wtarr[$i]['version'] = $this->appManager->getAppVersion($appid, true);
			$wtarr[$i]['shipped'] = $this->appManager->isShipped($appid);
			$i++;
		}

		return $wtarr;
	}

	/**
	 * Flatten appinfo name (string or locale map) to a single display string.
	 *
	 * @param string $appid app id fallback
	 * @param array|null $appinfo OCP appinfo or null
	 */
	private function appDisplayName(string $appid, ?array $appinfo): string {
		if ($appinfo === null) {
			return $appid;
		}
		$name = $appinfo['name'] ?? $appid;
		if (is_string($name) && $name !== '') {
			return $name;
		}
		if (is_array($name) && $name !== []) {
			$first = reset($name);
			return is_string($first) && $first !== '' ? $first : $appid;
		}
		return $appid;
	}

	public function disableapp($who): DataResponse {
		try {
			if ($this->appManager->isEnabledForAnyone($who)) {
				$this->appManager->disableApp($who, false);
				return new DataResponse(['ok' => true, 'appid' => $who]);
			}
			return new DataResponse([
				'ok' => false,
				'appid' => $who,
				'error' => 'app not enabled',
			], Http::STATUS_BAD_REQUEST);
		} catch (\Throwable $e) {
			$this->logger->error(
				'NcTower: FATAL ERROR or EXCEPTION in AppsController->disableapp: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
				['app' => 'nc_tower']
			);
			return new DataResponse([
				'ok' => false,
				'appid' => $who,
				'error' => $e->getMessage(),
			], Http::STATUS_INTERNAL_SERVER_ERROR);
		}
	}

	public function enableapp($who): DataResponse {
		try {
			$this->appManager->enableApp($who, false);
			return new DataResponse(['ok' => true, 'appid' => $who]);
		} catch (\Throwable $e) {
			$this->logger->error(
				'NcTower: FATAL ERROR or EXCEPTION in AppsController->enableapp: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
				['app' => 'nc_tower']
			);
			return new DataResponse([
				'ok' => false,
				'appid' => $who,
				'error' => $e->getMessage(),
			], Http::STATUS_INTERNAL_SERVER_ERROR);
		}
	}

	/**
	 * Legacy PHP stub — live updates use client-side appstore OCS.
	 */
	public function updateapp(string $who): JSONResponse {
		return new JSONResponse([
			'data' => [
				'message' => $this->l->t('Use NC Tower Apps (appstore OCS) or Settings → Apps.'),
				'appid' => $who,
				'available' => false,
			],
		], Http::STATUS_NOT_IMPLEMENTED);
	}

	/**
	 * Legacy stub kept for old clients. Vue uses src/services/appstoreOcs.js.
	 */
	#[AdminRequired]
	#[NoCSRFRequired]
	public function getAppsWithUpdates(): DataResponse {
		return new DataResponse([
			'apps' => [],
			'appscount' => 0,
			'available' => false,
			'message' => $this->l->t('Update listing moved to appstore OCS in the browser. Use Settings → Apps if the client cannot reach the store.'),
		]);
	}

	#[AdminRequired]
	#[NoCSRFRequired]
	public function listCategories(): JSONResponse {
		return new JSONResponse([]);
	}

	#[AdminRequired]
	#[NoCSRFRequired]
	public function isnoti(): DataResponse {
		$ncinfo = $this->myService->getNCInfo();
		$parts = explode('.', $ncinfo['nc_version']);
		$version = (int)$parts[0];
		if ($version < 32) {
			$enabledapps = $this->appManager->getEnabledAppsForUser($this->userSession->getUser());
		} else {
			$enabledapps = $this->appManager->getEnabledApps();
		}

		$isnoti = in_array('notifications', $enabledapps, true) ? 'true' : 'false';

		return new DataResponse([
			'isnoti' => $isnoti,
		]);
	}

	#[AdminRequired]
	#[NoCSRFRequired]
	public function islogcleaner(): DataResponse {
		$ncinfo = $this->myService->getNCInfo();
		$parts = explode('.', $ncinfo['nc_version']);
		$version = (int)$parts[0];
		if ($version < 32) {
			$enabledapps = $this->appManager->getEnabledAppsForUser($this->userSession->getUser());
		} else {
			$enabledapps = $this->appManager->getEnabledApps();
		}

		$islogcleaner = in_array('logcleaner', $enabledapps, true) ? 'true' : 'false';

		return new DataResponse([
			'islogcleaner' => $islogcleaner,
		]);
	}
}
