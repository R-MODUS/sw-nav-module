function api() {
    const prefs = window.RmodusUiPrefs;
    return prefs && prefs.isEnabled() ? prefs : null;
}

export function get(path, fallback) {
    const prefs = api();
    return prefs ? prefs.get(path, fallback) : fallback;
}

export function set(path, value) {
    api()?.set(path, value);
}

/** Replace an object value (prefs.set deep-merges, so removed keys would survive). */
export function replace(path, value) {
    const prefs = api();
    if (!prefs) {
        return;
    }
    const all = prefs.load();
    const parts = path.split('.');
    let cursor = all;
    for (let i = 0; i < parts.length - 1; i += 1) {
        cursor[parts[i]] = cursor[parts[i]] && typeof cursor[parts[i]] === 'object' ? cursor[parts[i]] : {};
        cursor = cursor[parts[i]];
    }
    cursor[parts[parts.length - 1]] = value;
    prefs.save(all);
}

/** null = never saved (first run pins everything). */
export function loadPinned() {
    const pinned = get('sensors.pinned', null);
    return Array.isArray(pinned) ? new Set(pinned.map(String)) : null;
}

export function savePinned(keys) {
    set('sensors.pinned', [...keys]);
}

/** Per column count; the key changed with the 12-column grid so old 6-column layouts are dropped. */
const LAYOUT_PATH = 'sensors.gridLayout';

export function loadLayout() {
    const layout = get(LAYOUT_PATH, null);
    return layout && typeof layout === 'object' ? layout : {};
}

export function saveLayout(layout) {
    replace(LAYOUT_PATH, layout);
}
