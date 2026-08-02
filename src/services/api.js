import axios from '@nextcloud/axios'
import { generateUrl } from '@nextcloud/router'

// @nextcloud/axios attaches the requesttoken header, so POSTs satisfy the
// CSRF check that every Tower mutator route relies on.

const BASE = '/apps/nc_tower'

/**
 * Turn an axios failure into a message worth showing an operator.
 *
 * The sidecar proxy answers with {error, detail, http} on failure; a bare
 * "Request failed with status code 502" tells nobody anything.
 *
 * @param {Error} error axios error
 * @return {Error} error with a useful message and the payload attached
 */
function normalise(error) {
	const data = error?.response?.data || {}
	const status = error?.response?.status
	const message = data.error || data.detail || error?.message || 'request failed'
	const wrapped = new Error(status ? `${message} (HTTP ${status})` : message)
	wrapped.status = status
	wrapped.data = data
	return wrapped
}

/**
 * @param {string} path route below /apps/nc_tower
 * @param {object} [params] query params
 * @return {Promise<object>} response body
 */
export async function get(path, params) {
	try {
		const { data } = await axios.get(generateUrl(BASE + path), { params })
		return data
	} catch (error) {
		throw normalise(error)
	}
}

/**
 * @param {string} path route below /apps/nc_tower
 * @param {object} [body] JSON body
 * @return {Promise<object>} response body
 */
export async function post(path, body) {
	try {
		const { data } = await axios.post(generateUrl(BASE + path), body || {})
		return data
	} catch (error) {
		throw normalise(error)
	}
}

export default { get, post }
