<?php

declare(strict_types=1);

namespace OCA\NcTower\Exception;

use Exception;

/**
 * Thrown when a caller is not an administrator. Mapped to HTTP 403 JSON by
 * ForbiddenMiddleware. Mirrors the estate pattern (nc-roomba/nc-gcs).
 */
class ForbiddenException extends Exception {
}
