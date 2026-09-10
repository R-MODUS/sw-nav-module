/* === NASTAVENÍ / SÍŤ === */

(function () {
    let loaded = null;

    function adminHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        try {
            const pin = localStorage.getItem('robot_admin_token');
            if (pin) headers['X-Admin-Pin'] = pin;
        } catch (_e) {
            /* ignore */
        }
        return headers;
    }

    function reportError(err) {
        const msg = (err && err.message) ? err.message : String(err || 'Chyba');
        console.error(msg);
        alert(msg);
    }

    async function api(path, options) {
        const opts = options || {};
        const res = await fetch(path, {
            ...opts,
            headers: { ...adminHeaders(), ...(opts.headers || {}) },
        });
        let body = null;
        try {
            body = await res.json();
        } catch (_e) {
            body = null;
        }
        if (!res.ok) {
            const detail = body && (body.detail || body.message);
            throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`);
        }
        return body;
    }

    function pwHint(elId, set) {
        const el = document.getElementById(elId);
        if (!el) return;
        el.textContent = set ? '(uloženo)' : '(nenastaveno)';
    }

    function clientRowHtml(entry, index) {
        const ssid = entry && entry.ssid ? String(entry.ssid) : '';
        const hidden = !!(entry && entry.hidden);
        const set = !!(entry && (entry.password_set || entry.psk_set));
        return `
            <div class="panel panel-pad stack network-client-row" data-index="${index}">
                <div class="profiles-editor-head">
                    <strong>Síť #${index + 1}</strong>
                    <button type="button" class="btn btn-danger network-remove-client">Odebrat</button>
                </div>
                <div class="grid-2">
                    <label class="network-field">
                        <span>SSID</span>
                        <input type="text" class="net-client-ssid" value="${escapeAttr(ssid)}">
                    </label>
                    <label class="network-field">
                        <span>Heslo ${set ? '<small>(uloženo)</small>' : '<small>(nenastaveno)</small>'}</span>
                        <input type="password" class="net-client-password" placeholder="beze změny" autocomplete="new-password">
                    </label>
                    <label class="network-field network-check">
                        <input type="checkbox" class="net-client-hidden" ${hidden ? 'checked' : ''}>
                        <span>Skryté SSID</span>
                    </label>
                </div>
            </div>
        `;
    }

    function escapeAttr(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;');
    }

    function renderClients(networks) {
        const list = document.getElementById('net-client-list');
        if (!list) return;
        const items = Array.isArray(networks) ? networks : [];
        if (!items.length) {
            list.innerHTML = '<p class="profiles-hint">Žádné client sítě — přidej aspoň jednu pro mode=client.</p>';
            return;
        }
        list.innerHTML = items.map((n, i) => clientRowHtml(n, i)).join('');
        list.querySelectorAll('.network-remove-client').forEach((btn) => {
            btn.addEventListener('click', () => {
                const row = btn.closest('.network-client-row');
                row?.remove();
                reindexClients();
            });
        });
    }

    function reindexClients() {
        const list = document.getElementById('net-client-list');
        if (!list) return;
        const rows = [...list.querySelectorAll('.network-client-row')];
        if (!rows.length) {
            list.innerHTML = '<p class="profiles-hint">Žádné client sítě — přidej aspoň jednu pro mode=client.</p>';
            return;
        }
        rows.forEach((row, i) => {
            row.dataset.index = String(i);
            const title = row.querySelector('strong');
            if (title) title.textContent = `Síť #${i + 1}`;
        });
    }

    function collectClients() {
        const list = document.getElementById('net-client-list');
        if (!list) return [];
        return [...list.querySelectorAll('.network-client-row')].map((row) => {
            const ssid = row.querySelector('.net-client-ssid')?.value?.trim() || '';
            const password = row.querySelector('.net-client-password')?.value || '';
            const hidden = !!row.querySelector('.net-client-hidden')?.checked;
            return { ssid, password, hidden };
        }).filter((n) => n.ssid);
    }

    function fillForm(config) {
        const net = (config && config.network) || {};
        const ap = net.ap || {};
        const fb = net.fallback_ap || {};

        const modeEl = document.getElementById('net-mode');
        if (modeEl) modeEl.value = net.mode || 'client';

        const country = document.getElementById('net-country');
        if (country) country.value = net.country || 'CZ';

        const domain = document.getElementById('net-ros-domain');
        if (domain) domain.value = net.ros_domain_id != null ? net.ros_domain_id : 0;

        document.getElementById('net-ap-ssid').value = ap.ssid || '';
        document.getElementById('net-ap-password').value = '';
        document.getElementById('net-ap-address').value = ap.address || '192.168.50.1/24';
        document.getElementById('net-ap-hidden').checked = !!ap.hidden;
        pwHint('net-ap-pw-hint', !!ap.password_set);

        document.getElementById('net-fb-enabled').checked = fb.enabled !== false;
        document.getElementById('net-fb-timeout').value = fb.timeout != null ? fb.timeout : 60;
        document.getElementById('net-fb-ssid').value = fb.ssid || '';
        document.getElementById('net-fb-password').value = '';
        document.getElementById('net-fb-hidden').checked = !!fb.hidden;
        pwHint('net-fb-pw-hint', !!fb.password_set);

        renderClients(net.networks || []);
        updateModeVisibility();
    }

    function updateModeVisibility() {
        const mode = document.getElementById('net-mode')?.value || 'client';
        const client = document.getElementById('net-client-section');
        const ap = document.getElementById('net-ap-section');
        if (client) client.style.display = mode === 'ethernet' ? 'none' : '';
        if (ap) ap.style.display = mode === 'ethernet' ? 'none' : '';
    }

    function buildPayload() {
        const prevBoot = (loaded && loaded.boot) || {};
        return {
            boot: {
                network: prevBoot.network !== false,
            },
            network: {
                mode: document.getElementById('net-mode')?.value || 'client',
                country: (document.getElementById('net-country')?.value || 'CZ').trim().toUpperCase(),
                ros_domain_id: Number(document.getElementById('net-ros-domain')?.value || 0),
                networks: collectClients(),
                ap: {
                    ssid: document.getElementById('net-ap-ssid')?.value?.trim() || '',
                    password: document.getElementById('net-ap-password')?.value || '',
                    address: document.getElementById('net-ap-address')?.value?.trim() || '',
                    hidden: !!document.getElementById('net-ap-hidden')?.checked,
                },
                fallback_ap: {
                    enabled: !!document.getElementById('net-fb-enabled')?.checked,
                    timeout: Number(document.getElementById('net-fb-timeout')?.value || 60),
                    ssid: document.getElementById('net-fb-ssid')?.value?.trim() || '',
                    password: document.getElementById('net-fb-password')?.value || '',
                    hidden: !!document.getElementById('net-fb-hidden')?.checked,
                },
            },
        };
    }

    async function reload() {
        try {
            const data = await api('/api/network');
            loaded = data.config || {};
            const pathLabel = document.getElementById('network-path-label');
            if (pathLabel && data.path) {
                pathLabel.textContent = 'Nastavení připojení';
                pathLabel.title = data.path;
                pathLabel.dataset.path = data.path;
            }
            fillForm(loaded);
        } catch (err) {
            reportError(err);
        }
    }

    async function save(apply) {
        const payload = buildPayload();
        if (apply) {
            if (!confirm(
                'Uložit network.yaml a použít síť teď?\n'
                + 'Můžeš ztratit Wi‑Fi spojení s robotem.'
            )) {
                return;
            }
        }
        try {
            const res = await api('/api/network', {
                method: 'PUT',
                body: JSON.stringify({ config: payload, apply: !!apply }),
            });
            alert(res.message || (apply ? 'Uloženo a apply naplánován.' : 'Uloženo.'));
            await reload();
        } catch (err) {
            reportError(err);
        }
    }

    async function applyOnly() {
        if (!confirm(
            'Spustit rmodus-network apply podle uloženého network.yaml?\n'
            + 'Můžeš ztratit Wi‑Fi spojení.'
        )) {
            return;
        }
        try {
            const res = await api('/api/network/apply', { method: 'POST', body: '{}' });
            alert(res.message || 'Apply naplánován.');
        } catch (err) {
            reportError(err);
        }
    }

    async function rebootHost() {
        if (!confirm(
            'Opravdu restartovat celé zařízení?\n'
            + 'Web i SSH se odpojí.'
        )) {
            return;
        }
        const btn = document.getElementById('system-reboot-btn');
        if (btn) btn.disabled = true;
        try {
            await api('/api/system/reboot', { method: 'POST', body: '{}' });
        } catch (err) {
            reportError(err);
            if (btn) btn.disabled = false;
        }
    }

    window.initSettingsPage = async function initSettingsPage() {
        document.getElementById('network-reload-btn')?.addEventListener('click', reload);
        document.getElementById('network-save-btn')?.addEventListener('click', (e) => {
            e.preventDefault();
            save(false);
        });
        document.getElementById('network-apply-btn')?.addEventListener('click', (e) => {
            e.preventDefault();
            applyOnly();
        });
        document.getElementById('system-reboot-btn')?.addEventListener('click', (e) => {
            e.preventDefault();
            rebootHost();
        });
        document.getElementById('network-path-label')?.addEventListener('click', async (e) => {
            e.preventDefault();
            const path = e.currentTarget.dataset.path || e.currentTarget.title || '';
            if (!path) return;
            try {
                await navigator.clipboard.writeText(path);
            } catch (_err) {
                window.prompt('Cesta k network.yaml:', path);
            }
        });
        document.getElementById('net-mode')?.addEventListener('change', updateModeVisibility);
        document.getElementById('net-add-client-btn')?.addEventListener('click', () => {
            const list = document.getElementById('net-client-list');
            if (!list) return;
            const hint = list.querySelector('.profiles-hint');
            if (hint) hint.remove();
            const wrap = document.createElement('div');
            wrap.innerHTML = clientRowHtml({ ssid: '', password_set: false }, list.querySelectorAll('.network-client-row').length);
            const row = wrap.firstElementChild;
            list.appendChild(row);
            row.querySelector('.network-remove-client')?.addEventListener('click', () => {
                row.remove();
                reindexClients();
            });
        });
        await reload();
    };
})();
