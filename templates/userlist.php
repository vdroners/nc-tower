<?php

declare(strict_types=1);

use OCP\Util;

Util::addScript(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-user');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-main');
?>

<div id="admin-cockpit-setup"
     data-who="<?php p($_['who']); ?>"
     data-gid="<?php p($_['gid']); ?>"
     data-guser="<?php p($_['guser']); ?>">
</div>

<div id="nc_tower"></div>
