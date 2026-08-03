<?php

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCA\NcTower\AppInfo\Application;
use OCA\NcTower\Service\EndpointConfigService;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\AdminRequired;
use OCP\AppFramework\Http\JSONResponse;
use OCP\IRequest;

class AdminController extends Controller {
	public function __construct(
		IRequest $request,
		private EndpointConfigService $endpoints,
	) {
		parent::__construct(Application::APP_ID, $request);
	}

	#[AdminRequired]
	public function saveSettings(): JSONResponse {
		$this->endpoints->saveFromRequest($this->request->getParams());
		return new JSONResponse([
			'ok' => true,
			'settings' => $this->endpoints->allSettings(),
		]);
	}
}
