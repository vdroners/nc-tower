/**
 * Tiered polling.
 *
 * 1.8 refreshed all thirteen Ops sections on one 12 s tick, which re-ran a
 * five-disk `smartctl -a` sweep every twelve seconds and rebuilt every table
 * from scratch. Each task now carries its own interval, nothing polls while
 * the tab is hidden, and a hidden tab catches up once on return.
 */
export default class Poller {

	constructor() {
		this.tasks = new Map()
		this.timers = new Map()
		this.running = false
		this.onVisibility = this.handleVisibility.bind(this)
	}

	/**
	 * @param {string} name task id
	 * @param {Function} fn async loader
	 * @param {number} intervalMs how often to repeat
	 */
	add(name, fn, intervalMs) {
		this.tasks.set(name, { fn, intervalMs })
	}

	/** Run every task once, then schedule each on its own interval. */
	start() {
		this.running = true
		document.addEventListener('visibilitychange', this.onVisibility)
		for (const name of this.tasks.keys()) {
			this.run(name)
			this.schedule(name)
		}
	}

	stop() {
		this.running = false
		document.removeEventListener('visibilitychange', this.onVisibility)
		for (const timer of this.timers.values()) {
			clearInterval(timer)
		}
		this.timers.clear()
	}

	/**
	 * @param {string} [name] task to refresh; omit for all
	 * @return {Promise<void>} resolves once the run(s) settle
	 */
	async refresh(name) {
		const names = name ? [name] : [...this.tasks.keys()]
		await Promise.all(names.map((key) => this.run(key)))
	}

	/**
	 * @param {string} name task id
	 * @return {Promise<void>} resolves when the loader settles
	 */
	async run(name) {
		const task = this.tasks.get(name)
		if (!task) {
			return
		}
		try {
			await task.fn()
		} catch (error) {
			// Loaders own their error state; never let one poisoned task
			// tear down the interval for every other section.
			console.error(`[nc_tower] poll ${name}`, error)
		}
	}

	/**
	 * @param {string} name task id
	 */
	schedule(name) {
		const task = this.tasks.get(name)
		if (!task || this.timers.has(name)) {
			return
		}
		this.timers.set(name, setInterval(() => {
			if (document.visibilityState !== 'hidden') {
				this.run(name)
			}
		}, task.intervalMs))
	}

	handleVisibility() {
		if (document.visibilityState === 'visible' && this.running) {
			this.refresh()
		}
	}

}
