<?php

declare(strict_types=1);

namespace OCA\NcTower\AppInfo;

use OCP\AppFramework\App;
use OCP\App\IAppManager;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\INavigationManager;
use OCP\IConfig;
use OCP\IURLGenerator;
use OCA\NcTower\Dashboard\NcTowerWidget;

class Application extends App implements IBootstrap {
	public const APP_ID = 'nc_tower';

	public function __construct(array $urlParams = []) {
		parent::__construct(self::APP_ID, $urlParams);
	}

	public function register(IRegistrationContext $context): void {
		$context->registerNotifierService(\OCA\NcTower\Notification\Notifier::class);
		$context->registerDashboardWidget(NcTowerWidget::class);
	}

	public function boot(IBootContext $context): void {
		try {
			$context->injectFn($this->registerAppsManagementNavigation(...));
		} catch (\Throwable) {
		}
	}

	private function registerAppsManagementNavigation(IConfig $config, IAppManager $appManager): void {
		$container = $this->getContainer();
		$appManager->enableAppForGroups(self::APP_ID, ['admin'], false);
		$container->get(INavigationManager::class)->add(function () use ($container) {
			$urlGenerator = $container->get(IURLGenerator::class);
			return [
				'id' => self::APP_ID,
				'order' => 1000,
				'href' => $urlGenerator->linkToRoute(self::APP_ID . '.page.index'),
				'icon' => $urlGenerator->imagePath(self::APP_ID, 'app.svg'),
				'name' => 'NC Tower',
			];
		});
	}
}
