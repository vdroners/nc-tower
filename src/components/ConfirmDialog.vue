<template>
	<NcDialog :open="open"
		:name="title"
		size="small"
		@update:open="$emit('cancel')">
		<p class="tower-confirm__message">{{ message }}</p>
		<NcNoteCard v-if="danger" type="warning">This cannot be undone.</NcNoteCard>
		<div v-if="phrase" class="tower-confirm__gate">
			<label :for="inputId">Type <code>{{ phrase }}</code> to confirm</label>
			<NcTextField :id="inputId"
				:value.sync="typed"
				:label="`Type ${phrase}`"
				:label-visible="false"
				@keydown.enter="submit" />
		</div>
		<template #actions>
			<NcButton type="tertiary" @click="$emit('cancel')">Cancel</NcButton>
			<NcButton :type="danger ? 'error' : 'primary'" :disabled="!satisfied" @click="submit">
				{{ confirmLabel }}
			</NcButton>
		</template>
	</NcDialog>
</template>

<script>
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcDialog from '@nextcloud/vue/dist/Components/NcDialog.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import NcTextField from '@nextcloud/vue/dist/Components/NcTextField.js'

/**
 * Replaces window.confirm() and prompt('Type RECREATE'). Same safety gate —
 * destructive actions still require the phrase typed out — but keyboard
 * accessible, themed, and usable on a phone, which prompt() is not.
 */
export default {
	name: 'ConfirmDialog',
	components: { NcButton, NcDialog, NcNoteCard, NcTextField },
	props: {
		open: {
			type: Boolean,
			default: false,
		},
		title: {
			type: String,
			default: 'Confirm',
		},
		message: {
			type: String,
			default: '',
		},
		confirmLabel: {
			type: String,
			default: 'Confirm',
		},
		/** When set, the operator must type this exact word to enable the button. */
		phrase: {
			type: String,
			default: '',
		},
		danger: {
			type: Boolean,
			default: false,
		},
	},
	data() {
		return { typed: '' }
	},
	computed: {
		inputId() {
			return `tower-confirm-${this._uid}`
		},
		satisfied() {
			return !this.phrase || this.typed.trim() === this.phrase
		},
	},
	watch: {
		open(value) {
			if (value) {
				this.typed = ''
			}
		},
	},
	methods: {
		submit() {
			if (this.satisfied) {
				this.$emit('confirm')
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.tower-confirm {
	&__message {
		margin: 0 0 10px;
		overflow-wrap: anywhere;
	}

	&__gate {
		margin-top: 12px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
}
</style>
