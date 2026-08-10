<?php
/**
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * NC Tower — Nextcloud admin orchestrator (vdroners / 19labs).
 * See CREDITS.md for heritage notes.
 */

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\IL10N;
use OCP\IConfig;
use OCP\AppFramework\Db\TTransactional;
use OCP\IDBConnection;

// Helper is a plain service, not a routed controller. The route/CSRF attributes
// that used to sit on its constructor were inert noise — and #[FrontpageRoute]
// there was a phantom POST-/ route waiting to be scanned into existence.
class Helper
{
    use TTransactional;

    private IDBConnection $db;
    private IConfig $config;
    private $appName;
    private $l;

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
