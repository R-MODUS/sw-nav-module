/**
 * Lokální UI preference (localStorage).
 * Zapíná se přes web.ui.persist_local v YAML (inject do __RMODUS_UI_CONFIG__).
 */
(() => {
    const STORAGE_KEY = 'rmodus.ui.v1';
    const LEGACY_SIDEBAR = 'rmodus_sidebar_collapsed';
    const LEGACY_SENSORS_PINNED = 'rmodus.sensors.pinned';

    const DEFAULTS = {
        version: 1,
        lastPage: null,
        sidebarCollapsed: false,
        sensors: {
            pinned: null, // null = ještě neuloženo (auto-pin all)
            gridLayout: {}, // { "<počet sloupců>": { tileId: {x, y, w, h} } }, 12sloupcová mřížka
            catalogCollapsed: false,
            groupsCollapsed: {},
        },
        map: {
            zoom: 1.0,
            followRobot: false,
            showLidar: false,
            lidarHidden: {},
        },
        tf: {
            showLabels: false,
            zoom: 2.0,
            selectedFrameId: null,
        },
    };

    function uiConfig() {
        return typeof window.__RMODUS_UI_CONFIG__ === 'object' && window.__RMODUS_UI_CONFIG__
            ? window.__RMODUS_UI_CONFIG__
            : {};
    }

    function isEnabled() {
        const cfg = uiConfig();
        if (Object.prototype.hasOwnProperty.call(cfg, 'persist_local')) {
            return Boolean(cfg.persist_local);
        }
        return true;
    }

    function deepMerge(base, overlay) {
        if (!overlay || typeof overlay !== 'object') {
            return base;
        }
        const out = Array.isArray(base) ? [...base] : { ...base };
        Object.keys(overlay).forEach((key) => {
            const value = overlay[key];
            if (
                value &&
                typeof value === 'object' &&
                !Array.isArray(value) &&
                out[key] &&
                typeof out[key] === 'object' &&
                !Array.isArray(out[key])
            ) {
                out[key] = deepMerge(out[key], value);
            } else {
                out[key] = value;
            }
        });
        return out;
    }

    function readRaw() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) {
                return null;
            }
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (_err) {
            return null;
        }
    }

    function writeRaw(prefs) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
            return true;
        } catch (_err) {
            return false;
        }
    }

    function migrateLegacy(prefs) {
        let changed = false;
        try {
            const sidebar = localStorage.getItem(LEGACY_SIDEBAR);
            if (sidebar !== null && prefs.sidebarCollapsed === DEFAULTS.sidebarCollapsed) {
                prefs.sidebarCollapsed = sidebar === '1';
                changed = true;
            }
            const pinnedRaw = localStorage.getItem(LEGACY_SENSORS_PINNED);
            if (pinnedRaw && (prefs.sensors == null || prefs.sensors.pinned == null)) {
                const pinned = JSON.parse(pinnedRaw);
                if (Array.isArray(pinned)) {
                    prefs.sensors = prefs.sensors || {};
                    prefs.sensors.pinned = pinned.map(String);
                    changed = true;
                }
            }
        } catch (_err) {
            /* ignore broken legacy */
        }
        return changed;
    }

    function load() {
        const prefs = deepMerge(DEFAULTS, readRaw() || {});
        if (prefs.version !== 1) {
            return deepMerge(DEFAULTS, {});
        }
        if (migrateLegacy(prefs)) {
            writeRaw(prefs);
        }
        return prefs;
    }

    function save(prefs) {
        if (!isEnabled()) {
            return false;
        }
        const next = deepMerge(DEFAULTS, prefs || {});
        next.version = 1;
        return writeRaw(next);
    }

    function patch(partial) {
        if (!isEnabled()) {
            return load();
        }
        const next = deepMerge(load(), partial || {});
        writeRaw(next);
        return next;
    }

    function get(path, fallback) {
        const prefs = load();
        if (!path) {
            return prefs;
        }
        const parts = String(path).split('.');
        let cur = prefs;
        for (let i = 0; i < parts.length; i += 1) {
            if (cur == null || typeof cur !== 'object' || !(parts[i] in cur)) {
                return fallback;
            }
            cur = cur[parts[i]];
        }
        return cur === undefined ? fallback : cur;
    }

    function set(path, value) {
        if (!isEnabled() || !path) {
            return;
        }
        const parts = String(path).split('.');
        const partial = {};
        let cursor = partial;
        for (let i = 0; i < parts.length - 1; i += 1) {
            cursor[parts[i]] = {};
            cursor = cursor[parts[i]];
        }
        cursor[parts[parts.length - 1]] = value;
        patch(partial);
    }

    window.RmodusUiPrefs = {
        STORAGE_KEY,
        DEFAULTS,
        isEnabled,
        load,
        save,
        patch,
        get,
        set,
    };
})();
