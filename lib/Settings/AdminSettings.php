<?php

declare(strict_types=1);

namespace OCA\NcTower\Settings;

use OCA\NcTower\AppInfo\Application;
use OCA\NcTower\Service\EndpointConfigService;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\IURLGenerator;
use OCP\Settings\ISettings;

class AdminSettings implements ISettings {
	public function __construct(
		private EndpointConfigService $endpoints,
		private IURLGenerator $urlGenerator,
	) {
	}

	public function getForm(): TemplateResponse {
		$settings = $this->endpoints->allSettings();
		$toolDefs = [];
		foreach (EndpointConfigService::TOOL_DEFS as $def) {
			$toolDefs[] = [
				'key' => $def['key'],
				'title' => $def['title'],
				'group' => $def['group'],
				'value' => $settings[$def['key']] ?? '',
			];
		}

		return new TemplateResponse(Application::APP_ID, 'admin_settings', [
			'sidecar_url' => $settings[EndpointConfigService::KEY_SIDECAR_URL] ?? EndpointConfigService::DEFAULT_SIDECAR_URL,
			'tool_defs' => $toolDefs,
			'save_url' => $this->urlGenerator->linkToRoute('nc_tower.admin.saveSettings'),
		]);
	}

	public function getSection(): string {
		return Application::APP_ID;
	}

	public function getPriority(): int {
		return 10;
	}
}
