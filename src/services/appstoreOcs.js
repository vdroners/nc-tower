import axios from '@nextcloud/axios'
import { generateOcsUrl } from '@nextcloud/router'

/**
 * Client-side App Store listing/update via the shipped `appstore` OCS API.
 * Tower PHP stays OCP-only (no OC\Installer).
 */

const OCS_HEADERS = { 'OCS-APIRequest': 'true' }

/**
 * Prompt for password when NC requires confirmation for store mutations.
 *
 * @return {Promise<void>}
 */
function confirmPassword() {
	return new Promise((resolve, reject) => {
		const api = typeof window !== 'undefined' ? window.OC?.PasswordConfirmation : null
		if (!api?.requirePasswordConfirmation) {
			resolve()
			return
		}
		if (typeof api.requiresPasswordConfirmation === 'function' && !api.requiresPasswordConfirmation()) {
			resolve()
			return
		}
		api.requirePasswordConfirmation(resolve, {}, reject)
	})
}

/**
 * @param {Error} error axios error
 * @return {Error}
 */
function normalise(error) {
	const data = error?.response?.data || {}
	const ocs = data.ocs?.meta || {}
	const status = error?.response?.status
	const message = ocs.message || data.message || data.error || error?.message || 'appstore request failed'
	const wrapped = new Error(status ? `${message} (HTTP ${status})` : message)
	wrapped.status = status
	wrapped.data = data
	return wrapped
}

/**
 * @return {Promise<object[]>} installed apps from appstore OCS
 */
export async function listApps() {
	try {
		const { data } = await axios.get(generateOcsUrl('/apps/appstore/api/v1/apps'), {
			headers: OCS_HEADERS,
		})
		const rows = data?.ocs?.data
		return Array.isArray(rows) ? rows : []
	} catch (error) {
		throw normalise(error)
	}
}

/**
 * Apps that have a non-empty `update` version string from the store.
 *
 * @return {Promise<{available: boolean, apps: object[], appscount: number, message?: string}>}
 */
export async function listAppUpdates() {
	const apps = await listApps()
	const pending = apps
		.filter((app) => app && app.update)
		.map((app) => ({
			id: app.id,
			appid: app.id,
			name: typeof app.name === 'string' ? app.name : (app.id || ''),
			version: app.version || '',
			updateVersion: app.update,
			icon: app.preview || app.icon || '',
			update: app.update,
		}))
	return {
		available: true,
		apps: pending,
		appscount: pending.length,
	}
}

/**
 * @param {string} appId
 * @return {Promise<object>} OCS data payload
 */
export async function updateApp(appId) {
	await confirmPassword()
	try {
		const { data } = await axios.post(
			generateOcsUrl('/apps/appstore/api/v1/apps/update'),
			{ appId },
			{ headers: OCS_HEADERS },
		)
		const meta = data?.ocs?.meta
		if (meta && meta.statuscode >= 400) {
			throw new Error(meta.message || 'update failed')
		}
		return data?.ocs?.data ?? {}
	} catch (error) {
		throw normalise(error)
	}
}

export default { listApps, listAppUpdates, updateApp }
