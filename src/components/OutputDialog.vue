<template>
	<NcDialog :open="open" :name="title" size="large" @update:open="$emit('close')">
		<div class="nc-tower-output__bar">
			<slot name="bar" />
			<span class="nc-tower-output__spacer" />
			<NcButton type="tertiary" @click="copy">Copy</NcButton>
		</div>
		<pre ref="body" class="nc-tower-output__body" :class="{ 'is-wrapped': wrap }">{{ text || '(empty)' }}</pre>
	</NcDialog>
</template>

<script>
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcDialog from '@nextcloud/vue/dist/Components/NcDialog.js'

/** Shared shell for logs, inspect JSON and exec output. */
export default {
	name: 'OutputDialog',
	components: { NcButton, NcDialog },
	props: {
		open: {
			type: Boolean,
			default: false,
		},
		title: {
			type: String,
			default: '',
		},
		text: {
			type: String,
			default: '',
		},
		wrap: {
			type: Boolean,
			default: true,
		},
		follow: {
			type: Boolean,
			default: false,
		},
	},
	watch: {
		text() {
			if (this.follow) {
				this.$nextTick(this.scrollToEnd)
			}
		},
	},
	methods: {
		scrollToEnd() {
			const body = this.$refs.body
			if (body) {
				body.scrollTop = body.scrollHeight
			}
		},
		async copy() {
			try {
				await navigator.clipboard.writeText(this.text || '')
				this.$emit('copied')
			} catch (error) {
				this.$emit('copy-failed', error)
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-output {
	&__bar {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
		margin-bottom: 8px;
	}

	&__spacer {
		flex: 1 1 auto;
	}

	&__body {
		margin: 0;
		max-height: 60vh;
		overflow: auto;
		font-family: var(--font-face-monospace, monospace);
		font-size: 0.8em;
		line-height: 1.45;
		background: var(--color-background-dark);
		border-radius: var(--border-radius, 4px);
		padding: 10px;
		white-space: pre;

		&.is-wrapped {
			white-space: pre-wrap;
			overflow-wrap: anywhere;
		}
	}
}
</style>
