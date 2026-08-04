<template>
	<div class="nc-tower-view">
		<StatusBanner :level="verdict.level"
			:count="verdict.items.length"
			:facts="facts"
			:updated="updatedAt"
			:busy="refreshingAll"
			@refresh="refreshAll" />

		<AttentionList :items="verdict.items" />

		<Section id="ops.containers"
			title="Containers"
			:summary="containerSummary"
			:severity="sev.containers"
			:loading="loading.containers"
			:error="errors.containers"
			default-open
			@refresh="refresh('containers')">
			<div class="nc-tower-toolbar">
				<NcTextField :value.sync="containerFilter"
					label="Filter containers"
					placeholder="Filter name, project, image, status…"
					trailing-button-icon="close"
					:show-trailing-button="containerFilter !== ''"
					@trailing-button-click="containerFilter = ''" />
			</div>
			<DataTable :columns="containerColumns"
				:rows="filteredContainers"
				row-key="name"
				default-sort="name"
				empty-text="No containers">
				<template #cell-status="{ row }">
					<span class="nc-tower-state" :class="`nc-tower-state--${row.status}`">{{ row.status }}</span>
				</template>
				<template #cell-cpu="{ row }">{{ row.cpu || '—' }}</template>
				<template #cell-trend="{ row }">
					<Sparkline :samples="trends[row.name] || []" :label="`${row.name} CPU`" :max="100" />
				</template>
				<template #cell-ports="{ row }">{{ fmt.ports(row.ports) }}</template>
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<span v-if="!row.mutable && !row.loggable" class="nc-tower-muted" :title="lockedHint">locked</span>
						<NcActions v-else :aria-label="`Actions for ${row.name}`">
							<NcActionButton v-if="row.loggable || row.mutable" @click="openLogs(row.name)">
									<template #icon><NcTowerIcon name="file-text" :size="18" /></template>
									Logs
								</NcActionButton>
							<NcActionButton v-if="row.loggable || row.mutable" @click="openInspect(row.name)">
									<template #icon><NcTowerIcon name="search" :size="18" /></template>
									Inspect
								</NcActionButton>
							<NcActionButton v-if="row.mutable" @click="ask('restart', row.name)">
									<template #icon><NcTowerIcon name="refresh" :size="18" /></template>
									Restart
								</NcActionButton>
							<NcActionButton v-if="row.mutable" @click="ask('stop', row.name)">
									<template #icon><NcTowerIcon name="stop" :size="18" /></template>
									Stop
								</NcActionButton>
							<NcActionButton v-if="row.mutable" @click="ask('start', row.name)">
									<template #icon><NcTowerIcon name="play" :size="18" /></template>
									Start
								</NcActionButton>
							<NcActionButton v-if="row.mutable" @click="ask('kill', row.name)">
									<template #icon><NcTowerIcon name="x" :size="18" /></template>
									Kill
								</NcActionButton>
							<NcActionButton v-if="row.mutable" @click="openRecreate(row.name)">
									<template #icon><NcTowerIcon name="rotate" :size="18" /></template>
									Recreate…
								</NcActionButton>
							<NcActionButton v-if="row.mutable" @click="openRename(row.name)">
									<template #icon><NcTowerIcon name="edit" :size="18" /></template>
									Rename…
								</NcActionButton>
							<NcActionButton v-if="row.loggable || row.mutable" @click="toggleStats(row.name)">
									<template #icon><NcTowerIcon name="activity" :size="18" /></template>
									{{ statsOpen[row.name] ? 'Hide stats' : 'Stats' }}
								</NcActionButton>
							<NcActionButton v-if="row.mutable" @click="openExec(row.name)">
									<template #icon><NcTowerIcon name="terminal" :size="18" /></template>
									Exec
								</NcActionButton>
						</NcActions>
					</div>
				</template>
			</DataTable>
			<div v-for="(blob, name) in statsOpen" :key="`stats-${name}`" class="nc-tower-stats-panel">
				<strong>{{ name }}</strong>
				<pre class="nc-tower-pre">{{ blob }}</pre>
			</div>
			<p class="nc-tower-muted">{{ lockedCount }} container(s) outside the sidecar allowlist. {{ lockedHint }}</p>
		</Section>

		<Section id="ops.stacks"
			default-open
			title="Stacks"
			:summary="`${stackRows.length} compose file(s) on pinned dirs`"
			:loading="loading.stacks"
			:error="errors.stacks"
			@refresh="refresh('stacks')">
			<DataTable :columns="stackColumns" :rows="stackRows" row-key="file" empty-text="No compose files">
				<template #cell-services="{ row }">{{ (row.services || []).join(', ') || '—' }}</template>
				<template #cell-running_hint="{ row }">{{ row.running_hint ? 'running' : '—' }}</template>
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton v-if="row.preview" type="tertiary" @click="showPreview(row)">Preview</NcButton>
						<NcActions v-if="row.file" :aria-label="`Actions for ${row.file}`">
							<NcActionButton @click="askStack('up', row)">
									<template #icon><NcTowerIcon name="arrow-up" :size="18" /></template>
									Up
								</NcActionButton>
							<NcActionButton @click="askStack('restart', row)">
									<template #icon><NcTowerIcon name="refresh" :size="18" /></template>
									Restart
								</NcActionButton>
							<NcActionButton @click="askStack('pull', row)">
									<template #icon><NcTowerIcon name="download" :size="18" /></template>
									Pull
								</NcActionButton>
							<NcActionButton @click="askStack('rebuild', row)">
									<template #icon><NcTowerIcon name="hammer" :size="18" /></template>
									Rebuild
								</NcActionButton>
							<NcActionButton @click="askStack('down', row)">
									<template #icon><NcTowerIcon name="arrow-down" :size="18" /></template>
									Down
								</NcActionButton>
						</NcActions>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="ops.host"
			default-open
			title="Host and storage"
			:summary="hostSummary"
			:severity="sev.host"
			:loading="loading.host"
			:error="errors.host"
			@refresh="refresh('host')">
			<div class="nc-tower-chips">
				<span class="nc-tower-chip">CPU {{ host.cpu_pct != null ? `${host.cpu_pct}%` : '—' }}</span>
				<span class="nc-tower-chip">load {{ (host.loadavg || []).join(' / ') || '—' }}</span>
				<span class="nc-tower-chip">mem {{ fmt.meminfo(host.mem_available) }} free</span>
				<span class="nc-tower-chip">swap {{ fmt.meminfo(host.swap_free) }} free</span>
				<span class="nc-tower-chip">pkg {{ host.package_temp_c != null ? `${host.package_temp_c}°C` : '—' }}</span>
				<span class="nc-tower-chip">up {{ fmt.duration(host.uptime_s) }}</span>
			</div>
			<DataTable :columns="diskColumns" :rows="host.disks || []" row-key="path" empty-text="No disks">
				<template #cell-used_pct="{ row }">
					<UsageBar v-if="!row.error" :percent="row.used_pct" />
					<span v-else class="nc-tower-bad">{{ row.error }}</span>
				</template>
				<template #cell-used_b="{ row }">{{ fmt.bytes(row.used_b) }} / {{ fmt.bytes(row.total_b) }}</template>
			</DataTable>
			<p class="nc-tower-muted">Interfaces: {{ ifaceLine || '—' }}</p>
		</Section>

		<Section id="ops.smart"
			title="SMART and NAS"
			:summary="smartSummary"
			:severity="sev.smart"
			:loading="loading.smart"
			:error="errors.smart"
			@refresh="refresh('smart')">
			<NcNoteCard v-if="smart.unavailable" type="warning">Unavailable: {{ smart.reason }}</NcNoteCard>
			<template v-else>
				<DataTable :columns="smartColumns" :rows="smart.disks || []" row-key="device" empty-text="No disks">
					<template #cell-health="{ row }">
						<span :class="row.health === 'PASS' ? 'nc-tower-good' : 'nc-tower-bad'">{{ row.health }}</span>
					</template>
					<template #cell-temp_c="{ row }">{{ row.temp_c != null ? `${row.temp_c}°C` : '—' }}</template>
					<template #cell-power_on_hours="{ row }">
						<span :class="{ 'nc-tower-warn-text': row.power_on_hours > 43800 }">
							{{ row.power_on_hours != null ? `${row.power_on_hours} h (${fmt.years(row.power_on_hours)})` : '—' }}
						</span>
					</template>
					<template #cell-actions="{ row }">
						<div class="nc-tower-actions-cell">
							<NcButton type="tertiary" @click="toggleSmartAttrs(row.device)">
								{{ smartAttrs[row.device] ? 'Hide' : 'Attributes' }}
							</NcButton>
						</div>
					</template>
				</DataTable>
				<div v-for="(attrs, device) in smartAttrs" :key="device" class="nc-tower-stats-panel">
					<strong>{{ device }} attributes</strong>
					<DataTable :columns="smartAttrColumns" :rows="attrs" empty-text="No attributes" />
				</div>
				<h4 class="nc-tower-subhead">Network mounts</h4>
				<DataTable :columns="nasColumns" :rows="smart.nas_mounts || []" row-key="path" empty-text="No network mounts">
					<template #cell-ok="{ row }">
						<span :class="row.ok ? 'nc-tower-good' : 'nc-tower-bad'">{{ row.ok ? 'OK' : 'down' }}</span>
					</template>
					<template #cell-used_pct="{ row }"><UsageBar :percent="row.used_pct" /></template>
				</DataTable>
			</template>
		</Section>

		<Section id="ops.gpu"
			title="GPU"
			:summary="gpuSummary"
			:severity="sev.gpu"
			:loading="loading.gpu"
			:error="errors.gpu"
			@refresh="refresh('gpu')">
			<NcNoteCard v-if="gpu.unavailable" type="warning">Unavailable: {{ gpu.reason }}</NcNoteCard>
			<template v-else>
				<DataTable :columns="gpuColumns" :rows="gpu.gpus || []" row-key="uuid" empty-text="No GPUs">
					<template #cell-util_pct="{ row }"><UsageBar :percent="row.util_pct" :warn="90" :crit="99" /></template>
					<template #cell-mem_used_mib="{ row }">{{ row.mem_used_mib }} / {{ row.mem_total_mib }} MiB</template>
					<template #cell-temp_c="{ row }">{{ row.temp_c }}°C</template>
					<template #cell-power_draw_w="{ row }">{{ row.power_draw_w }} / {{ row.power_limit_w }} W</template>
				</DataTable>
				<h4 v-if="(gpu.processes || []).length" class="nc-tower-subhead">Compute processes</h4>
				<DataTable v-if="(gpu.processes || []).length"
					:columns="gpuProcColumns"
					:rows="gpu.processes"
					empty-text="None">
					<template #cell-used_memory_mib="{ row }">{{ row.used_memory_mib != null ? `${row.used_memory_mib} MiB` : '—' }}</template>
				</DataTable>
			</template>
		</Section>

		<Section id="ops.fans"
			title="Fans"
			:summary="fanSummary"
			:loading="loading.fan"
			:error="errors.fan"
			@refresh="refreshFans">
			<FanPanel ref="fanPanel"
				@summary="fanSummary = $event"
				@loading="onFanLoading"
				@error="onFanError" />
		</Section>

		<Section id="ops.engine"
			title="Docker engine"
			:summary="engineSummary"
			:loading="loading.engine"
			:error="errors.engine"
			@refresh="refresh('engine')">
			<div class="nc-tower-chips">
				<span class="nc-tower-chip">{{ engine.Name || '—' }}</span>
				<span class="nc-tower-chip">v{{ engine.ServerVersion || '—' }}</span>
				<span class="nc-tower-chip">{{ engine.ContainersRunning ?? '—' }} running</span>
				<span class="nc-tower-chip">{{ engine.Images ?? '—' }} images</span>
				<span class="nc-tower-chip">{{ engine.OperatingSystem || '—' }}</span>
			</div>
			<TowerChart v-if="dfRows.length"
				type="bar"
				:labels="dfRows.map((r) => r.Type)"
				:datasets="dfDatasets"
				:height="150"
				show-legend
				title="Docker disk usage" />
			<DataTable :columns="dfColumns" :rows="dfRows" empty-text="No disk usage data" />
		</Section>

		<Section id="ops.images"
			title="Images"
			:summary="`${(images.images || []).length} image(s)`"
			:loading="loading.images"
			:error="errors.images"
			@refresh="refresh('images')">
			<div class="nc-tower-toolbar">
				<NcTextField :value.sync="pullRef" label="Image reference" placeholder="repo/name:tag" />
				<NcButton type="secondary" :disabled="!pullRef" @click="askPull(pullRef)">Pull</NcButton>
			</div>
			<DataTable :columns="imageColumns" :rows="imageRows" row-key="ref" default-sort="ref" empty-text="No images">
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton type="tertiary" :disabled="!row.ref" @click="askPull(row.ref)">Pull</NcButton>
						<NcButton type="tertiary" :disabled="!row.ref" @click="askImageRemove(row.ref)">Remove</NcButton>
					</div>
				</template>
			</DataTable>
			<p v-if="imageTruncated" class="nc-tower-muted">Showing first 80 of {{ (images.images || []).length }}.</p>
			<div class="nc-tower-toolbar">
				<NcButton type="secondary" :disabled="jobBusy" @click="askCleanup">
					Docker cleanup (prune)
				</NcButton>
			</div>
			<JobPanel :job="job" @dismiss="job = null" />
		</Section>

		<Section id="ops.volumes"
			title="Volumes"
			:summary="`${(volumes.volumes || []).length} volume(s)`"
			:loading="loading.volumes"
			:error="errors.volumes"
			@refresh="refresh('volumes')">
			<DataTable :columns="volumeColumns" :rows="volumeRows" row-key="name" default-sort="name" empty-text="No volumes">
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton type="tertiary" @click="inspectVolume(row.name)">Inspect</NcButton>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="ops.networks"
			title="Networks"
			:summary="`${(networks.networks || []).length} network(s)`"
			:loading="loading.networks"
			:error="errors.networks"
			@refresh="refresh('networks')">
			<DataTable :columns="networkColumns" :rows="networkRows" row-key="name" default-sort="name" empty-text="No networks">
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton type="tertiary" @click="inspectNetwork(row.name)">Inspect</NcButton>
					</div>
				</template>
			</DataTable>
		</Section>

		<Section id="ops.events"
			title="Docker events"
			:summary="eventSummary"
			:loading="loading.events"
			:error="errors.events"
			@refresh="refresh('events')">
			<div class="nc-tower-toolbar">
				<NcCheckboxRadioSwitch :checked.sync="showProbes" type="switch">
					Include healthcheck probes
				</NcCheckboxRadioSwitch>
			</div>
			<DataTable :columns="eventColumns" :rows="eventRows" empty-text="No recent events" />
			<p v-if="events.probes_hidden" class="nc-tower-muted">
				{{ events.probes_hidden }} healthcheck probe event(s) hidden.
			</p>
		</Section>

		<Section id="ops.backup"
			default-open
			title="Backup"
			:summary="backupSummary"
			:severity="sev.backup"
			:loading="loading.backup || loading.inbox"
			:error="errors.backup || errors.inbox"
			@refresh="refreshBackup">
			<p :class="backup.ok ? 'nc-tower-good' : 'nc-tower-warn-text'">
				<strong>{{ backup.status || '—' }}</strong> — {{ backup.summary || '' }}
			</p>
			<p class="nc-tower-muted">{{ backup.name || 'no backup file' }} · {{ fmt.time(backup.mtime) }}{{ backup.stale ? ' · stale' : '' }}</p>
			<p class="nc-tower-muted">
				Inventory: {{ backupInv.count || 0 }} file(s)
				<span v-if="backupInv.retention_days"> · retention {{ backupInv.retention_days }} d</span>
				<span v-if="backupInv.dir"> · {{ backupInv.dir }}</span>
			</p>
			<DataTable :columns="backupColumns" :rows="backupInv.items || []" row-key="name" empty-text="No backup files">
				<template #cell-size="{ row }">{{ fmt.bytes(row.size) }}</template>
				<template #cell-mtime="{ row }">{{ fmt.time(row.mtime) }}</template>
				<template #cell-age_hours="{ row }">{{ row.age_hours != null ? `${row.age_hours} h` : '—' }}</template>
				<template #cell-actions="{ row }">
					<div class="nc-tower-actions-cell">
						<NcButton type="tertiary" @click="askBackupDelete(row.name)">Delete</NcButton>
					</div>
				</template>
			</DataTable>
			<div class="nc-tower-toolbar">
				<NcButton type="secondary" @click="askBackup">Run backup now</NcButton>
			</div>
		</Section>

		<Section id="ops.packages"
			title="Packages"
			:summary="`${(packages.packages || []).length} upgradable · ${(packages.held || []).length} held`"
			:loading="loading.packages"
			:error="errors.packages"
			@refresh="refresh('packages')">
			<DataTable :columns="packageColumns" :rows="packages.packages || []" row-key="name" empty-text="No upgradable packages">
				<template #cell-held="{ row }">
					<NcCheckboxRadioSwitch :checked="!!row.held" type="switch" @update:checked="(v) => setPackageHold(row.name, v)">
						Hold
					</NcCheckboxRadioSwitch>
				</template>
			</DataTable>
			<p v-if="(packages.held || []).length" class="nc-tower-muted">Held: {{ (packages.held || []).join(', ') }}</p>
		</Section>

		<Section id="ops.cron"
			title="Cron"
			:summary="`${(cron.root_crontab || []).length} root entries`"
			:loading="loading.cron"
			:error="errors.cron"
			@refresh="loadCron">
			<NcNoteCard v-if="cron.error" type="warning">{{ cron.error }}</NcNoteCard>
			<label class="nc-tower-field-label" for="ops-cron-raw">root crontab</label>
			<textarea id="ops-cron-raw"
				v-model="cronDraft"
				class="nc-tower-textarea"
				rows="10"
				spellcheck="false" />
			<div class="nc-tower-toolbar">
				<NcButton type="secondary" @click="askCronSave">Save crontab</NcButton>
			</div>
		</Section>

		<Section id="ops.host-network"
			title="Network"
			:summary="networkSummary"
			:loading="loading.hostNetwork"
			:error="errors.hostNetwork"
			@refresh="refresh('hostNetwork')">
			<div class="nc-tower-chips">
				<span class="nc-tower-chip">public {{ hostNetwork.public_ip?.ip || '—' }}</span>
				<span class="nc-tower-chip">ddclient {{ hostNetwork.ddclient?.state || (hostNetwork.ddclient?.unavailable ? 'n/a' : '—') }}</span>
			</div>
			<h4 class="nc-tower-subhead">ZeroTier</h4>
			<NcNoteCard v-if="hostNetwork.zerotier?.unavailable" type="warning">{{ hostNetwork.zerotier.reason }}</NcNoteCard>
			<DataTable v-else
				:columns="ztColumns"
				:rows="hostNetwork.zerotier?.networks || []"
				empty-text="No ZeroTier networks" />
			<h4 class="nc-tower-subhead">WireGuard peers</h4>
			<NcNoteCard v-if="hostNetwork.wireguard?.unavailable" type="warning">{{ hostNetwork.wireguard.reason }}</NcNoteCard>
			<DataTable v-else
				:columns="wgColumns"
				:rows="hostNetwork.wireguard?.peers || []"
				empty-text="No peers" />
			<h4 class="nc-tower-subhead">Interfaces</h4>
			<DataTable :columns="hostIfColumns"
				:rows="hostNetwork.interfaces?.items || []"
				row-key="ifname"
				empty-text="No interfaces">
				<template #cell-addresses="{ row }">{{ fmt.addresses(row) || '—' }}</template>
			</DataTable>
		</Section>

		<Section id="ops.ollama"
			title="Ollama"
			:summary="ollamaSummary"
			:loading="loading.ollama"
			:error="errors.ollama"
			@refresh="refresh('ollama')">
			<NcNoteCard v-if="ollama.unavailable" type="warning">Unavailable: {{ ollama.reason }}</NcNoteCard>
			<template v-else>
				<div class="nc-tower-toolbar">
					<NcTextField :value.sync="ollamaPull" label="Model" placeholder="llama3.2:latest" />
					<NcButton type="secondary" :disabled="!ollamaPull || jobBusy" @click="askOllamaPull">Pull</NcButton>
				</div>
				<JobPanel :job="ollamaJob" @dismiss="ollamaJob = null" />
				<DataTable :columns="ollamaColumns" :rows="ollamaModelRows" row-key="name" empty-text="No models">
					<template #cell-size="{ row }">{{ row.size != null ? fmt.bytes(row.size) : '—' }}</template>
					<template #cell-actions="{ row }">
						<div class="nc-tower-actions-cell">
							<NcButton type="tertiary" @click="askOllamaDelete(row.name)">Delete</NcButton>
						</div>
					</template>
				</DataTable>
				<p v-if="(ollama.running || []).length" class="nc-tower-muted">
					Running: {{ (ollama.running || []).map((m) => m.name || m.model).join(', ') }}
				</p>
			</template>
		</Section>

		<Section id="ops.audit"
			title="Audit"
			:summary="`${filteredAudit.length} event(s)`"
			:loading="loading.audit"
			:error="errors.audit"
			@refresh="refresh('audit')">
			<div class="nc-tower-toolbar">
				<NcTextField :value.sync="auditFilter" label="Filter audit log" placeholder="container, backup, package…" />
			</div>
			<DataTable :columns="auditColumns" :rows="filteredAudit" empty-text="No audit rows">
				<template #cell-ts="{ row }">{{ row.ts || '—' }}</template>
			</DataTable>
		</Section>

		<Section id="ops.inbox"
			default-open
			title="Ops inbox"
			:summary="inboxSummary"
			:severity="sev.inbox"
			:loading="loading.inbox"
			:error="errors.inbox"
			@refresh="refresh('inbox')">
			<template v-if="(inbox.critical_recent || []).length">
				<h4 class="nc-tower-subhead tower-bad">Critical</h4>
				<DataTable :columns="inboxColumns" :rows="inbox.critical_recent" empty-text="None">
					<template #cell-mtime="{ row }">{{ fmt.time(row.mtime) }}</template>
				</DataTable>
			</template>
			<h4 class="nc-tower-subhead">Recent</h4>
			<DataTable :columns="inboxColumns" :rows="(inbox.inbox_recent || []).slice(0, 25)" empty-text="Empty">
				<template #cell-mtime="{ row }">{{ fmt.time(row.mtime) }}</template>
			</DataTable>
		</Section>

		<ConfirmDialog v-bind="confirm"
			:open="confirm.open"
			@cancel="confirm.open = false"
			@confirm="runConfirmed" />

		<OutputDialog :open="output.open"
			:title="output.title"
			:text="output.text"
			:follow="output.follow"
			@close="closeOutput">
			<template #bar>
				<NcCheckboxRadioSwitch v-if="output.kind === 'logs'"
					:checked.sync="logFollow"
					type="switch">
					Follow (2 s)
				</NcCheckboxRadioSwitch>
			</template>
		</OutputDialog>

		<NcDialog :open="exec.open" name="Run command" size="normal" @update:open="exec.open = false">
			<p>Exec in <strong>{{ exec.name }}</strong>. One-shot argv, no shell.</p>
			<NcTextField :value.sync="exec.raw" label="argv JSON array" placeholder='["ls","-la"]' />
			<NcNoteCard type="info">
				Shells and destructive binaries are refused by the sidecar allowlist.
			</NcNoteCard>
			<pre v-if="exec.out" class="nc-tower-pre">{{ exec.out }}</pre>
			<template #actions>
				<NcButton type="tertiary" @click="exec.open = false">Close</NcButton>
				<NcButton type="primary" :disabled="exec.busy" @click="runExec">Run</NcButton>
			</template>
		</NcDialog>

		<NcDialog :open="rename.open" name="Rename container" size="small" @update:open="rename.open = false">
			<p>Rename <strong>{{ rename.from }}</strong>.</p>
			<NcTextField :value.sync="rename.to" label="New name" />
			<template #actions>
				<NcButton type="tertiary" @click="rename.open = false">Cancel</NcButton>
				<NcButton type="primary" :disabled="!rename.to || rename.busy" @click="runRename">Rename</NcButton>
			</template>
		</NcDialog>

		<NcDialog :open="recreate.open" name="Recreate container" size="normal" @update:open="recreate.open = false">
			<p>Recreate <strong>{{ recreate.name }}</strong> with optional overrides.</p>
			<NcCheckboxRadioSwitch :checked.sync="recreate.pull" type="switch">Pull image first</NcCheckboxRadioSwitch>
			<NcTextField :value.sync="recreate.memory" label="Memory limit" placeholder="512m (optional)" />
			<NcTextField :value.sync="recreate.cpus" label="CPUs" placeholder="1.5 (optional)" />
			<NcTextField :value.sync="recreate.restart" label="Restart policy" placeholder="unless-stopped (optional)" />
			<label class="nc-tower-field-label">Env set (KEY=value per line)</label>
			<textarea v-model="recreate.envSet" class="nc-tower-textarea" rows="4" spellcheck="false" />
			<label class="nc-tower-field-label">Env unset (KEY per line)</label>
			<textarea v-model="recreate.envUnset" class="nc-tower-textarea" rows="3" spellcheck="false" />
			<p class="nc-tower-muted">Type RECREATE in the confirm dialog after Apply.</p>
			<template #actions>
				<NcButton type="tertiary" @click="recreate.open = false">Cancel</NcButton>
				<NcButton type="error" @click="confirmRecreate">Apply…</NcButton>
			</template>
		</NcDialog>
	</div>
