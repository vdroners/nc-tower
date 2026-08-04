<?php
/**
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * NC Tower — Nextcloud admin orchestrator (vdroners / 19labs).
 * See CREDITS.md for heritage notes.
 */

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\FrontpageRoute;
use OCP\AppFramework\Http\Attribute\NoAdminRequired;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\IL10N;
use OCP\IConfig;
use OCP\AppFramework\Db\TTransactional;
use OCP\IDBConnection;
use OCP\DB\QueryBuilder\IQueryBuilder;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\Http\JSONResponse;
use OCA\NcTower\Service\MyService;
use OCP\IRequest;
use Psr\Log\LoggerInterface;
use OCP\IAppConfig;
use OCP\App\IAppManager;

use OCP\IUserManager;
use OCP\IGroupManager;

class GroupController extends Controller {
    private $myService;
    private $logger;
    private $config;
    private $userManager;
    private $groupManager;
    private $l;
    private IAppManager $appManager;

    public function __construct(
            string $appName, 
            IRequest $request, 
            MyService $myService, 
            LoggerInterface $logger, 
            IConfig $config,
            IAppManager $appManager,
            IUserManager $userManager, 
            IGroupManager $groupManager, 
            IL10N $l, 
            private IAppConfig $appConfig
        ) {
        parent::__construct($appName, $request);
        $this->myService = $myService;
        $this->logger = $logger;
        $this->config = $config;
        $this->appManager = $appManager;
        $this->userManager = $userManager;
        $this->groupManager = $groupManager;
        $this->l = $l;
    }

    
    
    public function addgroup($who): DataResponse {
        try {
            if ($this->groupManager->groupExists($who)) {
                return new DataResponse(['ok' => false, 'gid' => $who, 'error' => 'group exists'], 409);
            }
            $this->groupManager->createGroup($who);
            return new DataResponse(['ok' => true, 'gid' => $who]);
        } catch (\Throwable $e) {
            $this->logger->error(
                'NcTower: FATAL ERROR or EXCEPTION in DataController->addgroup: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
                ['app' => 'nc_tower']
            );
            return new DataResponse(['ok' => false, 'gid' => $who, 'error' => $e->getMessage()], 500);
        }
    }
    
    public function deletegroup($who): DataResponse {
        try {
            if ($this->groupManager->groupExists($who)) { 
                $this->myService->deletegroup($who);
                return new DataResponse(['ok' => true, 'gid' => $who]);
            }
            return new DataResponse(['ok' => false, 'gid' => $who, 'error' => 'group not found'], 404);
        } catch (\Throwable $e) {
            $this->logger->error(
                'NcTower: FATAL ERROR or EXCEPTION in DataController->deletegroup: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
                ['app' => 'nc_tower']
            );
            return new DataResponse(['ok' => false, 'gid' => $who, 'error' => $e->getMessage()], 500);
        }
    }
  
  
}
