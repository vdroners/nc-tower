/**
 * Control Tower Ops + Tools UI (owned; not Admin Cockpit bundle).
 */
(function () {
	'use strict';

	const BASE = OC.generateUrl('/apps/nc_tower');

	function token() {
		return (window.OC && OC.requestToken) ? OC.requestToken : '';
	}

	function toast(msg) {
		const el = document.getElementById('nc-tower-toast');
		if (!el) {
			console.log('[nc_tower]', msg);
			return;
		}
		el.hidden = false;
		el.textContent = msg;
		clearTimeout(el._t);
		el._t = setTimeout(() => { el.hidden = true; }, 4500);
	}

	async function apiGet(path) {
		const res = await fetch(BASE + path, {
			credentials: 'same-origin',
			headers: { requesttoken: token() },
		});
		const data = await res.json().catch(() => ({}));
		if (!res.ok) {
			const err = new Error(data.error || data.detail || ('HTTP ' + res.status));
			err.status = res.status;
			err.data = data;
			throw err;
		}
		return data;
	}

	async function apiPost(path, body) {
		const res = await fetch(BASE + path, {
			method: 'POST',
			credentials: 'same-origin',
			headers: {
				'Content-Type': 'application/json',
				requesttoken: token(),
			},
			body: JSON.stringify(body || {}),
		});
		const data = await res.json().catch(() => ({}));
		if (!res.ok) {
			const err = new Error(data.error || data.detail || ('HTTP ' + res.status));
			err.status = res.status;
			err.data = data;
			throw err;
		}
		return data;
	}

	function setBody(section, html) {
		const root = document.querySelector('[data-section="' + section + '"] .nc-tower-card__body');
		if (root) root.innerHTML = html;
	}

	function setBanner(msg) {
		const el = document.getElementById('nc-tower-banner');
		if (!el) return;
		if (!msg) {
			el.hidden = true;
			el.textContent = '';
			return;
		}
		el.hidden = false;
		el.textContent = msg;
	}

	function esc(s) {
		return String(s == null ? '' : s)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;');
	}

	function fmtBytes(n) {
		n = Number(n) || 0;
		const u = ['B', 'KB', 'MB', 'GB', 'TB'];
		let i = 0;
		while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
		return n.toFixed(i ? 1 : 0) + ' ' + u[i];
	}

	function fmtTime(ts) {
		if (!ts) return '—';
		try { return new Date(ts * 1000).toLocaleString(); } catch (e) { return String(ts); }
	}

	async function loadHost() {
		try {
			const d = await apiGet('/tower/host');
			const disks = (d.disks || []).map((x) => {
				if (x.error) return '<li>' + esc(x.path) + ': ' + esc(x.error) + '</li>';
				return '<li><strong>' + esc(x.path) + '</strong> ' +
					esc(fmtBytes(x.used_b)) + ' / ' + esc(fmtBytes(x.total_b)) +
					' (' + esc(x.used_pct) + '% used, ' + esc(fmtBytes(x.free_b)) + ' free)</li>';
			}).join('');
			setBody('host',
				'<div class="nc-tower-chips">' +
				'<span class="nc-tower-chip">load ' + esc((d.loadavg || []).join(' / ')) + '</span>' +
				'<span class="nc-tower-chip">mem avail ' + esc(d.mem_available || '—') + '</span>' +
				'<span class="nc-tower-chip">uptime ' + esc(Math.round(d.uptime_s || 0)) + 's</span>' +
				'</div><ul>' + disks + '</ul>');
		} catch (e) {
			setBody('host', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
			setBanner('Sidecar unavailable or host metrics failed — check nc_tower_sidecar.');
		}
	}

	async function loadGpu() {
		try {
			const d = await apiGet('/tower/gpu');
			if (d.unavailable) {
				setBody('gpu', '<p class="nc-tower-muted">Unavailable: ' + esc(d.reason || 'n/a') + '</p>');
				return;
			}
			const rows = (d.gpus || []).map((g) =>
				'<tr><td>' + esc(g.name) + '</td><td>' + esc(g.util_pct) + '%</td><td>' +
				esc(g.mem_used_mib) + ' / ' + esc(g.mem_total_mib) + ' MiB</td><td>' +
				esc(g.temp_c) + '°C</td><td>' + esc(g.fan_pct) + '%</td></tr>').join('');
			setBody('gpu', '<table class="nc-tower-table"><thead><tr><th>Name</th><th>Util</th><th>Mem</th><th>Temp</th><th>Fan</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">No GPUs</td></tr>') + '</tbody></table>');
		} catch (e) {
			setBody('gpu', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadSmart() {
		try {
			const d = await apiGet('/tower/smart');
			if (d.unavailable) {
				setBody('smart', '<p class="nc-tower-muted">Unavailable: ' + esc(d.reason || 'n/a') + '</p>');
				return;
			}
			const rows = (d.disks || []).map((x) => {
				const cls = x.health === 'PASS' ? 'nc-tower-ok' : (x.health === 'FAIL' ? 'nc-tower-error' : 'nc-tower-warn');
				return '<tr><td>' + esc(x.device) + '</td><td class="' + cls + '">' + esc(x.health) + '</td></tr>';
			}).join('');
			setBody('smart', '<table class="nc-tower-table"><thead><tr><th>Device</th><th>Health</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="2">No disks</td></tr>') + '</tbody></table>' +
				'<p class="nc-tower-muted">Full SMART attrs: Webmin → SMART Health</p>');
		} catch (e) {
			setBody('smart', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadFan() {
		try {
			const d = await apiGet('/tower/fan');
			if (d.unavailable) {
				setBody('fan', '<p class="nc-tower-muted">Unavailable: ' + esc(d.reason || 'n/a') +
					'. Chassis fans: Webmin Fan Control.</p>');
				return;
			}
			let html = '<pre class="nc-tower-preview">' + esc(JSON.stringify(d, null, 2).slice(0, 1500)) + '</pre>';
			html += '<p><label>All fans % <input type="number" id="nc-tower-fan-speed" min="20" max="100" value="40" /></label> ';
			html += '<button type="button" id="nc-tower-fan-set">Set all (≥20%)</button> ';
			html += '<button type="button" id="nc-tower-fan-auto">Set auto</button></p>';
			html += '<p class="nc-tower-muted">Off / 0% rejected. Chassis PWM via Webmin.</p>';
			setBody('fan', html);
			document.getElementById('nc-tower-fan-set')?.addEventListener('click', async () => {
				const speed = parseInt(document.getElementById('nc-tower-fan-speed').value, 10);
				if (!confirm('Set all GPU fans to ' + speed + '%?')) return;
				try {
					const r = await apiPost('/tower/fan', { op: 'set-all-speeds', speed });
					toast(r.ok ? 'Fan speed set' : (r.error || 'failed'));
					loadFan();
				} catch (e) { toast(e.message); }
			});
			document.getElementById('nc-tower-fan-auto')?.addEventListener('click', async () => {
				try {
					const r = await apiPost('/tower/fan', { op: 'set-auto' });
					toast(r.ok ? 'Fan auto' : (r.error || 'failed'));
					loadFan();
				} catch (e) { toast(e.message); }
			});
		} catch (e) {
			setBody('fan', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	let containerCache = [];

	function renderContainers(filter) {
		const q = (filter || '').toLowerCase();
		const list = containerCache.filter((c) => {
			if (!q) return true;
			return (c.name + ' ' + c.status + ' ' + (c.image || '')).toLowerCase().includes(q);
		});
		const rows = list.map((c) => {
			const acts = c.mutable
				? '<button type="button" data-act="restart" data-name="' + esc(c.name) + '">restart</button>' +
					'<button type="button" data-act="stop" data-name="' + esc(c.name) + '">stop</button>' +
					'<button type="button" data-act="start" data-name="' + esc(c.name) + '">start</button>' +
					'<button type="button" data-act="logs" data-name="' + esc(c.name) + '">logs</button>'
				: '<span class="nc-tower-muted">locked</span>';
			return '<tr><td>' + esc(c.name) + '</td><td>' + esc(c.status) + '</td><td>' + esc(c.cpu) + '</td><td>' +
				esc(c.mem) + '</td><td>' + esc((c.ports || []).slice(0, 3).join(', ')) + '</td><td>' + acts + '</td></tr>';
		}).join('');
		const counts = window._ncTowerCounts || {};
		const chips = '<div class="nc-tower-chips">' +
			'<span class="nc-tower-chip">running ' + esc(counts.running) + '</span>' +
			'<span class="nc-tower-chip">exited ' + esc(counts.exited) + '</span>' +
			'<span class="nc-tower-chip">total ' + esc(counts.total) + '</span></div>';
		setBody('containers', chips +
			'<table class="nc-tower-table"><thead><tr><th>Name</th><th>Status</th><th>CPU</th><th>Mem</th><th>Ports</th><th>Actions</th></tr></thead><tbody>' +
			(rows || '<tr><td colspan="6">No containers</td></tr>') + '</tbody></table>');
		document.querySelectorAll('[data-section="containers"] [data-act]').forEach((btn) => {
			btn.addEventListener('click', onContainerAct);
		});
	}

	async function onContainerAct(ev) {
		const btn = ev.currentTarget;
		const name = btn.getAttribute('data-name');
		const act = btn.getAttribute('data-act');
		if (act === 'logs') {
			try {
				const d = await apiGet('/tower/containers/' + encodeURIComponent(name) + '/logs?tail=100');
				const dlg = document.getElementById('nc-tower-logs');
				document.getElementById('nc-tower-logs-body').textContent = d.logs || '(empty)';
				dlg.showModal();
			} catch (e) { toast(e.message); }
			return;
		}
		if (!confirm(act.toUpperCase() + ' container ' + name + '?')) return;
		btn.disabled = true;
		try {
			const r = await apiPost('/tower/containers/' + encodeURIComponent(name) + '/' + act, {});
			toast(r.ok ? (name + ' → ' + (r.status || act)) : (r.error || 'failed'));
			await loadContainers();
		} catch (e) {
			toast(e.message);
		} finally {
			btn.disabled = false;
		}
	}

	async function loadContainers() {
		try {
			const d = await apiGet('/tower/containers');
			containerCache = d.containers || [];
			window._ncTowerCounts = d.counts || {};
			renderContainers(document.getElementById('nc-tower-container-filter')?.value || '');
		} catch (e) {
			setBody('containers', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
			setBanner('Sidecar unavailable or Docker error.');
		}
	}

	async function loadStacks() {
		try {
			const d = await apiGet('/tower/stacks');
			const rows = (d.stacks || []).map((s) => {
				if (!s.file) {
					return '<tr><td>' + esc(s.dir) + '</td><td colspan="4" class="nc-tower-muted">' +
						(s.exists ? 'no compose file' : 'missing dir') + '</td></tr>';
				}
				const risky = s.risky ? ' data-risky="1"' : '';
				const btns = '<button type="button" data-stack="up" data-file="' + esc(s.file) + '"' + risky + '>up</button>' +
					'<button type="button" data-stack="down" data-file="' + esc(s.file) + '"' + risky + '>down</button>';
				return '<tr><td>' + esc(s.dir) + '</td><td><code>' + esc(s.file) + '</code><div class="nc-tower-preview">' +
					esc(s.preview || '') + '</div></td><td>' + esc((s.services || []).join(', ')) +
					'</td><td>' + (s.running_hint ? 'running?' : '—') + '</td><td>' + btns + '</td></tr>';
			}).join('');
			setBody('stacks',
				'<table class="nc-tower-table"><thead><tr><th>Dir</th><th>File / preview</th><th>Services</th><th>Hint</th><th></th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">No stacks</td></tr>') + '</tbody></table>');
			document.querySelectorAll('[data-stack]').forEach((btn) => {
				btn.addEventListener('click', async () => {
					const file = btn.getAttribute('data-file');
					const action = btn.getAttribute('data-stack');
					const risky = btn.getAttribute('data-risky') === '1';
					let msg = action.toUpperCase() + ' compose\n' + file + '?';
					if (risky) msg = 'SIM/GAZEBO/SITL FILE\n' + msg + '\nType YES to confirm.';
					if (risky) {
						if (prompt(msg) !== 'YES') return;
					} else if (!confirm(msg)) return;
					btn.disabled = true;
					try {
						const r = await apiPost('/tower/stacks/' + action, { file });
						toast(r.ok ? ('stack ' + action + ' ok') : (r.error || r.stderr || 'failed'));
						await loadStacks();
						await loadContainers();
					} catch (e) { toast(e.message); }
					finally { btn.disabled = false; }
				});
			});
		} catch (e) {
			setBody('stacks', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadOps() {
		try {
			const d = await apiGet('/tower/ops-inbox');
			const b = d.backup || {};
			const cls = b.ok ? 'nc-tower-ok' : 'nc-tower-warn';
			setBody('backup',
				'<p class="' + cls + '"><strong>' + esc(b.status || '—') + '</strong> — ' + esc(b.summary || '') + '</p>' +
				'<p class="nc-tower-muted">' + esc(b.name || 'no file') + ' · ' + esc(fmtTime(b.mtime)) +
				(b.stale ? ' · stale' : '') + '</p>' +
				(d.port_audit_latest
					? '<p>Port audit: <code>' + esc(d.port_audit_latest.name) + '</code> · ' +
						esc(fmtTime(d.port_audit_latest.mtime)) + '</p>'
					: ''));
			const rows = (d.inbox_recent || []).slice(0, 25).map((x) =>
				'<tr><td>' + esc(x.name) + '</td><td>' + esc(x.monitor || '') + '</td><td>' +
				esc(x.status || '') + '</td><td>' + esc(x.detail || '') + '</td><td>' +
				esc(fmtTime(x.mtime)) + '</td></tr>').join('');
			setBody('inbox',
				'<table class="nc-tower-table"><thead><tr><th>File</th><th>Monitor</th><th>Status</th><th>Detail</th><th>When</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">Empty</td></tr>') + '</tbody></table>');
		} catch (e) {
			setBody('backup', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
			setBody('inbox', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadTools() {
		const root = document.querySelector('#nc-tower-tools .nc-tower-card__body') ||
			document.querySelector('#nc-tower-tools');
		if (!root) return;
		try {
			const d = await apiGet('/tower/tools');
			const groups = d.groups || [];
			let html = '';
			groups.forEach((g) => {
				html += '<section class="nc-tower-card"><h3>' + esc(g.title) + '</h3><div class="nc-tower-tools-grid">';
				(g.tools || []).forEach((t) => {
					if (t.url) {
						html += '<div class="nc-tower-tool-card"><a href="' + esc(t.url) + '" target="_blank" rel="noopener">' +
							esc(t.title) + '</a>' + (t.note ? '<p class="nc-tower-muted">' + esc(t.note) + '</p>' : '') + '</div>';
					} else {
						html += '<div class="nc-tower-tool-card"><strong>' + esc(t.title) + '</strong>' +
							'<p class="nc-tower-muted">' + esc(t.note || '') + '</p></div>';
					}
				});
				html += '</div></section>';
			});
			root.innerHTML = html || '<p>No tools</p>';
		} catch (e) {
			root.innerHTML = '<p class="nc-tower-error">' + esc(e.message) + '</p>';
		}
	}

	function bootOps() {
		document.getElementById('nc-tower-container-filter')?.addEventListener('input', (e) => {
			renderContainers(e.target.value);
		});
		Promise.all([
			loadHost(), loadGpu(), loadSmart(), loadFan(),
			loadContainers(), loadStacks(), loadOps(),
		]);
	}

	document.addEventListener('DOMContentLoaded', () => {
		if (document.getElementById('nc-tower-ops')) bootOps();
		if (document.getElementById('nc-tower-tools')) loadTools();
	});
})();
