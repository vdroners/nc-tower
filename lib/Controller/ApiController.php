<?php

declare(strict_types=1);

namespace OCA\NcTower\Controller;

use OCP\AppFramework\Http;
use OCP\AppFramework\Http\Attribute\ApiRoute;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\OCSController;
use OCP\IConfig;
use OCP\IRequest;

/**
 * Control Tower API (admin-only by default).
 */
class ApiController extends OCSController {
	public function __construct(
		string $appName,
		IRequest $request,
		private IConfig $config,
	) {
		parent::__construct($appName, $request);
	}

	/**
	 * @return DataResponse<Http::STATUS_OK, array{app: string, version: string, message: string}, array{}>
	 */
	#[ApiRoute(verb: 'GET', url: '/api')]
	public function index(): DataResponse {
		$version = $this->config->getAppValue('nc_tower', 'installed_version', '1.4.0');
		return new DataResponse([
			'app' => 'nc_tower',
			'version' => $version,
			'message' => 'Control Tower',
		]);
	}
}
