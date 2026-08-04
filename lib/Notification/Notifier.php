<?php
/**
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * NC Tower — Nextcloud admin orchestrator (vdroners / 19labs).
 * See CREDITS.md for heritage notes.
 *
declare(strict_types=1);

namespace OCA\NcTower\Notification;

use OCA\NcTower\AppInfo\Application;
use OCP\IURLGenerator;
use OCP\L10N\IFactory;
use OCP\Notification\INotification;
use OCP\Notification\INotifier;
use OCP\Notification\UnknownNotificationException;

use OCP\IUserSession;

class Notifier implements INotifier {
	private IFactory $factory;
	private IURLGenerator $url;
	private IUserSession $userSession;

	public function __construct(\OCP\L10N\IFactory $factory,
								\OCP\IURLGenerator $urlGenerator,
								IUserSession $userSession,) {
		$this->factory = $factory;
		$this->url = $urlGenerator;
		$this->userSession = $userSession;
	}

	/**
	 * Identifier of the notifier, only use [a-z0-9_]
	 * @return string
	 */
	public function getID(): string {
		return 'nc_tower';
	}

	/**
	 * Human-readable name describing the notifier
	 * @return string
	 */
	public function getName(): string {
		return $this->factory->get('nc_tower')->t('nc_tower');
	}

	/**
	 * @param INotification $notification
	 * @param string $languageCode The code of the language that should be used to prepare the notification
	 */
	public function prepare(INotification $notification, string $languageCode): INotification {
		if ($notification->getApp() !== 'nc_tower') {
			// Not my app => throw
			throw new \OCP\Notification\UnknownNotificationException();
		}
		
		$lang = $this->factory->getUserLanguage($this->userSession->getUser());
        $l = $this->factory->get('nc_tower', $lang);
        
        switch ($notification->getSubject()) {
			case 'abc':
				$parameters = $notification->getSubjectParameters();
				$message = $parameters['message'];
                $von = $parameters['von'];
				$notification->setParsedSubject($l->t('message from %1$s', [$von]))
					->setIcon($this->url->getAbsoluteURL($this->url->imagePath('nc_tower', 'app-dark.svg')))
                    ->setParsedMessage($message);

				$action = $notification->createAction();
				$towerUrl = $this->url->linkToRouteAbsolute('nc_tower.page.index');
				$action->setParsedLabel($l->t('Read more'))
					->setLink($towerUrl, 'WEB')
					->setPrimary(true);
				$notification->setLink($towerUrl);
				$notification->addParsedAction($action);

				return $notification;

			default:
				throw new UnknownNotificationException();
		}
	}

	/**
	 * This is a little helper function which automatically sets the simple parsed subject
	 * based on the rich subject you set. This is also the default behaviour of the API
	 * since Nextcloud 26, but in case you would like to return simpler or other strings,
	 * this function allows you to take over.
	 *
	 * @param INotification $notification
	 */
	protected function setParsedSubjectFromRichSubject(INotification $notification): void {
		$placeholders = $replacements = [];
		foreach ($notification->getRichSubjectParameters() as $placeholder => $parameter) {
			$placeholders[] = '{' . $placeholder . '}';
			if ($parameter['type'] === 'file') {
				$replacements[] = $parameter['path'];
			} else {
				$replacements[] = $parameter['name'];
			}
		}

		$notification->setParsedSubject(str_replace($placeholders, $replacements, $notification->getRichSubject()));
	}
}
