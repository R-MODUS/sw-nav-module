import { createCatalog } from './catalog.js';
import { createDrawer } from './drawer.js';
import { createDashboard } from './grid.js';
import { BINARY_TYPES } from './binary.js';
import { sensorKey } from './meta.js';
import { loadPinned, savePinned } from './prefs.js';
import { store } from './store.js';
import { BLUEPRINT_KEY, buildTiles, sensorTile, WIDGET_ITEMS } from './tiles.js';

function mountSensorsPage(root) {
    const gridEl = root.querySelector('[data-role="grid"]');
    const emptyEl = root.querySelector('[data-role="grid-empty"]');
    const countEl = root.querySelector('[data-role="count"]');
    const pinnedCountEl = root.querySelector('[data-role="pinned-count"]');

    const savedPins = loadPinned();
    const pinned = savedPins || new Set();
    let autoPinPending = savedPins === null;
    let tiles = [];

    function tileIdForKey(key) {
        return tiles.find((tile) => tile.keys.includes(key))?.id || null;
    }

    const drawer = createDrawer(root.querySelector('[data-role="drawer"]'), {
        onOpen: (tile) => dashboard.setSelected(tiles.some((t) => t.id === tile.id) ? tile.id : tileIdForKey(tile.keys[0])),
        onClose: () => dashboard.setSelected(null),
    });
    drawer.setSensorTileResolver((key) => {
        const sensor = store.entry(key)?.sensor;
        return sensor ? sensorTile(sensor) : null;
    });

    const dashboard = createDashboard(gridEl, {
        onOpen: (tile) => drawer.open(tile),
        onUnpin: (tile) => setPinned(tile.keys, false),
        onSelectKey: (key) => drawer.openSensor(key),
    });

    const catalog = createCatalog(root.querySelector('[data-role="catalog"]'), {
        isPinned: (key) => pinned.has(key),
        setPinned,
        onOpenSensor: (key) => drawer.openSensor(key),
    });

    function setPinned(keys, on) {
        keys.forEach((key) => (on ? pinned.add(key) : pinned.delete(key)));
        savePinned(pinned);
        refresh();
    }

    function refresh() {
        const catalogSensors = store.catalog;
        if (autoPinPending && catalogSensors.length > 0) {
            pinned.add(BLUEPRINT_KEY);
            catalogSensors
                .filter((s) => !BINARY_TYPES.has(s.sensor_type))
                .forEach((s) => pinned.add(sensorKey(s.sensor_type, s.sensor_id)));
            savePinned(pinned);
            autoPinPending = false;
        }
        tiles = buildTiles(catalogSensors, pinned);
        dashboard.sync(tiles);
        catalog.render();
        countEl.textContent = String(catalogSensors.length);
        pinnedCountEl.textContent = String(tiles.length);
        emptyEl.hidden = tiles.length > 0;
    }

    root.querySelector('[data-role="pin-all"]')?.addEventListener('click', () => {
        setPinned(
            [...WIDGET_ITEMS.map((w) => w.key), ...store.catalog.map((s) => sensorKey(s.sensor_type, s.sensor_id))],
            true,
        );
    });
    root.querySelector('[data-role="pin-none"]')?.addEventListener('click', () => {
        setPinned([...pinned], false);
    });
    root.querySelector('[data-role="reset-layout"]')?.addEventListener('click', () => {
        dashboard.resetLayout(tiles);
    });

    const offCatalog = store.onCatalog(refresh);
    let destroyed = false;
    const offTick = store.onTick(() => {
        if (!root.isConnected) {
            destroy();
        }
    });

    function destroy() {
        if (destroyed) {
            return;
        }
        destroyed = true;
        offCatalog();
        offTick();
        drawer.destroy();
        catalog.destroy();
        dashboard.destroy();
    }

    refresh();
    return { destroy };
}

let page = null;

window.handleSensorCatalog = (sensors) => store.setCatalog(sensors);
window.handleSensorData = (message) => store.ingest(message);

window.initSensorsPage = () => {
    page?.destroy();
    page = null;
    const root = document.querySelector('.sensors-page');
    if (!root) {
        return;
    }
    if (typeof window.GridStack === 'undefined') {
        console.error('GridStack se nenačetl (static/vendor/gridstack).');
        return;
    }
    page = mountSensorsPage(root);
};
