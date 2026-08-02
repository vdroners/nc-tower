/**
 * Control Tower Ops / Host / Tools UI (owned; not Admin Cockpit bundle).
 */
(function () {
	'use strict';

	const BASE = OC.generateUrl('/apps/nc_tower');
	const REFRESH_MS = 12000;
	let logFollowTimer = null;
	let logFollowName = null;
	let logSince = '';

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

	/** Normalize docker ports field (API string or array) for table cells. */
	function fmtPorts(ports) {
		if (ports == null || ports === '') return '—';
		if (typeof ports === 'string') {
			const parts = ports.split(',').map((s) => s.trim()).filter(Boolean);
			return parts.slice(0, 2).join(', ') + (parts.length > 2 ? '…' : '');
		}
		if (Array.isArray(ports)) {
			return ports.slice(0, 2).map((p) => (typeof p === 'string' ? p : JSON.stringify(p))).join(', ');
		}
		return String(ports);
	}

	/** Format iface address list from {address} objects or strings. */
	function fmtAddrs(iface) {
		if (!iface) return '';
		if (typeof iface === 'string') return iface;
		const raw = iface.addresses || iface.addrs || iface.addr || [];
		if (typeof raw === 'string') return raw;
		if (!Array.isArray(raw)) return iface.address || '';
		const addrs = raw.map((a) => {
			if (typeof a === 'string') return a;
			if (a && a.address) {
				return a.prefixlen != null ? (a.address + '/' + a.prefixlen) : a.address;
			}
			return '';
		}).filter(Boolean);
		const v4 = addrs.filter((a) => a.includes('.') && !a.includes(':'));
		const show = (v4.length ? v4 : addrs).slice(0, 4);
		return show.join(', ');
	}

	function showInspect(payload) {
		const body = document.getElementById('nc-tower-inspect-body');
		const dlg = document.getElementById('nc-tower-inspect');
		if (!body || !dlg) return;
		body.textContent = JSON.stringify(payload, null, 2).slice(0, 20000);
		dlg.showModal();
	}

	let fanWired = false;
	let backupWired = false;

	async function loadHost() {
		try {
			const d = await apiGet('/tower/host');
			const disks = (d.disks || []).map((x) => {
				if (x.error) return '<li>' + esc(x.path) + ': ' + esc(x.error) + '</li>';
				return '<li><strong>' + esc(x.path) + '</strong> ' +
					esc(fmtBytes(x.used_b)) + ' / ' + esc(fmtBytes(x.total_b)) +
					' (' + esc(x.used_pct) + '% used)</li>';
			}).join('');
			const unhealthy = (d.unhealthy_containers || []).map((n) => esc(n)).join(', ') || 'none';
			const ifaces = (d.ifaces || []).slice(0, 8).map((i) => {
				if (typeof i === 'string') return esc(i);
				return esc(i.name || i.ifname || '') + ' ' + esc(fmtAddrs(i));
			}).join('; ');
			setBody('host',
				'<div class="nc-tower-chips">' +
				'<span class="nc-tower-chip">CPU ' + esc(d.cpu_pct != null ? d.cpu_pct + '%' : '—') + '</span>' +
				'<span class="nc-tower-chip">load ' + esc((d.loadavg || []).join(' / ')) + '</span>' +
				'<span class="nc-tower-chip">mem ' + esc(d.mem_available || '—') + ' avail</span>' +
				'<span class="nc-tower-chip">swap ' + esc(d.swap_available || d.swap_free || '—') + '</span>' +
				'<span class="nc-tower-chip">pkg temp ' + esc(d.package_temp_c != null ? d.package_temp_c + '°C' : '—') + '</span>' +
				'<span class="nc-tower-chip">uptime ' + esc(Math.round(d.uptime_s || 0)) + 's</span>' +
				'</div><ul>' + disks + '</ul>' +
				'<p class="nc-tower-muted">Unhealthy: ' + unhealthy + '</p>' +
				'<p class="nc-tower-muted">Ifaces: ' + (ifaces || '—') + '</p>');
		} catch (e) {
			setBody('host', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
			setBanner('Sidecar unavailable or host metrics failed — check nc_tower_sidecar + token.');
		}
	}

	async function loadDockerEngine() {
		try {
			const [info, df] = await Promise.all([
				apiGet('/tower/docker/info'),
				apiGet('/tower/docker/df'),
			]);
			const eng = info.info || info;
			let html = '<div class="nc-tower-chips">';
			html += '<span class="nc-tower-chip">server ' + esc(eng.Name || eng.name || '—') + '</span>';
			html += '<span class="nc-tower-chip">ver ' + esc(eng.ServerVersion || eng.server_version || '—') + '</span>';
			html += '<span class="nc-tower-chip">containers ' + esc(eng.Containers ?? eng.containers ?? '—') + '</span>';
			html += '<span class="nc-tower-chip">images ' + esc(eng.Images ?? eng.images ?? '—') + '</span>';
			html += '</div>';
			html += '<pre class="nc-tower-preview">' + esc(JSON.stringify(df, null, 2).slice(0, 2500)) + '</pre>';
			setBody('docker-engine', html);
		} catch (e) {
			setBody('docker-engine', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
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
				esc(g.temp_c) + '°C</td><td>' + esc(g.fan_pct) + '%</td><td>' +
				esc(g.power_draw_w != null ? g.power_draw_w
					: (g.power_w != null ? g.power_w : (g.power_draw != null ? g.power_draw : '—'))) +
				(g.power_limit_w != null ? ' / ' + esc(g.power_limit_w) : '') +
				'</td></tr>').join('');
			const procs = (d.processes || []).slice(0, 12).map((p) =>
				'<li>' + esc(p.pid || '') + ' ' + esc(p.process_name || p.name || '') +
				' ' + esc(p.used_memory_mib != null ? p.used_memory_mib + ' MiB'
					: (p.used_memory || p.mem || '')) + '</li>').join('');
			setBody('gpu', '<table class="nc-tower-table"><thead><tr><th>Name</th><th>Util</th><th>Mem</th><th>Temp</th><th>Fan</th><th>Power</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="6">No GPUs</td></tr>') + '</tbody></table>' +
				(procs ? '<ul>' + procs + '</ul>' : ''));
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
				return '<tr><td>' + esc(x.device) + '</td><td class="' + cls + '">' + esc(x.health) +
					'</td><td>' + esc(x.model || '—') + '</td><td>' + esc(x.temp_c != null ? x.temp_c + '°C' : '—') +
					'</td><td>' + esc(x.power_on_hours != null ? x.power_on_hours : '—') + '</td></tr>';
			}).join('');
			const nas = (d.nas_mounts || []).map((n) =>
				'<li>' + esc(n.path || n.mountpoint || '') + ' — ' +
				(n.ok || n.available ? '<span class="nc-tower-ok">OK</span>' : '<span class="nc-tower-error">down</span>') +
				' ' + esc(n.fstype || '') + '</li>').join('');
			setBody('smart',
				'<table class="nc-tower-table"><thead><tr><th>Device</th><th>Health</th><th>Model</th><th>Temp</th><th>Hours</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">No disks</td></tr>') + '</tbody></table>' +
				(nas ? '<h4>NAS mounts</h4><ul>' + nas + '</ul>' : '') +
				'<p class="nc-tower-muted">Full SMART attrs: Webmin → SMART Health</p>');
		} catch (e) {
			setBody('smart', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadFan(opts) {
		const soft = !!(opts && opts.soft);
		try {
			const d = await apiGet('/tower/fan');
			if (d.unavailable) {
				fanWired = false;
				setBody('fan', '<p class="nc-tower-muted">Unavailable: ' + esc(d.reason || 'n/a') +
					'. Chassis PWM writes: Webmin Fan Control.</p>');
				return;
			}
			const preview = JSON.stringify(d.status != null ? d.status : d, null, 2).slice(0, 1500);
			if (soft && fanWired) {
				const pre = document.querySelector('[data-section="fan"] .nc-tower-preview');
				if (pre) pre.textContent = preview;
				return;
			}
			let html = '<pre class="nc-tower-preview">' + esc(preview) + '</pre>';
			html += '<p><label>All fans % <input type="number" id="nc-tower-fan-speed" min="20" max="100" value="40" /></label> ';
			html += '<button type="button" id="nc-tower-fan-set">Set all (≥20%)</button> ';
			html += '<button type="button" id="nc-tower-fan-auto">Set auto</button></p>';
			setBody('fan', html);
			fanWired = true;
			document.getElementById('nc-tower-fan-set')?.addEventListener('click', async () => {
				const speed = parseInt(document.getElementById('nc-tower-fan-speed').value, 10);
				if (!confirm('Set all GPU fans to ' + speed + '%?')) return;
				try {
					const r = await apiPost('/tower/fan', { op: 'set-all-speeds', speed });
					toast(r.ok ? 'Fan speed set' : (r.error || 'failed'));
					loadFan({ soft: false });
				} catch (e) { toast(e.message); }
			});
			document.getElementById('nc-tower-fan-auto')?.addEventListener('click', async () => {
				try {
					const r = await apiPost('/tower/fan', { op: 'set-auto' });
					toast(r.ok ? 'Fan auto' : (r.error || 'failed'));
					loadFan({ soft: false });
				} catch (e) { toast(e.message); }
			});
		} catch (e) {
			fanWired = false;
			setBody('fan', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadChassisFan() {
		try {
			const d = await apiGet('/tower/chassis-fan');
			if (d.unavailable) {
				setBody('chassis-fan', '<p class="nc-tower-muted">' + esc(d.reason || 'unavailable') + '</p>');
				return;
			}
			const fans = (d.fans || d.items || []).map((f) =>
				'<tr><td>' + esc(f.name || f.label || '') + '</td><td>' + esc(f.rpm != null ? f.rpm : f.input) +
				'</td><td>' + esc(f.pwm != null ? f.pwm : '—') + '</td><td>' + esc(f.chip || f.hwmon || '') + '</td></tr>').join('');
			setBody('chassis-fan',
				'<table class="nc-tower-table"><thead><tr><th>Fan</th><th>RPM</th><th>PWM</th><th>Chip</th></tr></thead><tbody>' +
				(fans || '<tr><td colspan="4">No fans detected</td></tr>') + '</tbody></table>' +
				'<p class="nc-tower-muted">PWM/profile writes stay in Webmin Fan Control.</p>');
		} catch (e) {
			setBody('chassis-fan', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	let containerCache = [];

	function renderContainers(filter) {
		const q = (filter || '').toLowerCase();
		const list = containerCache.filter((c) => {
			if (!q) return true;
			return (c.name + ' ' + c.status + ' ' + (c.image || '') + ' ' + (c.project || '')).toLowerCase().includes(q);
		});
		const rows = list.map((c) => {
			const acts = [];
			if (c.mutable) {
				acts.push('<button type="button" data-act="restart" data-name="' + esc(c.name) + '">restart</button>');
				acts.push('<button type="button" data-act="stop" data-name="' + esc(c.name) + '">stop</button>');
				acts.push('<button type="button" data-act="start" data-name="' + esc(c.name) + '">start</button>');
				acts.push('<button type="button" data-act="kill" data-name="' + esc(c.name) + '">kill</button>');
				acts.push('<button type="button" data-act="recreate" data-name="' + esc(c.name) + '">recreate</button>');
				acts.push('<button type="button" data-act="exec" data-name="' + esc(c.name) + '">exec</button>');
			}
			if (c.loggable || c.mutable) {
				acts.push('<button type="button" data-act="logs" data-name="' + esc(c.name) + '">logs</button>');
				acts.push('<button type="button" data-act="inspect" data-name="' + esc(c.name) + '">inspect</button>');
			}
			if (!acts.length) acts.push('<span class="nc-tower-muted">locked</span>');
			return '<tr><td>' + esc(c.name) + '</td><td>' + esc(c.project || '—') + '</td><td>' + esc(c.status) +
				'</td><td>' + esc(c.cpu) + '</td><td>' + esc(c.mem) + '</td><td>' +
				esc(fmtPorts(c.ports)) + '</td><td class="nc-tower-actions">' + acts.join(' ') + '</td></tr>';
		}).join('');
		const counts = window._ncTowerCounts || {};
		const chips = '<div class="nc-tower-chips">' +
			'<span class="nc-tower-chip">running ' + esc(counts.running) + '</span>' +
			'<span class="nc-tower-chip">exited ' + esc(counts.exited) + '</span>' +
			'<span class="nc-tower-chip">total ' + esc(counts.total) + '</span></div>';
		setBody('containers', chips +
			'<table class="nc-tower-table"><thead><tr><th>Name</th><th>Project</th><th>Status</th><th>CPU</th><th>Mem</th><th>Ports</th><th>Actions</th></tr></thead><tbody>' +
			(rows || '<tr><td colspan="7">No containers</td></tr>') + '</tbody></table>');
		document.querySelectorAll('[data-section="containers"] [data-act]').forEach((btn) => {
			btn.addEventListener('click', onContainerAct);
		});
	}

	function stopLogFollow() {
		if (logFollowTimer) clearInterval(logFollowTimer);
		logFollowTimer = null;
		logFollowName = null;
		const cb = document.getElementById('nc-tower-logs-follow');
		if (cb) cb.checked = false;
	}

	async function fetchLogs(name) {
		// Tail-only poll (no wall-clock since) — avoids duplicate append / overlap on follow.
		const path = '/tower/containers/' + encodeURIComponent(name) + '/logs?tail=200';
		const d = await apiGet(path);
		const body = document.getElementById('nc-tower-logs-body');
		if (!body) return;
		body.textContent = d.logs || '(empty)';
		body.parentElement?.scrollTo?.(0, body.scrollHeight);
	}

	async function onContainerAct(ev) {
		const btn = ev.currentTarget;
		const name = btn.getAttribute('data-name');
		const act = btn.getAttribute('data-act');
		if (act === 'logs') {
			try {
				stopLogFollow();
				logFollowName = name;
				logSince = '';
				await fetchLogs(name);
				const dlg = document.getElementById('nc-tower-logs');
				dlg.showModal();
				document.getElementById('nc-tower-logs-follow').onchange = (e) => {
					if (e.target.checked) {
						logFollowTimer = setInterval(() => fetchLogs(name).catch(() => {}), 2000);
					} else {
						stopLogFollow();
						logFollowName = name;
					}
				};
				dlg.addEventListener('close', stopLogFollow, { once: true });
			} catch (e) { toast(e.message); }
			return;
		}
		if (act === 'inspect') {
			try {
				const d = await apiGet('/tower/containers/' + encodeURIComponent(name) + '/inspect');
				showInspect(d.inspect || d);
			} catch (e) { toast(e.message); }
			return;
		}
		if (act === 'exec') {
			document.getElementById('nc-tower-exec-name').textContent = name;
			document.getElementById('nc-tower-exec-out').textContent = '';
			document.getElementById('nc-tower-exec').showModal();
			document.getElementById('nc-tower-exec-form').onsubmit = async (ev2) => {
				ev2.preventDefault();
				let cmd;
				try { cmd = JSON.parse(document.getElementById('nc-tower-exec-cmd').value); }
				catch (e) { toast('cmd must be JSON array'); return; }
				try {
					const r = await apiPost('/tower/containers/' + encodeURIComponent(name) + '/exec', { cmd: cmd, timeout: 30 });
					document.getElementById('nc-tower-exec-out').textContent =
						(r.stdout || '') + (r.stderr || '') + (r.error ? '\nERR ' + r.error : '');
				} catch (e) { toast(e.message); }
			};
			document.getElementById('nc-tower-exec-close').onclick = () => {
				document.getElementById('nc-tower-exec').close();
			};
			return;
		}
		if (act === 'recreate') {
			const typed = prompt('Type RECREATE to recreate container ' + name);
			if (typed !== 'RECREATE') return;
		} else if (act === 'kill') {
			if (!confirm('KILL container ' + name + '?')) return;
		} else if (!confirm(act.toUpperCase() + ' container ' + name + '?')) {
			return;
		}
		btn.disabled = true;
		try {
			let r;
			if (act === 'recreate') {
				r = await apiPost('/tower/containers/' + encodeURIComponent(name) + '/recreate', {});
			} else {
				r = await apiPost('/tower/containers/' + encodeURIComponent(name) + '/' + act, {});
			}
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
				const btns =
					'<button type="button" data-stack="up" data-file="' + esc(s.file) + '"' + risky + '>up</button>' +
					'<button type="button" data-stack="down" data-file="' + esc(s.file) + '"' + risky + '>down</button>' +
					'<button type="button" data-stack="restart" data-file="' + esc(s.file) + '"' + risky + '>restart</button>' +
					'<button type="button" data-stack="pull" data-file="' + esc(s.file) + '"' + risky + '>pull</button>' +
					'<button type="button" data-stack="rebuild" data-file="' + esc(s.file) + '" data-risky="1">rebuild</button>';
				return '<tr><td>' + esc(s.dir) + '</td><td><code>' + esc(s.file) + '</code><div class="nc-tower-preview">' +
					esc(s.preview || '') + '</div></td><td>' + esc((s.services || []).join(', ')) +
					'</td><td>' + (s.running_hint ? 'running?' : '—') + '</td><td class="nc-tower-actions">' + btns + '</td></tr>';
			}).join('');
			setBody('stacks',
				'<table class="nc-tower-table"><thead><tr><th>Dir</th><th>File / preview</th><th>Services</th><th>Hint</th><th></th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">No stacks</td></tr>') + '</tbody></table>');
			document.querySelectorAll('[data-stack]').forEach((btn) => {
				btn.addEventListener('click', async () => {
					const file = btn.getAttribute('data-file');
					const action = btn.getAttribute('data-stack');
					const risky = btn.getAttribute('data-risky') === '1' || action === 'rebuild';
					let msg = action.toUpperCase() + ' compose\n' + file + '?';
					if (risky) {
						if (prompt(msg + '\nType YES to confirm.') !== 'YES') return;
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

	async function loadImages() {
		try {
			const prevPull = document.getElementById('nc-tower-image-pull')?.value || '';
			const d = await apiGet('/tower/docker/images');
			const imgs = d.images || d || [];
			const list = Array.isArray(imgs) ? imgs : [];
			const rows = list.slice(0, 80).map((img) => {
				const repo = img.Repository || img.repository || img.RepoTags || img.ID || '';
				const tag = img.Tag || img.tag || '';
				const id = (img.ID || img.Id || '').toString().slice(0, 12);
				const size = img.Size || img.size || '';
				const ref = (typeof repo === 'string' ? repo : '') + (tag && tag !== '<none>' ? ':' + tag : '');
				return '<tr><td>' + esc(ref || id) + '</td><td>' + esc(id) + '</td><td>' + esc(size) +
					'</td><td><button type="button" data-pull="' + esc(ref) + '">pull</button></td></tr>';
			}).join('');
			setBody('images',
				'<p><input type="text" id="nc-tower-image-pull" placeholder="image:tag" style="width:60%" /> ' +
				'<button type="button" id="nc-tower-image-pull-btn">Pull</button></p>' +
				'<table class="nc-tower-table"><thead><tr><th>Ref</th><th>ID</th><th>Size</th><th></th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="4">No images</td></tr>') + '</tbody></table>');
			const pullInput = document.getElementById('nc-tower-image-pull');
			if (pullInput && prevPull) pullInput.value = prevPull;
			const doPull = async (image) => {
				if (!image) return;
				if (!confirm('Pull image ' + image + '?')) return;
				try {
					const r = await apiPost('/tower/docker/images/pull', { image });
					toast(r.ok ? 'pull ok' : (r.error || 'failed'));
					loadImages();
				} catch (e) { toast(e.message); }
			};
			document.getElementById('nc-tower-image-pull-btn')?.addEventListener('click', () => {
				doPull(document.getElementById('nc-tower-image-pull').value.trim());
			});
			document.querySelectorAll('[data-pull]').forEach((b) => {
				b.addEventListener('click', () => doPull(b.getAttribute('data-pull')));
			});
		} catch (e) {
			setBody('images', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadVolumes() {
		try {
			const d = await apiGet('/tower/docker/volumes');
			const vols = d.volumes || d.Volumes || [];
			const list = Array.isArray(vols) ? vols : [];
			const rows = list.slice(0, 80).map((v) => {
				const name = v.Name || v.name || '';
				return '<tr><td>' + esc(name) + '</td><td>' + esc(v.Driver || v.driver || '') +
					'</td><td>' + esc(v.Mountpoint || v.mountpoint || '') +
					'</td><td><button type="button" data-vol-inspect="' + esc(name) + '">inspect</button></td></tr>';
			}).join('');
			setBody('volumes',
				'<table class="nc-tower-table"><thead><tr><th>Name</th><th>Driver</th><th>Mountpoint</th><th></th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="4">No volumes</td></tr>') + '</tbody></table>');
			document.querySelectorAll('[data-vol-inspect]').forEach((btn) => {
				btn.addEventListener('click', async () => {
					const name = btn.getAttribute('data-vol-inspect');
					try {
						const r = await apiGet('/tower/docker/volumes?name=' + encodeURIComponent(name));
						showInspect(r.volume || r.inspect || r);
					} catch (e) { toast(e.message); }
				});
			});
		} catch (e) {
			setBody('volumes', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadNetworks() {
		try {
			const d = await apiGet('/tower/docker/networks');
			const nets = d.networks || d || [];
			const list = Array.isArray(nets) ? nets : [];
			const rows = list.map((n) => {
				const name = n.Name || n.name || '';
				return '<tr><td>' + esc(name) + '</td><td>' + esc(n.Driver || n.driver || '') +
					'</td><td>' + esc(n.Scope || n.scope || '') + '</td><td>' +
					esc((n.ID || n.Id || '').toString().slice(0, 12)) +
					'</td><td><button type="button" data-net-inspect="' + esc(name) + '">inspect</button></td></tr>';
			}).join('');
			setBody('networks',
				'<table class="nc-tower-table"><thead><tr><th>Name</th><th>Driver</th><th>Scope</th><th>ID</th><th></th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">No networks</td></tr>') + '</tbody></table>');
			document.querySelectorAll('[data-net-inspect]').forEach((btn) => {
				btn.addEventListener('click', async () => {
					const name = btn.getAttribute('data-net-inspect');
					try {
						const r = await apiGet('/tower/docker/networks?name=' + encodeURIComponent(name));
						showInspect(r.network || r.inspect || r);
					} catch (e) { toast(e.message); }
				});
			});
		} catch (e) {
			setBody('networks', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadEvents() {
		try {
			const d = await apiGet('/tower/docker/events?since=15m');
			const ev = d.events || d.items || [];
			const list = Array.isArray(ev) ? ev : [];
			const rows = list.slice(-80).reverse().map((e) => {
				let t = e.time || e.Time;
				if (t == null && e.timeNano) t = Math.floor(Number(e.timeNano) / 1e9);
				const when = (typeof t === 'number' || (typeof t === 'string' && /^\d+$/.test(t)))
					? fmtTime(Number(t))
					: String(t || '—');
				return '<tr><td>' + esc(when) + '</td><td>' + esc(e.Type || e.type || '') +
					'</td><td>' + esc(e.Action || e.action || '') + '</td><td>' +
					esc(e.Actor?.Attributes?.name || e.name || JSON.stringify(e.Actor || {}).slice(0, 80)) +
					'</td></tr>';
			}).join('');
			setBody('events',
				'<table class="nc-tower-table"><thead><tr><th>Time</th><th>Type</th><th>Action</th><th>Target</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="4">No recent events</td></tr>') + '</tbody></table>');
		} catch (e) {
			setBody('events', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadOps(opts) {
		const soft = !!(opts && opts.soft);
		try {
			const d = await apiGet('/tower/ops-inbox');
			const b = d.backup || {};
			const cls = b.ok ? 'nc-tower-ok' : 'nc-tower-warn';
			const statusHtml =
				'<p class="' + cls + '"><strong>' + esc(b.status || '—') + '</strong> — ' + esc(b.summary || '') + '</p>' +
				'<p class="nc-tower-muted">' + esc(b.name || 'no file') + ' · ' + esc(fmtTime(b.mtime)) +
				(b.stale ? ' · stale' : '') + '</p>';
			if (soft && backupWired && document.getElementById('nc-tower-backup-run')) {
				const root = document.querySelector('[data-section="backup"] .nc-tower-card__body');
				if (root) {
					const btnRow = root.querySelector('#nc-tower-backup-run')?.parentElement;
					root.innerHTML = statusHtml +
						'<p><button type="button" id="nc-tower-backup-run">Run backup now</button> ' +
						'<span class="nc-tower-muted">Delete backups stays in Webmin.</span></p>';
					document.getElementById('nc-tower-backup-run')?.addEventListener('click', async () => {
						if (!confirm('Run allowlisted backup script now? This may take several minutes.')) return;
						try {
							const r = await apiPost('/tower/backup/run', {});
							toast(r.ok ? 'Backup started/finished ok' : (r.error || 'failed'));
							loadOps({ soft: false });
						} catch (e) { toast(e.message); }
					});
					void btnRow;
				}
			} else {
				setBody('backup',
					statusHtml +
					'<p><button type="button" id="nc-tower-backup-run">Run backup now</button> ' +
					'<span class="nc-tower-muted">Delete backups stays in Webmin.</span></p>');
				backupWired = true;
				document.getElementById('nc-tower-backup-run')?.addEventListener('click', async () => {
					if (!confirm('Run allowlisted backup script now? This may take several minutes.')) return;
					try {
						const r = await apiPost('/tower/backup/run', {});
						toast(r.ok ? 'Backup started/finished ok' : (r.error || 'failed'));
						loadOps({ soft: false });
					} catch (e) { toast(e.message); }
				});
			}
			const crit = (d.critical_recent || []).map((x) =>
				'<tr class="nc-tower-error"><td>' + esc(x.name) + '</td><td>' + esc(x.monitor || '') +
				'</td><td>' + esc(x.status || '') + '</td><td>' + esc(x.detail || '') +
				'</td><td>' + esc(fmtTime(x.mtime)) + '</td></tr>').join('');
			const rows = (d.inbox_recent || []).slice(0, 25).map((x) =>
				'<tr><td>' + esc(x.name) + '</td><td>' + esc(x.monitor || '') + '</td><td>' +
				esc(x.status || '') + '</td><td>' + esc(x.detail || '') + '</td><td>' +
				esc(fmtTime(x.mtime)) + '</td></tr>').join('');
			setBody('inbox',
				(crit ? '<h4>CRITICAL</h4><table class="nc-tower-table"><thead><tr><th>File</th><th>Monitor</th><th>Status</th><th>Detail</th><th>When</th></tr></thead><tbody>' +
					crit + '</tbody></table>' : '') +
				'<table class="nc-tower-table"><thead><tr><th>File</th><th>Monitor</th><th>Status</th><th>Detail</th><th>When</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">Empty</td></tr>') + '</tbody></table>');
		} catch (e) {
			backupWired = false;
			setBody('backup', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
			setBody('inbox', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	/* —— Host tab —— */
	async function loadHostMounts() {
		try {
			const d = await apiGet('/tower/mounts');
			const rows = (d.mounts || d.items || []).map((m) =>
				'<tr><td>' + esc(m.target || m.mountpoint || m.path) + '</td><td>' + esc(m.source || m.device || '') +
				'</td><td>' + esc(m.fstype || m.type || '') + '</td><td>' +
				esc(m.used_pct != null ? m.used_pct + '%' : (m.usage || '—')) + '</td></tr>').join('');
			setBody('host-mounts',
				'<table class="nc-tower-table"><thead><tr><th>Mount</th><th>Source</th><th>FS</th><th>Used</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="4">None</td></tr>') + '</tbody></table>');
		} catch (e) {
			setBody('host-mounts', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadHostPackages() {
		try {
			const d = await apiGet('/tower/packages');
			if (d.unavailable) {
				setBody('host-packages', '<p class="nc-tower-muted">' + esc(d.reason || 'unavailable') + '</p>');
				return;
			}
			const pkgs = d.packages || d.upgradable || [];
			const rows = pkgs.slice(0, 60).map((p) => {
				if (typeof p === 'string') return '<tr><td colspan="2">' + esc(p) + '</td></tr>';
				return '<tr><td>' + esc(p.name || p.package) + '</td><td>' +
					esc(p.new_version || p.version || p.candidate || '') + '</td></tr>';
			}).join('');
			setBody('host-packages',
				'<p class="nc-tower-chip">' + esc(d.count != null ? d.count : pkgs.length) + ' upgradable</p>' +
				'<table class="nc-tower-table"><thead><tr><th>Package</th><th>Version</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="2">None</td></tr>') + '</tbody></table>');
		} catch (e) {
			setBody('host-packages', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadHostProc() {
		try {
			const d = await apiGet('/tower/proc');
			const rows = (d.processes || d.items || []).map((p) =>
				'<tr><td>' + esc(p.pid || '') + '</td><td>' + esc(p.user || p.USER || '') +
				'</td><td>' + esc(p.cpu || p['%CPU'] || '') + '</td><td>' + esc(p.mem || p['%MEM'] || '') +
				'</td><td>' + esc(p.command || p.CMD || p.cmd || '') + '</td></tr>').join('');
			setBody('host-proc',
				'<table class="nc-tower-table"><thead><tr><th>PID</th><th>User</th><th>CPU</th><th>Mem</th><th>Command</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="5">None</td></tr>') + '</tbody></table>' +
				'<p class="nc-tower-muted">Kill stays out of Tower.</p>');
		} catch (e) {
			setBody('host-proc', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadHostSystemd() {
		try {
			const d = await apiGet('/tower/systemd');
			const rows = (d.units || d.items || []).map((u) =>
				'<tr><td>' + esc(u.unit || u.name) + '</td><td>' + esc(u.active || u.state || '') +
				'</td><td>' + esc(u.enabled || '') + '</td><td>' +
				(u.restartable !== false
					? '<button type="button" data-unit="' + esc(u.unit || u.name) + '">restart</button>'
					: '') + '</td></tr>').join('');
			setBody('host-systemd',
				'<table class="nc-tower-table"><thead><tr><th>Unit</th><th>Active</th><th>Enabled</th><th></th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="4">None</td></tr>') + '</tbody></table>');
			document.querySelectorAll('[data-section="host-systemd"] [data-unit]').forEach((btn) => {
				btn.addEventListener('click', async () => {
					const unit = btn.getAttribute('data-unit');
					if (!confirm('Restart ' + unit + '?')) return;
					try {
						const r = await apiPost('/tower/systemd/restart', { unit });
						toast(r.ok ? 'restarted ' + unit : (r.error || 'failed'));
						loadHostSystemd();
					} catch (e) { toast(e.message); }
				});
			});
		} catch (e) {
			setBody('host-systemd', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadHostCron() {
		try {
			const d = await apiGet('/tower/cron');
			const lines = (d.root_crontab || d.crontab || []).map((l) => '<li><code>' + esc(l) + '</code></li>').join('');
			const files = (d.cron_d_files || d.cron_d || d.files || []).map((f) => '<li>' + esc(f) + '</li>').join('');
			setBody('host-cron',
				'<h4>root crontab</h4><ul>' + (lines || '<li class="nc-tower-muted">empty</li>') + '</ul>' +
				'<h4>/etc/cron.d</h4><ul>' + (files || '<li class="nc-tower-muted">none</li>') + '</ul>' +
				'<p class="nc-tower-muted">Edits stay in Webmin.</p>');
		} catch (e) {
			setBody('host-cron', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
		}
	}

	async function loadHostNet() {
		try {
			const d = await apiGet('/tower/net');
			const rows = (d.ifaces || d.interfaces || []).map((i) =>
				'<tr><td>' + esc(i.name || i.ifname) + '</td><td>' +
				esc(fmtAddrs(i)) +
				'</td><td>' + esc(i.state || i.operstate || '') + '</td></tr>').join('');
			setBody('host-net',
				'<table class="nc-tower-table"><thead><tr><th>Iface</th><th>Addrs</th><th>State</th></tr></thead><tbody>' +
				(rows || '<tr><td colspan="3">None</td></tr>') + '</tbody></table>');
		} catch (e) {
			setBody('host-net', '<p class="nc-tower-error">' + esc(e.message) + '</p>');
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
		const loadOnce = () => Promise.all([
			loadHost(), loadDockerEngine(), loadGpu(), loadSmart(), loadFan({ soft: false }), loadChassisFan(),
			loadContainers(), loadStacks(), loadImages(), loadVolumes(), loadNetworks(),
			loadEvents(), loadOps({ soft: false }),
		]);
		// Tick: refresh tables/chips; soft-update fan/backup so forms are not rebuilt every 12s.
		const loadTick = () => Promise.all([
			loadHost(), loadDockerEngine(), loadGpu(), loadSmart(), loadFan({ soft: true }), loadChassisFan(),
			loadContainers(), loadStacks(), loadImages(), loadVolumes(), loadNetworks(),
			loadEvents(), loadOps({ soft: true }),
		]);
		loadOnce();
		setInterval(loadTick, REFRESH_MS);
	}

	function bootHost() {
		const loadAll = () => Promise.all([
			loadHostMounts(), loadHostPackages(), loadHostProc(),
			loadHostSystemd(), loadHostCron(), loadHostNet(),
		]);
		loadAll();
		setInterval(loadAll, REFRESH_MS);
	}

	document.addEventListener('DOMContentLoaded', () => {
		if (document.getElementById('nc-tower-ops')) bootOps();
		if (document.getElementById('nc-tower-host')) bootHost();
		if (document.getElementById('nc-tower-tools')) loadTools();
	});
})();