</template>

<script>
import { showError, showSuccess } from '@nextcloud/dialogs'
import NcActionButton from '@nextcloud/vue/dist/Components/NcActionButton.js'
import NcActions from '@nextcloud/vue/dist/Components/NcActions.js'
import NcButton from '@nextcloud/vue/dist/Components/NcButton.js'
import NcCheckboxRadioSwitch from '@nextcloud/vue/dist/Components/NcCheckboxRadioSwitch.js'
import NcDialog from '@nextcloud/vue/dist/Components/NcDialog.js'
import NcNoteCard from '@nextcloud/vue/dist/Components/NcNoteCard.js'
import NcTextField from '@nextcloud/vue/dist/Components/NcTextField.js'

import AttentionList from '../components/AttentionList.vue'
import NcTowerIcon from '../components/NcTowerIcon.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import DataTable from '../components/DataTable.vue'
import FanPanel from '../components/FanPanel.vue'
import JobPanel from '../components/JobPanel.vue'
import Sparkline from '../components/Sparkline.vue'
import TowerChart from '../components/TowerChart.vue'
import OutputDialog from '../components/OutputDialog.vue'
import Section from '../components/Section.vue'
import StatusBanner from '../components/StatusBanner.vue'
import UsageBar from '../components/UsageBar.vue'

