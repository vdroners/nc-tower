<?php
/**
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * NC Tower — Nextcloud admin orchestrator (vdroners / 19labs).
 * See CREDITS.md for heritage notes.
 */

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\AppFramework\Http\Attribute\FrontpageRoute;
use OCP\AppFramework\Http\Attribute\NoAdminRequired;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\IL10N;
use OCP\IConfig;
use OCP\AppFramework\Db\TTransactional;
use OCP\IDBConnection;

class Helper
{
    use TTransactional;

    private IDBConnection $db;
    private IConfig $config;
    private $appName;
    private $l;
    #[NoCSRFRequired]
    #[FrontpageRoute(verb: 'POST', url: '/')]

   public function __construct(IConfig $config, IL10N $l, $appName, IDBConnection $db){
        $this->config = $config;
        $this->l = $l;
        $this->appName = $appName;
        $this->db = $db;
    }

    public function getAppValue($key) {
        return $this->config->getAppValue($this->appName, $key);
    }

    public function setAppValue($key, $value) {
        return $this->config->setAppValue($this->appName, $key, $value);
    }
}
