<?php
/**
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * NC Tower — Nextcloud admin orchestrator (vdroners / 19labs).
 * See CREDITS.md for heritage notes.
 */

declare(strict_types=1);

namespace OCA\NcTower\Dashboard;

use OCA\NcTower\AppInfo\Application;
use OCP\Dashboard\IWidget;
use OCP\Dashboard\IConditionalWidget;
use OCP\IConfig;
use OCP\IL10N;
use OCP\IURLGenerator;
use OCP\Util;
use OCP\IUserSession;
use OCP\IGroupManager;

#[\AllowDynamicProperties]
class NcTowerWidget implements IWidget, IConditionalWidget
{
  public function __construct(private IL10N $l10n,
  private IURLGenerator $url,
  private IConfig $config,
  IUserSession $userSession,
  IGroupManager $groupManager,
) {
  $user = $userSession->getUser();
  $this->wtisadmin = $groupManager->isAdmin($user->getUID());
}

public function isEnabled(): bool {
  return $this->wtisadmin ? true : false;
}

/**
 * @inheritDoc
 */
public function getId(): string {
  return 'nc_tower-widget';
}

/**
 * @inheritDoc
 */
public function getTitle(): string {
  return $this->l10n->t('NC Tower');
}

/**
 * @inheritDoc
 */
public function getOrder(): int {
  return 10;
}

/**
 * @inheritDoc
 */
public function getIconClass(): string {
  return 'icon-nc_tower';
}

/**
 * @inheritDoc
 */
public function getUrl(): ?string {
  return $this->url->linkToRouteAbsolute('nc_tower.page.ops');
}

    public function load(): void
    {
        Util::addScript('nc_tower', 'nc_tower-widget');
    }
}
