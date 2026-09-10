/* === PROFILY (config page) === */

(function () {
    const CM_BASE = 'static/vendor/codemirror';
    const CM_ASSETS = [
        { type: 'css', href: `${CM_BASE}/codemirror.min.css` },
        { type: 'css', href: `${CM_BASE}/material-darker.min.css` },
        { type: 'js', src: `${CM_BASE}/codemirror.min.js` },
        { type: 'js', src: `${CM_BASE}/yaml.min.js` },
    ];

    let selectedName = null;
    let selectedActive = false;
    let loadedContent = '';
    let dirty = false;
    let editing = false;
    let listCache = null;
    let cm = null;
    let cmReady = null;

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

    function reportError(err) {
        const msg = (err && err.message) ? err.message : String(err || 'Chyba');
        console.error(msg);
        alert(msg);
    }

    function loadAsset(asset) {
        return new Promise((resolve, reject) => {
            if (asset.type === 'css') {
                if (document.querySelector(`link[href="${asset.href}"]`)) {
                    resolve();
                    return;
                }
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = asset.href;
                link.onload = () => resolve();
                link.onerror = () => reject(new Error(`CSS ${asset.href}`));
                document.head.appendChild(link);
                return;
            }
            if (document.querySelector(`script[src="${asset.src}"]`)) {
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.src = asset.src;
            script.async = false;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error(`JS ${asset.src}`));
            document.head.appendChild(script);
        });
    }

    async function ensureCodeMirror() {
        if (window.CodeMirror) return true;
        if (!cmReady) {
            cmReady = (async () => {
                try {
                    for (const asset of CM_ASSETS) {
                        await loadAsset(asset);
                    }
                    return !!window.CodeMirror;
                } catch (err) {
                    console.warn('CodeMirror se nenačetl, fallback na textarea:', err);
                    return false;
                }
            })();
        }
        return cmReady;
    }

    function getEditorText() {
        if (cm) return cm.getValue();
        const ta = document.getElementById('config-editor');
        return ta ? ta.value : '';
    }

    function setEditorText(text) {
        if (cm) {
            cm.setValue(text || '');
            cm.clearHistory();
            return;
        }
        const ta = document.getElementById('config-editor');
        if (ta) ta.value = text || '';
    }

    function markDirty() {
        if (!editing) return;
        dirty = getEditorText() !== loadedContent;
        updateChrome();
    }

    async function ensureEditorMounted() {
        const ta = document.getElementById('config-editor');
        if (!ta) return;
        if (cm) {
            // CodeMirror instance is tied to previous DOM after SPA page reload.
            try {
                cm.toTextArea();
            } catch (_e) {
                /* ignore */
            }
            cm = null;
        }
        const ok = await ensureCodeMirror();
        if (!ok || !window.CodeMirror) return;
        cm = window.CodeMirror.fromTextArea(ta, {
            mode: 'yaml',
            theme: 'material-darker',
            lineNumbers: true,
            lineWrapping: true,
            indentUnit: 2,
            tabSize: 2,
            readOnly: true,
            viewportMargin: Infinity,
        });
        cm.on('change', markDirty);
        cm.setSize('100%', '52vh');
    }

    function closeMoreMenu() {
        const menu = document.getElementById('profiles-more-menu');
        const btn = document.getElementById('profiles-more-btn');
        if (menu) menu.hidden = true;
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }

    function toggleMoreMenu() {
        const menu = document.getElementById('profiles-more-menu');
        const btn = document.getElementById('profiles-more-btn');
        if (!menu || !btn || btn.disabled) return;
        const open = menu.hidden;
        menu.hidden = !open;
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function updateChrome() {
        const has = !!selectedName;
        const editBtn = document.getElementById('profiles-edit-btn');
        const saveBtn = document.getElementById('profiles-save-btn');
        const cancelBtn = document.getElementById('profiles-cancel-btn');
        const actBtn = document.getElementById('profiles-activate-btn');
        const moreBtn = document.getElementById('profiles-more-btn');
        const delBtn = document.getElementById('profiles-delete-btn');
        const dlBtn = document.getElementById('profiles-download-btn');
        const wrap = document.getElementById('profiles-editor-wrap');

        if (editBtn) {
            editBtn.hidden = editing;
            editBtn.disabled = !has || editing;
        }
        if (saveBtn) {
            saveBtn.hidden = !editing;
            saveBtn.disabled = !editing;
        }
        if (cancelBtn) {
            cancelBtn.hidden = !editing;
            cancelBtn.disabled = !editing;
        }
        if (actBtn) {
            actBtn.disabled = !has || editing || selectedActive;
            actBtn.hidden = editing;
        }
        if (moreBtn) moreBtn.disabled = !has;
        if (dlBtn) dlBtn.disabled = !has;
        if (delBtn) {
            delBtn.disabled = !has || selectedActive || editing;
            delBtn.title = selectedActive
                ? 'Nelze smazat aktivní profil'
                : editing
                    ? 'Nejdřív ukonči úpravy'
                    : '';
        }

        if (wrap) wrap.classList.toggle('is-editing', editing);

        if (cm) {
            cm.setOption('readOnly', !editing);
        } else {
            const ta = document.getElementById('config-editor');
            if (ta) ta.disabled = !has || !editing;
        }
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

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
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

    async function refreshList() {
        try {
            const data = await api('/api/profiles');
            renderList(data);
        } catch (err) {
            reportError(err);
        }
    }

    function confirmLeaveEdit() {
        if (!editing) return true;
        if (!dirty) {
            editing = false;
            setEditorText(loadedContent);
            updateChrome();
            return true;
        }
        if (!confirm('Máš neuložené změny. Zahodit je?')) return false;
        editing = false;
        dirty = false;
        setEditorText(loadedContent);
        updateChrome();
        return true;
    }

    async function openProfile(name) {
        if (selectedName === name) return;
        if (!confirmLeaveEdit()) return;

        selectedName = name;
        closeMoreMenu();
        try {
            const data = await api(`/api/profiles/${encodeURIComponent(name)}`);
            loadedContent = data.content || '';
            selectedActive = !!data.active;
            editing = false;
            dirty = false;
            setEditorText(loadedContent);

            const title = document.getElementById('profiles-editor-title');
            const pathEl = document.getElementById('profiles-editor-path');
            if (title) {
                title.textContent = data.active ? `${data.name} (aktivní)` : data.name;
            }
            if (pathEl) pathEl.textContent = data.path || '';

            updateChrome();
            if (listCache) renderList(listCache);
        } catch (err) {
            reportError(err);
        }
    }

    function startEdit() {
        if (!selectedName || editing) return;
        editing = true;
        dirty = false;
        closeMoreMenu();
        updateChrome();
        if (cm) cm.focus();
        else document.getElementById('config-editor')?.focus();
    }

    function cancelEdit() {
        if (!editing) return;
        if (dirty && !confirm('Zahodit neuložené změny?')) return;
        editing = false;
        dirty = false;
        setEditorText(loadedContent);
        updateChrome();
    }

    async function saveSelected() {
        if (!selectedName || !editing) return;
        if (!dirty) {
            editing = false;
            updateChrome();
            return;
        }
        const content = getEditorText();
        try {
            await api(`/api/profiles/${encodeURIComponent(selectedName)}`, {
                method: 'PUT',
                body: JSON.stringify({ content }),
            });
            loadedContent = content;
            dirty = false;
            editing = false;
            updateChrome();
            await refreshList();
        } catch (err) {
            reportError(err);
        }
    }

    async function activateSelected() {
        if (!selectedName || editing) return;
        if (!confirm(`Aktivovat profil „${selectedName}“?\nBringup se načte až po restartu služby.`)) {
            return;
        }
        closeMoreMenu();
        try {
            await api(`/api/profiles/${encodeURIComponent(selectedName)}/activate`, {
                method: 'POST',
                body: '{}',
            });
            await refreshList();
            await openProfile(selectedName);
        } catch (err) {
            reportError(err);
        }
    }

    function downloadSelected() {
        if (!selectedName) return;
        closeMoreMenu();
        const content = editing ? getEditorText() : loadedContent;
        const blob = new Blob([content.endsWith('\n') ? content : `${content}\n`], {
            type: 'text/yaml;charset=utf-8',
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${selectedName}.yaml`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }

    async function deleteSelected() {
        if (!selectedName || selectedActive || editing) return;
        if (!confirm(`Smazat profil „${selectedName}“? Tuto akci nelze vrátit.`)) {
            return;
        }
        closeMoreMenu();
        try {
            await api(`/api/profiles/${encodeURIComponent(selectedName)}`, { method: 'DELETE' });
            selectedName = null;
            selectedActive = false;
            loadedContent = '';
            dirty = false;
            editing = false;
            setEditorText('');
            const title = document.getElementById('profiles-editor-title');
            const pathEl = document.getElementById('profiles-editor-path');
            if (title) title.textContent = 'Vyber profil';
            if (pathEl) pathEl.textContent = '';
            updateChrome();
            await refreshList();
        } catch (err) {
            reportError(err);
        }
    }

    async function createProfile() {
        if (!confirmLeaveEdit()) return;
        const name = prompt('Jméno nového profilu (bez .yaml):');
        if (!name || !name.trim()) return;
        const sourceDefault = selectedName || (listCache && listCache.active) || '';
        const source = prompt(
            'Zkopírovat z profilu (prázdné = aktivní / minimální stub):',
            sourceDefault
        );
        try {
            const body = { name: name.trim() };
            if (source && source.trim()) body.source = source.trim();
            const res = await api('/api/profiles', {
                method: 'POST',
                body: JSON.stringify(body),
            });
            dirty = false;
            editing = false;
            await refreshList();
            await openProfile(res.name);
        } catch (err) {
            reportError(err);
        }
    }

    window.initProfilesPage = async function initProfilesPage() {
        const rootHint = uiCfg().configs_root;
        const rootLabel = document.getElementById('profiles-root-label');
        if (rootLabel && rootHint) rootLabel.textContent = rootHint;

        selectedName = null;
        selectedActive = false;
        loadedContent = '';
        dirty = false;
        editing = false;
        cm = null;

        await ensureEditorMounted();

        document.getElementById('profiles-refresh-btn')?.addEventListener('click', refreshList);
        document.getElementById('profiles-create-btn')?.addEventListener('click', createProfile);
        document.getElementById('profiles-edit-btn')?.addEventListener('click', startEdit);
        document.getElementById('profiles-save-btn')?.addEventListener('click', saveSelected);
        document.getElementById('profiles-cancel-btn')?.addEventListener('click', cancelEdit);
        document.getElementById('profiles-activate-btn')?.addEventListener('click', activateSelected);
        document.getElementById('profiles-download-btn')?.addEventListener('click', downloadSelected);
        document.getElementById('profiles-delete-btn')?.addEventListener('click', deleteSelected);
        document.getElementById('profiles-more-btn')?.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleMoreMenu();
        });
        document.getElementById('config-editor')?.addEventListener('input', markDirty);

        if (!window.__rmodusProfilesMenuCloseBound) {
            window.__rmodusProfilesMenuCloseBound = true;
            document.addEventListener('click', (e) => {
                const more = document.getElementById('profiles-more');
                if (!more || more.contains(e.target)) return;
                closeMoreMenu();
            });
        }

        updateChrome();
        await refreshList();
        if (listCache && listCache.active) {
            await openProfile(listCache.active);
        }
    };
})();