import { get, post } from '../services/api.js'
import fmt from '../services/format.js'
import { assess, worst } from '../services/health.js'
import { runJob } from '../services/jobs.js'
import Poller from '../services/poll.js'

const LOCKED_HINT = 'Widen NC_TOWER_CONTAINER_LOG_ALLOW for read-only logs without granting mutate rights.'

export default {
	name: 'Ops',
	components: {
		AttentionList, ConfirmDialog, DataTable, FanPanel, JobPanel, NcTowerIcon, OutputDialog, Section, Sparkline,
		StatusBanner, TowerChart, UsageBar,
		NcActionButton, NcActions, NcButton, NcCheckboxRadioSwitch, NcDialog, NcNoteCard, NcTextField,
	},
	data() {
		return {
			fmt,
			lockedHint: LOCKED_HINT,
			host: {},
			engineRaw: {},
			df: {},
			gpu: {},
			smart: {},
			chassisFan: {},
			containers: {},
			stacks: {},
			images: {},
			volumes: {},
			networks: {},
			events: {},
			inbox: {},
			packages: {},
			cron: {},
			cronDraft: '',
			backupInv: {},
			hostNetwork: {},
			ollama: {},
			audit: {},
			system: {},
			appUpdates: {},
			showProbes: false,
			trends: {},
			statsOpen: {},
			smartAttrs: {},
			loading: {},
			errors: {},
			containerFilter: '',
			pullRef: '',
			auditFilter: '',
			ollamaPull: '',
			fanSummary: '',
			job: null,
			ollamaJob: null,
			jobBusy: false,
			refreshingAll: false,
			updatedAt: '',
			logFollow: false,
			logTimer: null,
			confirm: { open: false, title: '', message: '', confirmLabel: 'Confirm', phrase: '', danger: false },
			pendingAction: null,
			output: { open: false, title: '', text: '', kind: '', follow: false, name: '' },
			exec: { open: false, name: '', raw: '["ls","-la"]', out: '', busy: false },
			rename: { open: false, from: '', to: '', busy: false },
			recreate: {
				open: false, name: '', pull: false, memory: '', cpus: '', restart: '',
				envSet: '', envUnset: '',
			},
			containerColumns: [
				{ key: 'name', label: 'Name' },
				{ key: 'project', label: 'Project' },
				{ key: 'status', label: 'Status' },
				{ key: 'cpu', label: 'CPU', align: 'end', sortBy: 'cpu_pct' },
				{ key: 'trend', label: 'Trend', sortable: false },
				{ key: 'mem', label: 'Memory', align: 'end' },
				{ key: 'ports', label: 'Ports' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			stackColumns: [
				{ key: 'dir', label: 'Directory' },
				{ key: 'file', label: 'Compose file', mono: true },
				{ key: 'services', label: 'Services' },
				{ key: 'running_hint', label: 'State' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			diskColumns: [
				{ key: 'path', label: 'Path' },
				{ key: 'used_b', label: 'Used' },
				{ key: 'used_pct', label: 'Usage' },
			],
			smartColumns: [
				{ key: 'device', label: 'Device' },
				{ key: 'health', label: 'Health' },
				{ key: 'model', label: 'Model' },
				{ key: 'temp_c', label: 'Temp', align: 'end' },
				{ key: 'power_on_hours', label: 'Powered on', align: 'end' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			smartAttrColumns: [
				{ key: 'id', label: 'ID', align: 'end' },
				{ key: 'name', label: 'Name' },
				{ key: 'value', label: 'Value', align: 'end' },
				{ key: 'worst', label: 'Worst', align: 'end' },
				{ key: 'thresh', label: 'Thresh', align: 'end' },
				{ key: 'raw', label: 'Raw' },
			],
			nasColumns: [
				{ key: 'path', label: 'Mount' },
				{ key: 'ok', label: 'State' },
				{ key: 'fstype', label: 'FS' },
				{ key: 'used_pct', label: 'Usage' },
			],
			gpuColumns: [
				{ key: 'name', label: 'GPU' },
				{ key: 'util_pct', label: 'Utilisation' },
				{ key: 'mem_used_mib', label: 'Memory', align: 'end' },
				{ key: 'temp_c', label: 'Temp', align: 'end' },
				{ key: 'fan_pct', label: 'Fan', align: 'end' },
				{ key: 'power_draw_w', label: 'Power', align: 'end' },
			],
			gpuProcColumns: [
				{ key: 'pid', label: 'PID' },
				{ key: 'process_name', label: 'Process' },
				{ key: 'used_memory_mib', label: 'Memory', align: 'end' },
			],
			dfColumns: [
				{ key: 'Type', label: 'Type' },
				{ key: 'TotalCount', label: 'Total', align: 'end' },
				{ key: 'Active', label: 'Active', align: 'end' },
				{ key: 'Size', label: 'Size', align: 'end' },
				{ key: 'Reclaimable', label: 'Reclaimable', align: 'end' },
			],
			imageColumns: [
				{ key: 'ref', label: 'Reference' },
				{ key: 'id', label: 'ID', mono: true },
				{ key: 'size', label: 'Size', align: 'end' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			volumeColumns: [
				{ key: 'name', label: 'Name' },
				{ key: 'driver', label: 'Driver' },
				{ key: 'mountpoint', label: 'Mount point', mono: true },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			networkColumns: [
				{ key: 'name', label: 'Name' },
				{ key: 'driver', label: 'Driver' },
				{ key: 'scope', label: 'Scope' },
				{ key: 'id', label: 'ID', mono: true },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			eventColumns: [
				{ key: 'when', label: 'When' },
				{ key: 'type', label: 'Type' },
				{ key: 'action', label: 'Action' },
				{ key: 'target', label: 'Target' },
			],
			inboxColumns: [
				{ key: 'name', label: 'File' },
				{ key: 'monitor', label: 'Monitor' },
				{ key: 'status', label: 'Status' },
				{ key: 'detail', label: 'Detail' },
				{ key: 'mtime', label: 'When' },
			],
			backupColumns: [
				{ key: 'name', label: 'File' },
				{ key: 'size', label: 'Size', align: 'end' },
				{ key: 'mtime', label: 'Modified' },
				{ key: 'age_hours', label: 'Age', align: 'end' },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			packageColumns: [
				{ key: 'name', label: 'Package' },
				{ key: 'old_version', label: 'Installed' },
				{ key: 'new_version', label: 'Available' },
				{ key: 'held', label: 'Hold', sortable: false },
			],
			ztColumns: [
				{ key: 'name', label: 'Name' },
				{ key: 'id', label: 'Network ID', mono: true },
				{ key: 'status', label: 'Status' },
				{ key: 'type', label: 'Type' },
			],
			wgColumns: [
				{ key: 'public_key', label: 'Peer', mono: true },
				{ key: 'endpoint', label: 'Endpoint' },
				{ key: 'allowed_ips', label: 'Allowed IPs' },
				{ key: 'latest_handshake', label: 'Handshake' },
			],
			hostIfColumns: [
				{ key: 'name', label: 'Interface' },
				{ key: 'state', label: 'State' },
				{ key: 'addresses', label: 'Addresses' },
			],
			ollamaColumns: [
				{ key: 'name', label: 'Model' },
				{ key: 'size', label: 'Size', align: 'end' },
				{ key: 'digest', label: 'Digest', mono: true },
				{ key: 'actions', label: '', align: 'end', sortable: false },
			],
			auditColumns: [
				{ key: 'ts', label: 'When' },
				{ key: 'line', label: 'Event' },
			],
		}
	},
	computed: {
		verdict() {
			return assess({
				host: this.host,
				containers: this.containers,
				smart: this.smart,
				gpu: this.gpu,
				inbox: this.inbox,
				packages: this.packages,
				system: this.system,
				updates: this.appUpdates,
				chassisFan: this.chassisFan,
				backup: this.backupInv,
			})
		},
		sev() {
			const bySection = (name) => worst(...this.verdict.items
				.filter((item) => item.section === name)
				.map((item) => item.severity))
			return {
				containers: bySection('containers'),
				host: bySection('host'),
				smart: bySection('smart'),
				gpu: bySection('gpu'),
				inbox: bySection('inbox'),
				system: bySection('system'),
				backup: bySection('backup'),
				fans: bySection('fans'),
			}
		},
		facts() {
			const counts = this.containers.counts || {}
			const out = []
			if (counts.total != null) {
				out.push(`${counts.running || 0}/${counts.total} containers running`)
			}
			if (this.host.cpu_pct != null) {
				out.push(`CPU ${this.host.cpu_pct}%`)
			}
			if (this.host.package_temp_c != null) {
				out.push(`package ${this.host.package_temp_c}°C`)
			}
			const disks = (this.smart.disks || []).length
			if (disks) {
				out.push(`${(this.smart.disks || []).filter((d) => d.health === 'PASS').length}/${disks} SMART PASS`)
			}
			if (this.host.uptime_s) {
				out.push(`up ${fmt.duration(this.host.uptime_s)}`)
			}
			return out
		},
		filteredContainers() {
			const rows = this.containers.containers || []
			const query = this.containerFilter.trim().toLowerCase()
			if (!query) {
				return rows
			}
			return rows.filter((row) => `${row.name} ${row.status} ${row.image || ''} ${row.project || ''}`
				.toLowerCase().includes(query))
		},
		lockedCount() {
			return (this.containers.containers || []).filter((row) => !row.mutable && !row.loggable).length
		},
		containerSummary() {
			const counts = this.containers.counts || {}
			return `${counts.running || 0} running · ${counts.exited || 0} exited · ${counts.total || 0} total`
		},
		hostSummary() {
			const disks = this.host.disks || []
			const worstDisk = disks.reduce((acc, d) => (Number(d.used_pct) > Number(acc?.used_pct || 0) ? d : acc), null)
			return worstDisk ? `CPU ${this.host.cpu_pct ?? '—'}% · busiest disk ${worstDisk.path} ${worstDisk.used_pct}%` : ''
		},
		smartSummary() {
			const disks = this.smart.disks || []
			if (!disks.length) {
				return this.smart.unavailable ? 'unavailable' : ''
			}
			return `${disks.filter((d) => d.health === 'PASS').length}/${disks.length} PASS`
		},
		gpuSummary() {
			const gpus = this.gpu.gpus || []
			return gpus.length ? gpus.map((g) => `${g.name} ${g.temp_c}°C`).join(', ') : ''
		},
		engine() {
			return this.engineRaw.info || {}
		},
		engineSummary() {
			return this.engine.ServerVersion ? `Docker ${this.engine.ServerVersion} · ${this.engine.Containers ?? '—'} containers` : ''
		},
		backup() {
			return this.inbox.backup || {}
		},
		backupSummary() {
			const status = this.backup.status ? `${this.backup.status}${this.backup.stale ? ' · stale' : ''}` : ''
			const inv = this.backupInv.count != null ? `${this.backupInv.count} file(s)` : ''
			return [status, inv].filter(Boolean).join(' · ')
		},
		eventSummary() {
			const shown = (this.events.events || []).length
			const hidden = this.events.probes_hidden || 0
			return hidden ? `${shown} shown · ${hidden} probes hidden` : `${shown} in last hour`
		},
		inboxSummary() {
			const crit = (this.inbox.critical_recent || []).length
			return crit ? `${crit} critical` : `${(this.inbox.inbox_recent || []).length} recent`
		},
		ifaceLine() {
			return (this.host.ifaces || []).slice(0, 6)
				.map((iface) => `${iface.name || ''} ${fmt.addresses(iface)}`.trim())
				.filter(Boolean).join(' · ')
		},
		networkSummary() {
			const zt = (this.hostNetwork.zerotier?.networks || []).length
			const wg = (this.hostNetwork.wireguard?.peers || []).length
			const ip = this.hostNetwork.public_ip?.ip
			return [ip ? `public ${ip}` : '', zt ? `${zt} ZT` : '', wg ? `${wg} WG peer(s)` : ''].filter(Boolean).join(' · ')
		},
		ollamaSummary() {
			if (this.ollama.unavailable) {
				return 'unavailable'
			}
			return `${(this.ollama.models || []).length} model(s)`
		},
		ollamaModelRows() {
			return (this.ollama.models || []).map((model) => ({
				name: model.name || model.model || '',
				size: model.size,
				digest: String(model.digest || '').slice(0, 16),
			}))
		},
		filteredAudit() {
			const rows = this.audit.rows || []
			const query = this.auditFilter.trim().toLowerCase()
			if (!query) {
				return rows.slice().reverse()
			}
			return rows.filter((row) => String(row.line || '').toLowerCase().includes(query)).reverse()
		},
		stackRows() {
			return this.stacks.stacks || []
		},
		dfDatasets() {
			const bytes = (text) => {
				const m = String(text || '').match(/([\d.]+)\s*([KMGT]?B)/i)
				if (!m) {
					return 0
				}
				const unit = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 }
				return (parseFloat(m[1]) * (unit[m[2].toUpperCase()] || 1)) / 1024 ** 3
			}
			return [
				{ label: 'Size (GB)', data: this.dfRows.map((r) => bytes(r.Size)) },
				{ label: 'Reclaimable (GB)', data: this.dfRows.map((r) => bytes(r.Reclaimable)) },
			]
		},
		dfRows() {
			return (this.df.rows || []).filter((row) => typeof row === 'object')
		},
		imageRows() {
			const list = Array.isArray(this.images.images) ? this.images.images : []
			return list.slice(0, 80).map((img) => {
				const repo = img.Repository || img.repository || ''
				const tag = img.Tag || img.tag || ''
				return {
					ref: repo ? `${repo}${tag && tag !== '<none>' ? `:${tag}` : ''}` : '',
					id: String(img.ID || img.Id || '').slice(0, 12),
					size: img.Size || img.size || '',
				}
			})
		},
		imageTruncated() {
			return (this.images.images || []).length > 80
		},
		volumeRows() {
			const list = Array.isArray(this.volumes.volumes) ? this.volumes.volumes : []
			return list.map((vol) => ({
				name: vol.Name || vol.name || '',
				driver: vol.Driver || vol.driver || '',
				mountpoint: vol.Mountpoint || vol.mountpoint || '',
			}))
		},
		networkRows() {
			const list = Array.isArray(this.networks.networks) ? this.networks.networks : []
			return list.map((net) => ({
				name: net.Name || net.name || '',
				driver: net.Driver || net.driver || '',
				scope: net.Scope || net.scope || '',
				id: String(net.ID || net.Id || '').slice(0, 12),
			}))
		},
		eventRows() {
			const list = Array.isArray(this.events.events) ? this.events.events : []
			return list.slice(-80).reverse().map((event) => {
				let stamp = event.time || event.Time
				if (stamp == null && event.timeNano) {
					stamp = Math.floor(Number(event.timeNano) / 1e9)
				}
				return {
					when: fmt.time(stamp),
					type: event.Type || event.type || '',
					action: event.Action || event.action || '',
					target: event.Actor?.Attributes?.name || event.name || '',
				}
			})
		},
	},
	watch: {
		showProbes() {
			this.refresh('events')
		},
		logFollow(on) {
			this.stopLogFollow()
			if (on && this.output.name) {
				this.logTimer = setInterval(() => this.loadLogs(this.output.name), 2000)
			}
		},
	},
	created() {
		// Not in data(): observing timer handles and a Map buys nothing.
		this.poller = new Poller()
		const p = this.poller
		p.add('containers', () => this.fetch('containers', '/tower/containers'), 10000)
		p.add('host', () => this.fetch('host', '/tower/host'), 15000)
		p.add('gpu', () => this.fetch('gpu', '/tower/gpu'), 30000)
		p.add('events', () => this.fetch('events', '/tower/docker/events',
			{ since: '60m', probes: this.showProbes ? 1 : 0 }), 30000)
		p.add('engine', () => Promise.all([
			this.fetch('engineRaw', '/tower/docker/info', null, 'engine'),
			this.fetch('df', '/tower/docker/df', null, 'engine'),
		]), 60000)
		// Fans: FanPanel self-fetches; Ops also keeps chassisFan for assess().
		p.add('chassisFan', () => this.fetch('chassisFan', '/tower/chassis-fan'), 60000)
		p.add('inbox', () => this.fetch('inbox', '/tower/ops-inbox'), 60000)
		p.add('backup', () => this.fetch('backupInv', '/tower/backup', null, 'backup'), 120000)
		p.add('stacks', () => this.fetch('stacks', '/tower/stacks'), 60000)
		p.add('images', () => this.fetch('images', '/tower/docker/images'), 120000)
		p.add('volumes', () => this.fetch('volumes', '/tower/docker/volumes'), 120000)
		p.add('networks', () => this.fetch('networks', '/tower/docker/networks'), 120000)
		p.add('hostNetwork', () => this.fetch('hostNetwork', '/tower/network'), 120000)
		p.add('ollama', () => this.fetch('ollama', '/tower/ollama'), 120000)
		p.add('audit', () => this.fetch('audit', '/tower/audit', { limit: 200 }), 120000)
		p.add('cron', () => this.loadCron(), 300000)
		// smartctl walks every physical disk; 1.8 ran this every 12 s.
		p.add('smart', () => this.fetch('smart', '/tower/smart'), 300000)
		p.add('packages', () => this.fetch('packages', '/tower/packages'), 300000)
		// Nextcloud's own health feeds the same verdict banner.
		p.add('system', () => this.fetch('system', '/systeminfo'), 300000)
		p.add('appUpdates', () => this.fetch('appUpdates', '/appupdates'), 300000)
		p.start()
	},
	beforeDestroy() {
		this.poller.stop()
		this.stopLogFollow()
	},
	methods: {
		/**
		 * @param {string} [name] section to refresh; omit for all
		 * @return {Promise<void>} resolves once the loaders settle
		 */
		refresh(name) {
			if (name === 'fan') {
				return this.refreshFans()
			}
			return this.poller.refresh(name)
		},
		refreshFans() {
			return this.$refs.fanPanel?.refresh?.() || Promise.resolve()
		},
		onFanLoading(value) {
			this.$set(this.loading, 'fan', !!value)
		},
		onFanError(message) {
			this.$set(this.errors, 'fan', message || '')
		},
		refreshBackup() {
			return Promise.all([
				this.poller.refresh('inbox'),
				this.poller.refresh('backup'),
			])
		},
		async loadCron() {
			this.$set(this.loading, 'cron', true)
			try {
				this.cron = await get('/tower/cron')
				this.cronDraft = this.cron.root_crontab_raw || ''
				this.$set(this.errors, 'cron', '')
			} catch (error) {
				this.$set(this.errors, 'cron', error.message)
			} finally {
				this.$set(this.loading, 'cron', false)
			}
		},
		recordTrends(rows) {
			const next = { ...this.trends }
			for (const row of rows) {
				const pct = parseFloat(String(row.cpu || '').replace('%', ''))
				row.cpu_pct = Number.isFinite(pct) ? pct : 0
				// 30 samples at 10 s ≈ five minutes of history, held in memory
				// only: nothing on the host records per-container CPU.
				next[row.name] = [...(next[row.name] || []), row.cpu_pct].slice(-30)
			}
			this.trends = next
		},
		async fetch(key, path, params, loadingKey) {
			const slot = loadingKey || key
			this.$set(this.loading, slot, true)
			try {
				this[key] = await get(path, params)
				if (key === 'containers') {
					this.recordTrends(this[key].containers || [])
				}
				this.$set(this.errors, slot, '')
				this.updatedAt = new Date().toLocaleTimeString()
			} catch (error) {
				this.$set(this.errors, slot, error.message)
			} finally {
				this.$set(this.loading, slot, false)
			}
		},
		async refreshAll() {
			this.refreshingAll = true
			try {
				await Promise.all([
					this.poller.refresh(),
					this.refreshFans(),
				])
			} finally {
				this.refreshingAll = false
			}
		},

		ask(action, name) {
			const danger = ['kill', 'stop'].includes(action)
			this.confirm = {
				open: true,
				title: `${action[0].toUpperCase()}${action.slice(1)} container`,
				message: `${action} ${name}?`,
				confirmLabel: action,
				phrase: '',
				danger,
			}
			this.pendingAction = () => this.runContainer(action, name)
		},
		askStack(action, row) {
			const risky = row.risky || ['down', 'rebuild'].includes(action)
			this.confirm = {
				open: true,
				title: `Compose ${action}`,
				message: `${action} ${row.file}?`,
				confirmLabel: action,
				phrase: risky ? 'YES' : '',
				danger: risky,
			}
			this.pendingAction = () => this.runStack(action, row.file)
		},
		askPull(image) {
			this.confirm = {
				open: true,
				title: 'Pull image',
				message: `Pull ${image}?`,
				confirmLabel: 'Pull',
				phrase: '',
				danger: false,
			}
			this.pendingAction = () => this.runPull(image)
		},
		askImageRemove(ref) {
			this.confirm = {
				open: true,
				title: 'Remove image',
				message: `Remove image ${ref}? Blocked if any container still references it.`,
				confirmLabel: 'Remove',
				phrase: 'REMOVE',
				danger: true,
			}
			this.pendingAction = () => this.mutate(
				post('/tower/docker/images/remove', { ref }),
				`Removed ${ref}`,
				() => this.poller.refresh('images'),
			)
		},
		askCleanup() {
			this.confirm = {
				open: true,
				title: 'Docker cleanup',
				message: 'Run the allowlisted docker-cleanup prune job on the host?',
				confirmLabel: 'Prune',
				phrase: 'PRUNE',
				danger: true,
			}
			this.pendingAction = () => this.startJob('docker-cleanup', {}, 'job')
		},
		askBackup() {
			this.confirm = {
				open: true,
				title: 'Run backup',
				message: 'Run the allowlisted backup script now? This can take several minutes.',
				confirmLabel: 'Run backup',
				phrase: '',
				danger: false,
			}
			this.pendingAction = () => this.runBackup()
		},
		askBackupDelete(name) {
			this.confirm = {
				open: true,
				title: 'Delete backup',
				message: `Permanently delete ${name}?`,
				confirmLabel: 'Delete',
				phrase: 'DELETE',
				danger: true,
			}
			this.pendingAction = () => this.mutate(
				post('/tower/backup/delete', { file: name }),
				`Deleted ${name}`,
				() => this.poller.refresh('backup'),
			)
		},
		askCronSave() {
			this.confirm = {
				open: true,
				title: 'Save root crontab',
				message: 'Replace the root crontab with the edited text? A backup is kept under /ops/state/cron-backups.',
				confirmLabel: 'Save',
				phrase: 'CRON',
				danger: true,
			}
			this.pendingAction = () => this.mutate(
				post('/tower/cron', { crontab: this.cronDraft }),
				'Crontab saved',
				() => this.loadCron(),
			)
		},
		askOllamaPull() {
			const model = this.ollamaPull.trim()
			if (!model) {
				return
			}
			this.confirm = {
				open: true,
				title: 'Pull Ollama model',
				message: `Pull ${model}?`,
				confirmLabel: 'Pull',
				phrase: '',
				danger: false,
			}
			this.pendingAction = () => this.startJob('ollama-pull', { model }, 'ollamaJob')
		},
		askOllamaDelete(model) {
			this.confirm = {
				open: true,
				title: 'Delete Ollama model',
				message: `Delete model ${model}?`,
				confirmLabel: 'Delete',
				phrase: 'DELETE',
				danger: true,
			}
			this.pendingAction = () => this.mutate(
				post('/tower/ollama/models', { op: 'delete', model }),
				`Deleted ${model}`,
				() => this.poller.refresh('ollama'),
			)
		},
		async runConfirmed() {
			const action = this.pendingAction
			this.confirm.open = false
			this.pendingAction = null
			if (action) {
				await action()
			}
		},

		async mutate(promise, okMessage, after) {
			try {
				const result = await promise
				if (result && result.ok === true) {
					showSuccess(okMessage)
				} else if (result && result.id) {
					showSuccess(okMessage)
				} else {
					showError(result?.error || result?.stderr || 'Action failed')
				}
			} catch (error) {
				showError(error.message)
			} finally {
				if (after) {
					await after()
				}
			}
		},
		async startJob(kind, body, slot) {
			this.jobBusy = true
			this[slot] = { id: '', kind, status: 'running', log: '' }
			try {
				const job = await runJob(kind, body || {}, (tick) => {
					this[slot] = tick
				})
				this[slot] = job
				if (job.status === 'done') {
					showSuccess(`${kind} finished`)
				} else {
					showError(`${kind} failed (exit ${job.exit})`)
				}
			} catch (error) {
				showError(error.message)
			} finally {
				this.jobBusy = false
				if (kind === 'ollama-pull') {
					await this.poller.refresh('ollama')
				}
				if (kind === 'docker-cleanup') {
					await this.poller.refresh('images')
					await this.poller.refresh('engine')
				}
			}
		},
		runContainer(action, name) {
			const path = `/tower/containers/${encodeURIComponent(name)}/${action}`
			return this.mutate(post(path, {}), `${name}: ${action} done`, () => this.poller.refresh('containers'))
		},
		runStack(action, file) {
			return this.mutate(post(`/tower/stacks/${action}`, { file }), `Stack ${action} done`, async () => {
				await this.poller.refresh('stacks')
				await this.poller.refresh('containers')
			})
		},
		runPull(image) {
			return this.mutate(post('/tower/docker/images/pull', { image }), `Pulled ${image}`, () => this.poller.refresh('images'))
		},
		runBackup() {
			return this.mutate(post('/tower/backup/run', {}), 'Backup finished', () => this.refreshBackup())
		},
		async setPackageHold(name, hold) {
			await this.mutate(
				post('/tower/packages/hold', { package: name, hold: !!hold }),
				hold ? `Holding ${name}` : `Unheld ${name}`,
				() => this.poller.refresh('packages'),
			)
		},

		async toggleStats(name) {
			if (this.statsOpen[name]) {
				this.$delete(this.statsOpen, name)
				return
			}
			this.$set(this.statsOpen, name, 'Loading…')
			try {
				const data = await get(`/tower/containers/${encodeURIComponent(name)}/stats`)
				this.$set(this.statsOpen, name, JSON.stringify(data.stats || data, null, 2))
			} catch (error) {
				this.$set(this.statsOpen, name, error.message)
			}
		},
		async toggleSmartAttrs(device) {
			if (this.smartAttrs[device]) {
				this.$delete(this.smartAttrs, device)
				return
			}
			this.$set(this.smartAttrs, device, [])
			try {
				const data = await get('/tower/smart/attributes', { dev: device })
				this.$set(this.smartAttrs, device, data.attributes || [])
			} catch (error) {
				showError(error.message)
				this.$delete(this.smartAttrs, device)
			}
		},

		openRename(name) {
			this.rename = { open: true, from: name, to: name, busy: false }
		},
		async runRename() {
			this.rename.busy = true
			try {
				await this.mutate(
					post(`/tower/containers/${encodeURIComponent(this.rename.from)}/rename`, { name: this.rename.to }),
					`Renamed to ${this.rename.to}`,
					() => this.poller.refresh('containers'),
				)
				this.rename.open = false
			} finally {
				this.rename.busy = false
			}
		},
		openRecreate(name) {
			this.recreate = {
				open: true, name, pull: false, memory: '', cpus: '', restart: '',
				envSet: '', envUnset: '',
			}
		},
		confirmRecreate() {
			this.recreate.open = false
			const body = this.buildRecreateBody()
			this.confirm = {
				open: true,
				title: 'Recreate container',
				message: `Recreate ${this.recreate.name} with the chosen overrides?`,
				confirmLabel: 'Recreate',
				phrase: 'RECREATE',
				danger: true,
			}
			this.pendingAction = () => this.mutate(
				post(`/tower/containers/${encodeURIComponent(this.recreate.name)}/recreate`, body),
				`${this.recreate.name}: recreate done`,
				() => this.poller.refresh('containers'),
			)
		},
		buildRecreateBody() {
			const body = { pull: !!this.recreate.pull }
			const envSet = {}
			for (const line of String(this.recreate.envSet || '').split('\n')) {
				const trimmed = line.trim()
				if (!trimmed || !trimmed.includes('=')) {
					continue
				}
				const idx = trimmed.indexOf('=')
				envSet[trimmed.slice(0, idx)] = trimmed.slice(idx + 1)
			}
			const envUnset = String(this.recreate.envUnset || '').split('\n')
				.map((line) => line.trim()).filter(Boolean)
			if (Object.keys(envSet).length) {
				body.env_set = envSet
			}
			if (envUnset.length) {
				body.env_unset = envUnset
			}
			if (this.recreate.memory.trim()) {
				body.memory = this.recreate.memory.trim()
			}
			if (this.recreate.cpus.trim()) {
				body.cpus = this.recreate.cpus.trim()
			}
			if (this.recreate.restart.trim()) {
				body.restart_policy = this.recreate.restart.trim()
			}
			return body
		},

		async openLogs(name) {
			// A follow timer from a previously opened container would otherwise
			// keep polling and overwrite this dialog's body.
			this.stopLogFollow()
			this.logFollow = false
			this.output = { open: true, title: `Logs — ${name}`, text: 'Loading…', kind: 'logs', follow: true, name }
			await this.loadLogs(name)
		},
		async loadLogs(name) {
			try {
				const data = await get(`/tower/containers/${encodeURIComponent(name)}/logs`, { tail: 200 })
				this.output.text = data.logs || '(empty)'
			} catch (error) {
				this.output.text = error.message
			}
		},
		stopLogFollow() {
			if (this.logTimer) {
				clearInterval(this.logTimer)
				this.logTimer = null
			}
		},
		closeOutput() {
			this.output.open = false
			this.logFollow = false
			this.stopLogFollow()
		},
		async openInspect(name) {
			this.output = { open: true, title: `Inspect — ${name}`, text: 'Loading…', kind: 'inspect', follow: false, name }
			try {
				const data = await get(`/tower/containers/${encodeURIComponent(name)}/inspect`)
				this.output.text = JSON.stringify(data.inspect || data, null, 2)
			} catch (error) {
				this.output.text = error.message
			}
		},
		showPreview(row) {
			this.output = { open: true, title: row.file, text: row.preview || '', kind: 'preview', follow: false, name: '' }
		},
		async inspectVolume(name) {
			this.output = { open: true, title: `Volume — ${name}`, text: 'Loading…', kind: 'inspect', follow: false, name }
			try {
				const data = await get('/tower/docker/volumes', { name })
				this.output.text = JSON.stringify(data.inspect || data, null, 2)
			} catch (error) {
				this.output.text = error.message
			}
		},
		async inspectNetwork(name) {
			this.output = { open: true, title: `Network — ${name}`, text: 'Loading…', kind: 'inspect', follow: false, name }
			try {
				const data = await get('/tower/docker/networks', { name })
				this.output.text = JSON.stringify(data.inspect || data, null, 2)
			} catch (error) {
				this.output.text = error.message
			}
		},

		openExec(name) {
			this.exec = { open: true, name, raw: '["ls","-la"]', out: '', busy: false }
		},
		async runExec() {
			let cmd
			try {
				cmd = JSON.parse(this.exec.raw)
			} catch (error) {
				showError('Command must be a JSON array, e.g. ["ls","-la"]')
				return
			}
			if (!Array.isArray(cmd) || !cmd.length) {
				showError('Command must be a non-empty JSON array')
				return
			}
			this.exec.busy = true
			try {
				const result = await post(`/tower/containers/${encodeURIComponent(this.exec.name)}/exec`, { cmd, timeout: 30 })
				this.exec.out = `${result.stdout || ''}${result.stderr || ''}${result.error ? `\nERR ${result.error}` : ''}`
			} catch (error) {
				this.exec.out = error.message
			} finally {
				this.exec.busy = false
			}
		},
	},
}
</script>

<style lang="scss" scoped>
.nc-tower-cpu-cell,
.nc-tower-life {
	display: flex;
	flex-direction: column;
	gap: 2px;
	align-items: flex-end;
	min-width: 110px;
}

.nc-tower-life { align-items: flex-start; }

.nc-tower-toolbar {
	display: flex;
	align-items: flex-end;
	gap: 8px;
	flex-wrap: wrap;
	margin-bottom: 10px;
	max-width: 640px;
}

.nc-tower-subhead {
	margin: 16px 0 6px;
	font-size: 0.95em;
	color: var(--color-text-maxcontrast);
}

.nc-tower-field-label {
	display: block;
	margin: 10px 0 4px;
	font-size: 0.85em;
	color: var(--color-text-maxcontrast);
}

.nc-tower-textarea {
	width: 100%;
	max-width: 720px;
	font-family: var(--font-face-monospace, monospace);
	font-size: 0.82em;
	padding: 8px;
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius, 4px);
	background: var(--color-main-background);
	color: var(--color-main-text);
	resize: vertical;
}

.nc-tower-stats-panel {
	margin: 10px 0;
	padding: 8px 10px;
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius-large, 8px);
}

.nc-tower-pre {
	margin: 8px 0 0;
	max-height: 220px;
	overflow: auto;
	font-family: var(--font-face-monospace, monospace);
	font-size: 0.78em;
	background: var(--color-background-dark);
	border-radius: var(--border-radius, 4px);
	padding: 8px;
	white-space: pre-wrap;
}

.nc-tower-state {
	text-transform: capitalize;

	&--running { color: var(--color-success); }
	&--exited { color: var(--color-error); }
	&--paused { color: var(--color-warning); }
}

.nc-tower-good { color: var(--color-success); }
.nc-tower-bad { color: var(--color-error); }
.nc-tower-warn-text { color: var(--color-warning); }
</style>
