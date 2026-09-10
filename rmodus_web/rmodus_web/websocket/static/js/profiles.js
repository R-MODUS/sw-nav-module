/* === PROFILY (config page) === */

(function () {
    let selectedName = null;
    let dirty = false;
    let listCache = null;

    function uiCfg() {
        return (typeof window.__RMODUS_UI_CONFIG__ === 'object' && window.__RMODUS_UI_CONFIG__)
            ? window.__RMODUS_UI_CONFIG__
            : {};
    }

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

    function setStatus(msg, isError) {
        const el = document.getElementById('profiles-status');
        if (!el) return;
        el.textContent = msg || '';
        el.classList.toggle('profiles-status-error', !!isError);
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

    function renderList(data) {
        listCache = data;
        const rootLabel = document.getElementById('profiles-root-label');
        if (rootLabel && data.configs_root) {
            rootLabel.textContent = data.configs_root;
        }
        const list = document.getElementById('profiles-list');
        if (!list) return;
        list.innerHTML = '';
        if (!data.profiles || !data.profiles.length) {
            list.innerHTML = '<p class="profiles-hint">Žádné profily v profiles/.</p>';
            return;
        }
        data.profiles.forEach((p) => {
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'surface-list-item profiles-list-item'
                + (p.name === selectedName ? ' is-selected' : '')
                + (p.active ? ' is-active' : '');
            row.innerHTML = `
                <span class="profiles-list-name">${escapeHtml(p.name)}</span>
                ${p.active ? '<span class="profiles-badge">aktivní</span>' : ''}
            `;
            row.addEventListener('click', () => openProfile(p.name));
            list.appendChild(row);
        });
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function refreshList() {
        setStatus('Načítám seznam…');
        try {
            const data = await api('/api/profiles');
            renderList(data);
            setStatus(data.active
                ? `Aktivní profil: ${data.active}`
                : 'Není nastaven aktivní profil.');
        } catch (err) {
            setStatus(err.message || String(err), true);
        }
    }

    async function openProfile(name) {
        if (dirty && !confirm('Máš neuložené změny. Opravdu přepnout profil?')) {
            return;
        }
        selectedName = name;
        setStatus(`Načítám ${name}…`);
        try {
            const data = await api(`/api/profiles/${encodeURIComponent(name)}`);
            const editor = document.getElementById('config-editor');
            const title = document.getElementById('profiles-editor-title');
            const pathEl = document.getElementById('profiles-editor-path');
            if (editor) {
                editor.value = data.content || '';
                editor.disabled = false;
            }
            if (title) {
                title.textContent = data.active ? `${data.name} (aktivní)` : data.name;
            }
            if (pathEl) pathEl.textContent = data.path || '';
            dirty = false;
            setEditorButtons(true, !!data.active);
            if (listCache) renderList(listCache);
            setStatus(data.active
                ? `Otevřen aktivní profil ${data.name}`
                : `Otevřen profil ${data.name}`);
        } catch (err) {
            setStatus(err.message || String(err), true);
        }
    }

    function setEditorButtons(enabled, isActive) {
        const saveBtn = document.getElementById('profiles-save-btn');
        const actBtn = document.getElementById('profiles-activate-btn');
        const delBtn = document.getElementById('profiles-delete-btn');
        if (saveBtn) saveBtn.disabled = !enabled;
        if (actBtn) actBtn.disabled = !enabled || !!isActive;
        if (delBtn) delBtn.disabled = !enabled || !!isActive;
    }

    async function saveSelected() {
        if (!selectedName) return;
        const editor = document.getElementById('config-editor');
        if (!editor) return;
        setStatus('Ukládám…');
        try {
            await api(`/api/profiles/${encodeURIComponent(selectedName)}`, {
                method: 'PUT',
                body: JSON.stringify({ content: editor.value }),
            });
            dirty = false;
            setStatus(`Uloženo: ${selectedName}`);
            await refreshList();
        } catch (err) {
            setStatus(err.message || String(err), true);
        }
    }

    async function activateSelected() {
        if (!selectedName) return;
        if (!confirm(`Aktivovat profil „${selectedName}“?\nBringup se načte až po restartu služby.`)) {
            return;
        }
        setStatus('Aktivuji…');
        try {
            const res = await api(`/api/profiles/${encodeURIComponent(selectedName)}/activate`, {
                method: 'POST',
                body: '{}',
            });
            setStatus(res.message || `Aktivní: ${selectedName}`);
            await refreshList();
            await openProfile(selectedName);
            dirty = false;
        } catch (err) {
            setStatus(err.message || String(err), true);
        }
    }

    async function deleteSelected() {
        if (!selectedName) return;
        if (!confirm(`Smazat profil „${selectedName}“? Tuto akci nelze vrátit.`)) {
            return;
        }
        setStatus('Mažu…');
        try {
            await api(`/api/profiles/${encodeURIComponent(selectedName)}`, { method: 'DELETE' });
            selectedName = null;
            dirty = false;
            const editor = document.getElementById('config-editor');
            const title = document.getElementById('profiles-editor-title');
            const pathEl = document.getElementById('profiles-editor-path');
            if (editor) {
                editor.value = '';
                editor.disabled = true;
            }
            if (title) title.textContent = 'Vyber profil';
            if (pathEl) pathEl.textContent = '';
            setEditorButtons(false, false);
            setStatus('Profil smazán.');
            await refreshList();
        } catch (err) {
            setStatus(err.message || String(err), true);
        }
    }

    async function createProfile() {
        const name = prompt('Jméno nového profilu (bez .yaml):');
        if (!name || !name.trim()) return;
        const sourceDefault = selectedName || (listCache && listCache.active) || '';
        const source = prompt(
            'Zkopírovat z profilu (prázdné = aktivní / minimální stub):',
            sourceDefault
        );
        setStatus('Vytvářím…');
        try {
            const body = { name: name.trim() };
            if (source && source.trim()) body.source = source.trim();
            const res = await api('/api/profiles', {
                method: 'POST',
                body: JSON.stringify(body),
            });
            dirty = false;
            setStatus(`Vytvořeno: ${res.name}`);
            await refreshList();
            await openProfile(res.name);
        } catch (err) {
            setStatus(err.message || String(err), true);
        }
    }

    window.initProfilesPage = async function initProfilesPage() {
        const rootHint = uiCfg().configs_root;
        const rootLabel = document.getElementById('profiles-root-label');
        if (rootLabel && rootHint) rootLabel.textContent = rootHint;

        document.getElementById('profiles-refresh-btn')?.addEventListener('click', refreshList);
        document.getElementById('profiles-create-btn')?.addEventListener('click', createProfile);
        document.getElementById('profiles-save-btn')?.addEventListener('click', saveSelected);
        document.getElementById('profiles-activate-btn')?.addEventListener('click', activateSelected);
        document.getElementById('profiles-delete-btn')?.addEventListener('click', deleteSelected);
        document.getElementById('config-editor')?.addEventListener('input', () => {
            dirty = true;
        });

        selectedName = null;
        dirty = false;
        setEditorButtons(false, false);
        await refreshList();
        if (listCache && listCache.active) {
            await openProfile(listCache.active);
            dirty = false;
        }
    };
})();
