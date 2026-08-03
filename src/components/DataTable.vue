<template>
	<div class="nc-tower-table-wrap">
		<table class="nc-tower-table">
			<thead>
				<tr>
					<th v-for="col in columns"
						:key="col.key"
						:class="[`is-${col.align || 'start'}`, { 'is-sortable': col.sortable !== false }]"
						:style="col.width ? { width: col.width } : null"
						scope="col"
						:tabindex="col.sortable === false ? null : 0"
						:role="col.sortable === false ? null : 'button'"
						:aria-sort="sortKey === col.key ? (sortAsc ? 'ascending' : 'descending') : null"
						@click="col.sortable === false ? null : toggleSort(col.key)"
						@keydown.enter.prevent="col.sortable === false ? null : toggleSort(col.key)"
						@keydown.space.prevent="col.sortable === false ? null : toggleSort(col.key)">
						{{ col.label }}
						<NcTowerIcon v-if="sortKey === col.key"
							:name="sortAsc ? 'chevron-up' : 'chevron-down'"
							:size="14"
							class="nc-tower-table__caret" />
					</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="(row, index) in sorted" :key="rowKey ? row[rowKey] : index">
					<td v-for="col in columns"
						:key="col.key"
						:data-label="col.label"
						:class="[`is-${col.align || 'start'}`, { 'is-mono': col.mono }]">
						<slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
							{{ display(row[col.key]) }}
						</slot>
					</td>
				</tr>
				<tr v-if="!sorted.length">
					<td :colspan="columns.length" class="nc-tower-table__empty">{{ emptyText }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script>
import NcTowerIcon from './NcTowerIcon.vue'

/**
 * One markup, two layouts: a real table on desktop, and below 720 px each row
 * reflows into a stacked card with the column label rendered from data-label.
 * Duplicating the markup per breakpoint is what makes responsive tables rot.
 */
export default {
	name: 'DataTable',
	components: { NcTowerIcon },
	props: {
		columns: {
			type: Array,
			required: true,
		},
		rows: {
			type: Array,
			default: () => [],
		},
		rowKey: {
			type: String,
			default: '',
		},
		emptyText: {
			type: String,
			default: 'Nothing to show',
		},
		defaultSort: {
			type: String,
			default: '',
		},
		/** Start the default sort descending — "top N by CPU" is not ascending. */
		defaultDesc: {
			type: Boolean,
			default: false,
		},
	},
	data() {
		return {
			sortKey: this.defaultSort,
			sortAsc: !this.defaultDesc,
		}
	},
	computed: {
		sorted() {
			if (!this.sortKey) {
				return this.rows
			}
			// A column may sort on a companion field: "521.91 GB" and "66.59 MB"
			// do not compare as strings, so used sorts on used_bytes.
			const col = this.columns.find((c) => c.key === this.sortKey)
			const key = col?.sortBy || this.sortKey
			const direction = this.sortAsc ? 1 : -1
			return [...this.rows].sort((a, b) => {
				const left = a[key]
				const right = b[key]
				const bothNumeric = !Number.isNaN(parseFloat(left)) && !Number.isNaN(parseFloat(right))
				if (bothNumeric) {
					return (parseFloat(left) - parseFloat(right)) * direction
				}
				return String(left ?? '').localeCompare(String(right ?? '')) * direction
			})
		},
	},
	methods: {
		toggleSort(key) {
			if (this.sortKey === key) {
				this.sortAsc = !this.sortAsc
			} else {
				this.sortKey = key
				this.sortAsc = true
			}
		},
		display(value) {
			if (value == null || value === '') {
				return '—'
			}
			return value
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-table-wrap {
	overflow-x: auto;
}

.nc-tower-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 0.9em;

	th, td {
		text-align: start;
		padding: 6px 8px;
		border-bottom: 1px solid var(--color-border);
		vertical-align: middle;
	}

	th {
		position: sticky;
		top: 0;
		z-index: 1;
		background: var(--color-main-background);
		color: var(--color-text-maxcontrast);
		font-weight: 600;
		white-space: nowrap;

		&.is-sortable { cursor: pointer; }
		&.is-sortable:hover { color: var(--color-main-text); }
	}

	td.is-mono {
		font-family: var(--font-face-monospace, monospace);
		font-size: 0.92em;
	}

	.is-end { text-align: end; }
	.is-center { text-align: center; }

	&__caret {
		color: var(--color-text-maxcontrast);
	}

	&__empty {
		color: var(--color-text-maxcontrast);
		padding: 16px 8px;
	}
}

// Phone: every row becomes its own card, labels come from data-label.
@media (max-width: 720px) {
	.nc-tower-table {
		thead { display: none; }

		tr {
			display: block;
			margin-bottom: 10px;
			border: 1px solid var(--color-border);
			border-radius: var(--border-radius-large, 8px);
			padding: 4px 8px;
		}

		td {
			display: flex;
			justify-content: space-between;
			gap: 12px;
			border-bottom: none;
			padding: 4px 0;
			text-align: end;

			&::before {
				content: attr(data-label);
				color: var(--color-text-maxcontrast);
				font-weight: 600;
				text-align: start;
				flex: 0 0 40%;
			}
		}
	}
}
</style>
