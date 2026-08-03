<template>
	<div v-if="job" class="nc-tower-job" :class="`nc-tower-job--${job.status}`">
		<div class="nc-tower-job__head">
			<NcLoadingIcon v-if="job.status === 'running'" :size="18" />
			<SeverityDot v-else :level="job.status === 'done' ? 'ok' : 'crit'" />
			<strong>{{ job.kind }}</strong>
			<span class="nc-tower-job__state">{{ stateLabel }}</span>
			<span class="nc-tower-job__spacer" />
			<NcButton type="tertiary" @click="$emit('dismiss')">Dismiss</NcButton>
		</div>
		<pre v-if="job.log" ref="log" class="nc-tower-job__log">{{ job.log }}</pre>
		<p v-else class="nc-tower-muted">Waiting for output…</p>
		<p v-if="job.status === 'running'" class="nc-tower-muted">
			This runs on the host under systemd, so it keeps going if you close this page.
		</p>
	</div>
</template>

<script>
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcLoadingIcon from '@nextcloud/vue/dist/Components/NcLoadingIcon.js'
import SeverityDot from './SeverityDot.vue'

/**
 * Progress and output for a detached job. The work is owned by the host's
 * systemd, not by this request, so the panel polls rather than waits — which is
 * the whole point: an apt upgrade restarts dockerd and would otherwise kill the
 * container serving the response.
 */
export default {
	name: 'JobPanel',
	components: { NcButton, NcLoadingIcon, SeverityDot },
	props: {
		job: {
			type: Object,
			default: null,
		},
	},
	computed: {
		stateLabel() {
			if (!this.job) {
				return ''
			}
			if (this.job.status === 'running') {
				return 'running on the host'
			}
			return this.job.status === 'done' ? 'finished' : `failed (exit ${this.job.exit})`
		},
	},
	watch: {
		'job.log'() {
			this.$nextTick(() => {
				const log = this.$refs.log
				if (log) {
					log.scrollTop = log.scrollHeight
				}
			})
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-job {
	border: 1px solid var(--color-border);
	border-inline-start: 4px solid var(--color-primary-element);
	border-radius: var(--border-radius-large, 8px);
	padding: 10px 12px;
	margin: 10px 0;

	&--done { border-inline-start-color: var(--color-success); }
	&--failed { border-inline-start-color: var(--color-error); }

	&__head {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}

	&__state { color: var(--color-text-maxcontrast); font-size: 0.9em; }
	&__spacer { flex: 1 1 auto; }

	&__log {
		margin: 8px 0 0;
		max-height: 260px;
		overflow: auto;
		font-family: var(--font-face-monospace, monospace);
		font-size: 0.78em;
		background: var(--color-background-dark);
		border-radius: var(--border-radius, 4px);
		padding: 8px;
		white-space: pre-wrap;
	}
}
</style>
