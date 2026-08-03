<?php
/**
 *
 * NcTower APP (Nextcloud)
 *
 * @author Wolfgang Tödt <wtoedt@gmail.com>
 *
 * @copyright Copyright (c) 2025 Wolfgang Tödt
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */
declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCA\NcTower\Service\MyService;
use OCP\App\IAppManager;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
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
 * App Store install/update requires private Installer APIs that are not in OCP —
 * those features are stubbed; enable/disable stays available via IAppManager.
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

	public function appsinfo(): DataResponse {
		try {
			$thisapps = $this->appManager->getAllAppsInAppsFolders();
			sort($thisapps);
			$ncinfo = $this->myService->getNCInfo();
			$parts = explode('.', $ncinfo['nc_version']);
			$version = (int)$parts[0];
			if ($version < 32) {
				$thisappsenabled = $this->appManager->getEnabledAppsForUser($this->userSession->getUser());
			} else {
				$thisappsenabled = $this->appManager->getEnabledApps();
			}
			$thisappsdisabled = array_diff($thisapps, $thisappsenabled);
			$thisappsdisabledfull = $this->appsfull($thisappsdisabled);
			$thisappsenabledfull = $this->appsfull($thisappsenabled);
			$getadminsections = $this->settingManager->getAdminSections();
			$getpersonalsections = $this->settingManager->getPersonalSections();
			$adminsections = [];
			$adminsectionsappname = [];
			$adminsectionsappicon = [];
			$i = 0;
			foreach ($getadminsections as $dummy) {
				foreach ($dummy as $adminsection) {
					if ($adminsection->getID() != 'additional') {
						$adminsections[$i] = $adminsection->getID();
						$adminsectionsappname[$i] = $adminsection->getName() ?: $adminsection->getID();
						$adminsectionsappicon[$i] = $adminsection->getIcon();
					}
					$i++;
				}
			}
			$personalsections = [];
			$personalsectionsappname = [];
			$personalsectionsappicon = [];
			$i = 0;
			foreach ($getpersonalsections as $dummy) {
				foreach ($dummy as $personalsection) {
					if ($personalsection->getID() != 'calendar') {
						$personalsections[$i] = $personalsection->getID();
						$personalsectionsappname[$i] = $personalsection->getName() ?: $personalsection->getID();
						$personalsectionsappicon[$i] = $personalsection->getIcon();
					}
					$i++;
				}
			}

			return new DataResponse([
				'adminsections' => $adminsections,
				'adminsectionsappname' => $adminsectionsappname,
				'adminsectionsappicon' => $adminsectionsappicon,
				'personalsections' => $personalsections,
				'personalsectionsappname' => $personalsectionsappname,
				'personalsectionsappicon' => $personalsectionsappicon,
				'allapps' => count($thisapps),
				'appsenabled' => count($thisappsenabled),
				'thisapps' => $thisapps,
				'thisappsenabled' => $thisappsenabled,
				'thisappsdisabled' => $thisappsdisabled,
				'thisappsdisabledfull' => $thisappsdisabledfull,
				'thisappsenabledfull' => $thisappsenabledfull,
			]);
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
			if ($appinfo === null) {
				$obja = new \stdClass();
				$obja->appid = $appid;
				$obja->id = $i;
				$obja->name = $appid;
				$appinfo = $obja;
			}
			$wtarr[$i]['name'] = $appinfo;
			$wtarr[$i]['id'] = $i;
			$wtarr[$i]['icon'] = $icon ? $icon : $this->appManager->getAppWebPath('nc_tower') . '/img/dummy.svg';

			$wtarr[$i]['version'] = $this->appManager->getAppVersion($appid, true);
			$wtarr[$i]['shipped'] = $this->appManager->isShipped($appid);
			$i++;
		}

		return $wtarr;
	}

	public function disableapp($who) {
		try {
			if ($this->appManager->isInstalled($who)) {
				$this->appManager->disableApp($who, false);
				return 'true';
			}
			return 'false';
		} catch (\Throwable $e) {
			$this->logger->error(
				'NcTower: FATAL ERROR or EXCEPTION in AppsController->disableapp: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
				['app' => 'nc_tower']
			);
			return 'false';
		}
	}

	public function enableapp($who) {
		$this->appManager->enableApp($who, false);
		return 'true';
	}

	/**
	 * App Store updates require private OC\Installer — not available via OCP.
	 */
	public function updateapp(string $who): JSONResponse {
		return new JSONResponse([
			'data' => [
				'message' => $this->l->t('In-app updates are not available. Use Nextcloud Apps management.'),
				'appid' => $who,
				'available' => false,
			],
		], Http::STATUS_NOT_IMPLEMENTED);
	}

	/**
	 * Listing pending App Store updates requires private Installer APIs.
	 */
	public function getAppsWithUpdates(): DataResponse {
		return new DataResponse([
			'apps' => [],
			'appscount' => 0,
			'available' => false,
			'message' => $this->l->t('App update listing is not available via public APIs. Use Nextcloud Apps management.'),
		]);
	}

	public function listCategories(): JSONResponse {
		return new JSONResponse([]);
	}

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
