import { get, post } from './api.js'

/**
 * Start a detached job and follow it to completion.
 *
 * The work runs under the host's systemd, so the only way to observe it is to
 * poll. Callers get the job object on every tick and can render progress.
 *
 * @param {string} kind job kind the sidecar allowlists
 * @param {object} body kind-specific parameters
 * @param {Function} onTick called with the job object on each poll
 * @return {Promise<object>} the final job object
 */
export async function runJob(kind, body, onTick) {
	const started = await post(`/tower/jobs/${kind}`, body || {})
	if (!started.id) {
		throw new Error(started.error || 'job did not start')
	}
	let job = { id: started.id, kind, status: 'running', log: '' }
	onTick?.(job)
	// Poll until systemd writes the exit code. No timeout here on purpose: an
	// apt upgrade can outlive the page, and the job list still shows it after.
	for (;;) {
		await new Promise((resolve) => setTimeout(resolve, 1500))
		try {
			job = await get(`/tower/jobs/${started.id}`)
		} catch (error) {
			job = { ...job, status: 'failed', exit: -1, log: `${job.log}\n${error.message}` }
			onTick?.(job)
			return job
		}
		onTick?.(job)
		if (job.status !== 'running') {
			return job
		}
	}
}

export default { runJob }
