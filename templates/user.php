<?php

declare(strict_types=1);

use OCP\Util;

Util::addScript(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-user');
Util::addStyle(OCA\NcTower\AppInfo\Application::APP_ID, 'nc_tower-main');
?>

<div id="nc_tower"></div>
