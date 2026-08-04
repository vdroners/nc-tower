<template>
	<div class="nc-tower-fan-panel">
		<NcNoteCard v-for="(warn, idx) in warnings" :key="`w-${idx}`" type="warning">
			{{ warn }}
		</NcNoteCard>
		<NcNoteCard v-if="error" type="error">{{ error }}</NcNoteCard>

		<div class="nc-tower-toolbar nc-tower-fan-panel__profiles">
			<span class="nc-tower-muted">Profile</span>
			<NcButton v-for="name in profiles"
				:key="name"
				:type="activeProfile === name ? 'primary' : 'secondary'"
				:disabled="busy"
				@click="applyProfile(name)">
				{{ name }}
				<span v-if="activeProfile === name" class="nc-tower-fan-panel__badge">active</span>
			</NcButton>
			<span class="nc-tower-fan-panel__spacer" />
			<NcButton type="tertiary" :disabled="busy" @click="mutateChassis('restore-bios-defaults')">
				Restore BIOS defaults
			</NcButton>
			<NcButton type="tertiary" :disabled="busy" @click="mutateChassis('re-apply')">
				Apply saved state
			</NcButton>
		</div>

		<div class="nc-tower-fan-panel__grid">
			<div v-for="fan in chassisFans" :key="fan.index" class="nc-tower-fan-card">
				<div class="nc-tower-fan-card__head">
					<strong>{{ fan.header || fan.name || `FAN${fan.index}` }}</strong>
					<span class="nc-tower-chip">{{ fan.role || 'unused' }}</span>
					<span v-if="fan.fancontrol_managed" class="nc-tower-chip nc-tower-chip--warn">fancontrol</span>
				</div>
				<div class="nc-tower-chips">
					<span class="nc-tower-chip">{{ fan.rpm != null ? `${fan.rpm} RPM` : '— RPM' }}</span>
					<span class="nc-tower-chip">{{ pwmLabel(fan) }}</span>
					<span class="nc-tower-chip">{{ fan.mode_label || modeLabel(fan.mode) }}</span>
				</div>

				<template v-if="fan.role === 'pump'">
					<p class="nc-tower-muted">
						Pump locked at 100% manual — Tower refuses PWM/mode changes for safety.
					</p>
				</template>
				<template v-else>
					<label class="nc-tower-fan-card__field">
						<span class="nc-tower-muted">Mode</span>
						<select class="nc-tower-fan-card__select"
							:value="fan.mode"
							:disabled="busy"
							@change="onModeChange(fan, $event)">
							<option v-for="opt in modeOptions" :key="opt.value" :value="opt.value">
								{{ opt.label }}
							</option>
						</select>
					</label>
					<label class="nc-tower-fan-card__field">
						<span class="nc-tower-muted">Manual PWM {{ draftPct[fan.index] ?? Math.round(fan.pwm_pct || 0) }}%</span>
						<input class="nc-tower-fan-card__slider"
							type="range"
							min="0"
							max="100"
							step="1"
							:value="draftPct[fan.index] ?? Math.round(fan.pwm_pct || 0)"
							:disabled="busy || Number(fan.mode) !== 1"
							@input="onPctInput(fan, $event)"
							@change="onPctCommit(fan, $event)" />
					</label>
				</template>
			</div>
		</div>
		<p v-if="!chassisFans.length && !loading" class="nc-tower-muted">No chassis fans detected.</p>

		<FanCharts :history="historySamples"
			:fans="chassisFans"
			:temps="chassisTemps"
			:window-minutes.sync="historyMinutes" />

		<h4 class="nc-tower-subhead">GPU fans</h4>
		<NcNoteCard v-if="gpuFan.unavailable" type="warning">
			GPU fan control unavailable: {{ gpuFan.reason }}
		</NcNoteCard>
		<template v-else>
			<div class="nc-tower-toolbar">
				<NcTextField :value.sync="gpuAllSpeed"
					type="number"
					label="All GPU fans %"
					:label-visible="true" />
				<NcButton type="secondary" :disabled="busy" @click="mutateGpu('set-all-speeds')">Set all</NcButton>
				<NcButton type="tertiary" :disabled="busy" @click="mutateGpu('set-auto')">Set auto</NcButton>
			</div>
			<div v-if="gpuFanRows.length" class="nc-tower-fan-panel__gpu-rows">
				<div v-for="row in gpuFanRows" :key="row.index" class="nc-tower-fan-card nc-tower-fan-card--gpu">
					<span>{{ row.label }}</span>
					<span class="nc-tower-muted">{{ row.speedLabel }}</span>
					<div class="nc-tower-toolbar nc-tower-fan-panel__gpu-row-actions">
						<input v-model.number="gpuDraft[row.index]"
							class="nc-tower-fan-card__num"
							type="number"
							min="20"
							max="100"
							:disabled="busy" />
						<NcButton type="tertiary" :disabled="busy" @click="mutateGpu('set-speed', row.index)">
							Set speed
						</NcButton>
					</div>
				</div>
			</div>
		</template>

		<div class="nc-tower-toolbar nc-tower-fan-panel__systemd">
			<span class="nc-tower-chip"
				:class="fancontrolActive ? 'nc-tower-chip--warn' : 'nc-tower-chip--ok'">
				fancontrol.service {{ fancontrolActive ? 'active' : 'inactive' }}
			</span>
			<NcButton type="secondary" :disabled="busy" @click="restartFancontrol">
				Restart fancontrol
			</NcButton>
		</div>
	</div>
