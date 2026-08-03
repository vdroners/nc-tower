<?php
/**
 *
 * NcTower APP (Nextcloud)
 *
 * @author Wolfgang Tödt <wtoedt@gmail.com>
 *
 * @copyright Copyright (c) 2025 Wolfgang Tödt
 *
 * @license GNU AGPL version 3 or any later version
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
use OCP\IUserSession;
use OCP\IUserManager;
use OCP\IGroupManager;

class UserController extends Controller {
    private $myService;
    private $logger;
    private $config;
    private $userManager;
    private $groupManager;
    private $l;
    private IAppManager $appManager;
    private IUserSession $userSession;

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
            private IAppConfig $appConfig
        ) {
        parent::__construct($appName, $request);
        $this->myService = $myService;
        $this->logger = $logger;
        $this->config = $config;
        $this->appManager = $appManager;
        $this->userManager = $userManager;
        $this->groupManager = $groupManager;
        $this->userSession = $userSession;
        $this->l = $l;
    }

    public function usercount(): DataResponse {
        try {
            $users = $this->userManager->search('');
            $userList = [];
            $usrlist = [];
            foreach ($users as $user) {
                if ($user->getLastLogin()) {
					$status = false;
				} else {
					$status = true;
				}
                $mids = $user->getManagerUids();
                if (!$mids) {
					$mids[] = null;
				}
                $usrlist[] = $user->getUID();
                $userList[] = [
                    'uid' => $user->getUID(),
                    'displayname' => $user->getDisplayName(),
                    'lastlogin' => $user->getLastLogin(),
                    'firstlogin' => $user->getFirstLogin(),
                    'email' => $user->getEMailAddress(),
                    'cloudid' => $user->getCloudId(),
                    'quota' => $user->getQuota(),
                    'managerids' => $mids,
                    'last' => $this->formatLoginTs($user->getLastLogin()),
                    'first' => $this->formatLoginTs($user->getFirstLogin()),
					// Never recurse user homes here — hangs on large datadirs.
                    'used' => $this->quotaUsedLabel($user),
                    'used_bytes' => $this->storageUsedMap()[$user->getUID()] ?? 0,
                    'isadmin' => $this->groupManager->isAdmin($user->getUID()),
                    'status' => $status,
                ];
            }

            $groups = $this->groupManager->search('');
            $groupList = [];
            $grlist = [];
            foreach ($groups as $group) {
                $gusers = $group->getUsers();
                $guserList = [];
                $grlist[] = $group->getGID();
				foreach ($gusers as $guser) {
					if ($guser->getLastLogin()) {
						$status = false;
					} else {
						$status = true;
					}
					$guserList[] = [
						'uid' => $guser->getUID(),
						'displayname' => $guser->getDisplayName(),
						'lastlogin' => $guser->getLastLogin(),
						'firstlogin' => $guser->getFirstLogin(),
						'email' => $guser->getEMailAddress(),
						'cloudid' => $guser->getCloudId(),
						'quota' => $guser->getQuota(),
						'managerids' => $guser->getManagerUids(),
						'last' => $this->formatLoginTs($guser->getLastLogin()),
						'first' => $this->formatLoginTs($guser->getFirstLogin()),
						'used' => $this->quotaUsedLabel($guser),
						'used_bytes' => $this->storageUsedMap()[$guser->getUID()] ?? 0,
						'isadmin' => $this->groupManager->isAdmin($guser->getUID()),
						'status' => $status,
					];
				}
                $groupList[] = [
                    'gid' => $group->getGID(),
                    'guserscount' => count($gusers),
                    'guser' => $guserList,
                ];
            }
            $adminGroup = $this->groupManager->displayNamesInGroup('admin');
            return new DataResponse([
                'userCount' => count($userList),
                'groupCount' => count($groupList),
                'users' => $userList,
                'groups' => $groupList,
                'adminCount' => count($adminGroup),
                'admins' => $adminGroup,
                'grlist' => $grlist,
                'usrlist' => $usrlist,
            ]);

        } catch (\Throwable $e) {
            $this->logger->error(
                'NcTower: FATAL ERROR or EXCEPTION in UserController->usercount: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
                ['app' => 'nc_tower']
            );
            return new DataResponse([
                'userCount' => -1,
                'groupCount' => -1,
				'error' => $e->getMessage(),
            ], 500);
        }
    }

	/** Avoid IL10N datetime on epoch 0 (never logged in). */
	private function formatLoginTs(int $ts): string {
		if ($ts <= 0) {
			return '—';
		}
		return (string) $this->l->l('datetime', $ts);
	}

	/** @var array<string,int>|null uid => bytes used, loaded once per request */
	private ?array $storageUsed = null;

	/**
	 * Bytes used per user, read straight from the file cache.
	 *
	 * The previous implementation asked for IUser::getQuotaUsage(), which does
	 * not exist on Nextcloud 31–34, so every account fell through to a dash —
	 * including the ones holding hundreds of gigabytes. The size of each user's
	 * `files` folder is already maintained in oc_filecache, so a single join
	 * gets every account at once (126 rows in ~1 ms here) without setting up a
	 * filesystem per user, which is what made 1.4.1 hang.
	 *
	 * @return array<string,int> uid => bytes
	 */
	private function storageUsedMap(): array {
		if ($this->storageUsed !== null) {
			return $this->storageUsed;
		}
		$map = [];
		try {
			$db = \OCP\Server::get(\OCP\IDBConnection::class);
			$query = $db->getQueryBuilder();
			$query->select('s.id', 'f.size')
				->from('filecache', 'f')
				->innerJoin('f', 'storages', 's', 'f.storage = s.numeric_id')
				->where($query->expr()->eq('f.path', $query->createNamedParameter('files')))
				->andWhere($query->expr()->like('s.id', $query->createNamedParameter('home::%')));
			$result = $query->executeQuery();
			foreach ($result->fetchAll() as $row) {
				$uid = substr((string) $row['id'], strlen('home::'));
				$size = (int) $row['size'];
				if ($uid !== '' && $size >= 0) {
					$map[$uid] = $size;
				}
			}
			$result->closeCursor();
		} catch (\Throwable $e) {
			$this->logger->warning('NcTower: storage usage lookup failed: ' . $e->getMessage(), ['app' => 'nc_tower']);
		}
		$this->storageUsed = $map;
		return $map;
	}

	/** Fast quota label — no filesystem walk. */
	private function quotaUsedLabel(\OCP\IUser $user): string {
		$used = $this->storageUsedMap()[$user->getUID()] ?? null;
		return $used === null ? '—' : $this->myService->formatBytes($used);
	}
    
    public function deleteuser($who) {
        try {
            if ($this->userManager->userExists($who)) { 
                 $user = $this->userManager->get($who);
                 if ($user->delete()) {
                     $this->logger->info("NcTower: User $who successful deleted");
                     return 'true';
                }
                 else { return 'false'; }               
            }
            else { 
                return 'false';
            }
        } catch (\Throwable $e) {
            $this->logger->error(
                'NcTower: FATAL ERROR or EXCEPTION in DataController->deletegroup: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
                ['app' => 'nc_tower']
            );
            return 'false';
        }
    }
    
    public function edituser($who): DataResponse {
        try {
            $user =$this->userManager->get($who);
            $mids = $user->getManagerUids();
            if($mids) $mids = $mids[0];
            else $mids = "";
            $userList = [];
                $userList[] = [
                    'uid' => $who,
                    'displayname' => $user->getDisplayName(),
                    'email' => $user->getEMailAddress(),
                    'quota' => $user->getQuota(),
                    'managerids' => $mids,
                    'isadmin' => $this->groupManager->isAdmin($user->getUID()),
                    'groups' => $this->groupManager->getUserGroupIds($user),
                    'admingroups' => $this->myService->admingroup($who),
                    'lastlogin' => $user->getLastLogin(),
                    'firstlogin' => $user->getFirstLogin(),
                    'used' => $this->quotaUsedLabel($user),
                    'used_bytes' => $this->storageUsedMap()[$user->getUID()] ?? 0,
                    'status' => true,
                ];
            
            return new DataResponse([
                'user' => $userList,
            ]);

        } catch (\Throwable $e) {
            $this->logger->error(
                'NcTower: FATAL ERROR or EXCEPTION in DataController->edituser: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
                ['app' => 'nc_tower']
            );
            return new DataResponse([
                'user' => -1,
            ], 500);
        }
    }
    
    public function saveuser($uid, $displayname, $password, $email, $groups, $admingroups, $quota, $managerids): JSONResponse {
        if($quota === $this->l->t('default quota')) $uquota = $this->appConfig->getValueString('files', 'default_quota', '1 GB', false);
        elseif($quota === $this->l->t('unlimited')) $uquota = "none";
        else $uquota = $quota;
        $user =$this->userManager->get($uid);
        $oldgroups = $this->groupManager->getUserGroupIds($user);
        $oldadmingroups = $this->myService->admingroup($uid);
        
        if ($user->getDisplayName() <> $displayname) $user->setDisplayName($displayname);
        if ($password) {
            if($user->setPassword($password, null)) $this->logger->error('NcTower: Success in DataController->setPassword: ');
            else $this->logger->error('NcTower: Fail in DataController->setPassword: ');
        }
        if ($user->getEMailAddress() <> $email) $user->setEMailAddress($email);
        if ($oldgroups <> $groups) {
                $missingElements = array_diff($oldgroups, $groups);
                $newElements = array_diff($groups, $oldgroups);
                foreach ($newElements as $x) {
                        $this->groupManager->get($x)->addUser($user);
                }
                foreach ($missingElements as $x) {
                        $this->groupManager->get($x)->removeUser($user);
                }            
        }
        if ($oldadmingroups <> $admingroups) {
                $missingElements = array_diff($oldadmingroups, $admingroups);
                $newElements = array_diff($admingroups, $oldadmingroups);
                foreach ($newElements as $x) {
                        $this->myService->addadmingroup($uid, $x);
                }
                foreach ($missingElements as $x) {
                        $this->myService->deleteadmingroup($uid, $x);
                }                
        }
        if ($user->getQuota() <> $quota) {
            $user->setQuota($uquota);
        }
        if ($user->getManagerUids() <> $managerids) {
            $usrmid = [];
            $usrmid[] = $managerids;
            $user->setManagerUids($usrmid);
        }
        return new JSONResponse([
         'uid' => $uid,
         'displayname' => $displayname,
         'password' => $password,
        'email' => $email,
        'groups' => $groups,
        'admingroups' => $admingroups,
        'quota' => $quota,
        'managerids' => $managerids,
        'status' => true,
		   ]);
        
        try {
            if ($this->groupManager->groupExists($who)) { return 'false'; }
            else { 
                $this->groupManager->createGroup($who);
                return 'true';
            }
        } catch (\Throwable $e) {
            $this->logger->error(
                'NcTower: FATAL ERROR or EXCEPTION in DataController->addgroup: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
                ['app' => 'nc_tower']
            );
            return 'false';
        }
    }
    
    public function userexists($who) {
            if($this->userManager->get($who)) return true;
            else return false;
    }
    
    public function newuser($uid, $displayname, $password, $email, $groups, $admingroups, $quota, $managerids): DataResponse {
        try {
            $this->userManager->createUser($uid, $password);
            $this->saveuser($uid, $displayname, $password, $email, $groups, $admingroups, $quota, $managerids);
            $userList = [];
                $userList[] = [
                    'uid' => $uid,
                    'displayname' => '',
                    'email' => '',
                    'quota' => '',
                    'managerids' => '',
                    'isadmin' => '',
                ];

                $this->logger->info("NcTower: User $uid successful created");
            
            return new DataResponse([
                'user' => $userList,
            ]);

        } catch (\Throwable $e) {
            $this->logger->error(
                'NcTower: FATAL ERROR or EXCEPTION in DataController->newuser: ' . $e->getMessage() . "\n" . $e->getTraceAsString(),
                ['app' => 'nc_tower']
            );
            return new DataResponse([
                'user' => -1,
            ], 500);
        }
    }
    
    public function setuser($who) {
        return;
    }
    
    public function notifyuser() {
$rawData = file_get_contents('php://input');

$data = json_decode($rawData, true);
if (json_last_error() === JSON_ERROR_NONE) {
    $message = $data['what'] ?? '';
    $who = $data['who'] ?? '';
        $para = [
            'message' => $message,
            'von' => $this->userSession->getUser()->getUID(),
        ];
        $nmanager = \OCP\Server::get(\OCP\Notification\IManager::class);
        $notification = $nmanager->createNotification();

        $notification->setApp('nc_tower')
            ->setUser($who)
            ->setDateTime(new \DateTime())
            ->setObject('remote', '2311') // $type and $id
            ->setSubject('abc', $para) // $subject and $parameters
        ;
        $nmanager->notify($notification);
        return 'true';
        } else {
    http_response_code(400);
    echo json_encode(['status' => 'error', 'message' => 'Invalid JSON']);
}
        
    }
    
    public function notifygroup() {
$rawData = file_get_contents('php://input');

$data = json_decode($rawData, true);
if (json_last_error() === JSON_ERROR_NONE) {
    $message = $data['what'] ?? '';
    $who = $data['who'] ?? '';
        $para = [
            'message' => $message,
            'von' => $this->userSession->getUser()->getUID(),
        ];
        $group = $this->groupManager->get($who);
        $groupusers = $group->getUsers();
        //return 'true';
        $nmanager = \OCP\Server::get(\OCP\Notification\IManager::class);
        foreach ($groupusers as $groupuser) {
            $notification = $nmanager->createNotification();
            $notification->setApp('nc_tower')
            ->setUser($groupuser->getUID())
            ->setDateTime(new \DateTime())
            ->setObject('remote', '2311') // $type and $id
            ->setSubject('abc', $para) // $subject and $parameters
        ;
        $nmanager->notify($notification);
        $notification = $nmanager->createNotification();
        }
        

        
        return 'true';
        } else {
    http_response_code(400);
    echo json_encode(['status' => 'error', 'message' => 'Invalid JSON']);
}
        
    }
  
}