</template>

<script>
import { showError, showSuccess } from '@nextcloud/dialogs'
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import NcTextField from '@nextcloud/vue/dist/Components/NcTextField.js'

import FanCharts from './FanCharts.vue'
import { get, post } from '../services/api.js'

const DEFAULT_PROFILES = ['silent', 'balanced', 'performance']

const MODE_OPTIONS = [
	{ value: 1, label: '1 Manual' },
	{ value: 2, label: '2 Thermal Cruise' },
	{ value: 5, label: '5 Automatic' },
]

const MODE_LABELS = {
	1: 'Manual',
	2: 'Thermal Cruise',
	5: 'Automatic (BIOS)',
}

/**
 * Chassis + GPU fan controls for Ops › Fans. Fetches its own data so the
 * Section can stay a thin shell; expose refresh() for the Section refresh
 * button and refreshAll.
 */
export default {
	name: 'FanPanel',
	components: { FanCharts, NcButton, NcNoteCard, NcTextField },
	data() {
		return {
			loading: false,
			busy: false,
			error: '',
			chassisFan: {},
			gpuFan: {},
			systemd: {},
			historySamples: [],
			historyMinutes: 60,
			draftPct: {},
			gpuAllSpeed: '40',
			gpuDraft: {},
			modeOptions: MODE_OPTIONS,
		}
	},
	computed: {
		chassisFans() {
			return this.chassisFan.fans || this.chassisFan.items || []
		},
		chassisTemps() {
			return this.chassisFan.temps || []
		},
		warnings() {
			return this.chassisFan.warnings || []
		},
		profiles() {
			const list = this.chassisFan.profiles
			return Array.isArray(list) && list.length ? list : DEFAULT_PROFILES
		},
		activeProfile() {
			return this.chassisFan.active_profile || null
		},
		fancontrolActive() {
			if (this.chassisFan.fancontrol_active != null) {
				return !!this.chassisFan.fancontrol_active
			}
			const unit = (this.systemd.units || []).find((u) => u.unit === 'fancontrol.service')
			return unit ? /active|running/i.test(String(unit.active || unit.sub || '')) : false
		},
		summary() {
			const n = this.chassisFans.length
			const gpu = this.gpuFan.unavailable ? 'GPU fan n/a' : 'GPU fan ok'
			const profile = this.activeProfile ? ` · ${this.activeProfile}` : ''
			return `${n} chassis fan(s) · ${gpu}${profile}`
		},
		gpuFanRows() {
			const status = this.gpuFan.status || this.gpuFan
			const fans = status.fans || status.Fans || []
			if (!Array.isArray(fans) || !fans.length) {
				return []
			}
			return fans.map((fan, index) => {
				const idx = fan.index != null ? fan.index : (fan.fan != null ? fan.fan : index)
				const speed = fan.speed ?? fan.fan_pct ?? fan.pct ?? null
				return {
					index: Number(idx),
					label: fan.name || fan.label || `GPU fan ${idx}`,
					speedLabel: speed != null ? `${speed}%` : '—',
				}
			})
		},
	},
	watch: {
		historyMinutes() {
			this.loadHistory()
		},
		summary: {
			immediate: true,
			handler(value) {
				this.$emit('summary', value)
			},
		},
		chassisFans(list) {
			const next = { ...this.draftPct }
			for (const fan of list || []) {
				if (next[fan.index] == null && fan.pwm_pct != null) {
					next[fan.index] = Math.round(fan.pwm_pct)
				}
			}
			this.draftPct = next
		},
		gpuFanRows(rows) {
			const next = { ...this.gpuDraft }
			for (const row of rows) {
				if (next[row.index] == null) {
					next[row.index] = 40
				}
			}
			this.gpuDraft = next
		},
	},
	created() {
		this.refresh()
	},
	methods: {
		pwmLabel(fan) {
			if (fan.pwm_pct != null) {
				return `${Number(fan.pwm_pct).toFixed(0)}% PWM`
			}
			if (fan.pwm != null) {
				return `${fan.pwm}/255`
			}
			return '— PWM'
		},
		modeLabel(mode) {
			return MODE_LABELS[mode] || (mode != null ? `mode ${mode}` : '—')
		},
		/**
		 * Reload chassis, GPU, history, and systemd fancontrol status.
		 * @return {Promise<void>}
		 */
		async refresh() {
			this.loading = true
			this.error = ''
			this.$emit('loading', true)
			try {
				const [chassis, gpu, history, systemd] = await Promise.all([
					get('/tower/chassis-fan'),
					get('/tower/fan').catch((err) => ({ unavailable: true, reason: err.message })),
					get('/tower/chassis-fan/history', { minutes: this.historyMinutes })
						.catch(() => ({ samples: [] })),
					get('/tower/systemd').catch(() => ({})),
				])
				this.chassisFan = chassis || {}
				this.gpuFan = gpu || {}
				this.historySamples = history.samples || []
				this.systemd = systemd || {}
			} catch (err) {
				this.error = err.message || 'Fan refresh failed'
				this.$emit('error', this.error)
				throw err
			} finally {
				this.loading = false
				this.$emit('loading', false)
			}
		},
		async loadHistory() {
			try {
				const history = await get('/tower/chassis-fan/history', { minutes: this.historyMinutes })
				this.historySamples = history.samples || []
			} catch (err) {
				showError(err.message)
			}
		},
		/**
		 * @param {string} op chassis-fan mutate op
		 * @param {object} [payload] extra body fields
		 * @return {Promise<void>}
		 */
		async mutateChassis(op, payload = {}) {
			this.busy = true
			try {
				const result = await post('/tower/chassis-fan', { op, ...payload })
				if (result && result.ok === true) {
					showSuccess(op === 'apply-profile'
						? `Profile ${payload.profile || ''} applied`
						: `Chassis fan: ${op}`)
				} else {
					showError(result?.error || result?.stderr || 'Chassis fan action failed')
				}
			} catch (err) {
				showError(err.message)
			} finally {
				this.busy = false
				await this.refresh().catch(() => {})
			}
		},
		applyProfile(name) {
			if (!window.confirm(`Apply chassis fan profile “${name}”?`)) {
				return
			}
			return this.mutateChassis('apply-profile', { profile: name })
		},
		onModeChange(fan, event) {
			const mode = Number(event.target.value)
			if (!Number.isFinite(mode)) {
				return
			}
			return this.mutateChassis('set-mode', { header: fan.index, mode })
		},
		onPctInput(fan, event) {
			const pct = Number(event.target.value)
			this.$set(this.draftPct, fan.index, pct)
		},
		onPctCommit(fan, event) {
			const pct = Number(event.target.value)
			this.$set(this.draftPct, fan.index, pct)
			if (Number(fan.mode) !== 1) {
				return
			}
			return this.mutateChassis('set-value', { header: fan.index, pct })
		},
		/**
		 * @param {string} op GPU fan op
		 * @param {number} [fanIndex]
		 * @return {Promise<void>}
		 */
		async mutateGpu(op, fanIndex) {
			this.busy = true
			try {
				let body
				if (op === 'set-auto') {
					body = { op }
				} else if (op === 'set-all-speeds') {
					body = { op, speed: Number(this.gpuAllSpeed) }
				} else {
					body = { op, fan: fanIndex, speed: Number(this.gpuDraft[fanIndex]) }
				}
				const result = await post('/tower/fan', body)
				if (result && result.ok === true) {
					showSuccess('GPU fan setting applied')
				} else {
					showError(result?.error || result?.stderr || 'GPU fan action failed')
				}
			} catch (err) {
				showError(err.message)
			} finally {
				this.busy = false
				await this.refresh().catch(() => {})
			}
		},
		async restartFancontrol() {
			if (!window.confirm('Restart fancontrol.service?')) {
				return
			}
			this.busy = true
			try {
				const result = await post('/tower/systemd/restart', { unit: 'fancontrol.service' })
				if (result && result.ok === true) {
					showSuccess('fancontrol.service restarted')
				} else {
					showError(result?.error || result?.stderr || 'Restart failed')
				}
			} catch (err) {
				showError(err.message)
			} finally {
				this.busy = false
				await this.refresh().catch(() => {})
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-fan-panel {
	display: flex;
	flex-direction: column;
	gap: 4px;
}

.nc-tower-fan-panel__profiles {
	max-width: none;
	align-items: center;
}

.nc-tower-fan-panel__badge {
	margin-inline-start: 6px;
	font-size: 0.75em;
	opacity: 0.9;
}

.nc-tower-fan-panel__spacer {
	flex: 1 1 8px;
}

.nc-tower-fan-panel__grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
	gap: 10px;
	margin: 8px 0;
}

.nc-tower-fan-card {
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
	padding: 10px 12px;
	background: var(--color-main-background);

	&__head {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
		margin-bottom: 6px;
	}

	&__field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin-top: 8px;
	}

	&__select,
	&__num {
		max-width: 100%;
		padding: 4px 8px;
		border: 1px solid var(--color-border);
		border-radius: var(--border-radius, 4px);
		background: var(--color-main-background);
		color: var(--color-main-text);
	}

	&__num {
		width: 72px;
	}

	&__slider {
		width: 100%;
	}

	&--gpu {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
	}
}

.nc-tower-fan-panel__gpu-rows {
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.nc-tower-fan-panel__gpu-row-actions {
	margin-bottom: 0;
	max-width: none;
}

.nc-tower-fan-panel__systemd {
	margin-top: 12px;
	max-width: none;
}

.nc-tower-toolbar {
	display: flex;
	align-items: flex-end;
	gap: 8px;
	flex-wrap: wrap;
	margin-bottom: 10px;
	max-width: 640px;
}

.nc-tower-chips {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
}

.nc-tower-chip {
	display: inline-flex;
	align-items: center;
	padding: 2px 8px;
	border-radius: var(--border-radius-pill, 999px);
	background: var(--color-background-dark);
	font-size: 0.85em;

	&--ok {
		color: var(--color-success);
	}

	&--warn {
		color: var(--color-warning);
	}
}

.nc-tower-subhead {
	margin: 16px 0 6px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.nc-tower-muted {
	color: var(--color-text-maxcontrast);
	font-size: 0.9em;
}
</style>
