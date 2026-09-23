import { el, STATUS_LABELS, worstStatus } from './meta.js';
import { loadLayout, saveLayout } from './prefs.js';
import { store } from './store.js';
import { TILE_SIZES } from './tiles.js';
import { createWidget } from './widgets/index.js';

const COLUMNS = 12;
const CLICK_AFTER_DRAG_MS = 250;

function createTileController(tile, { onOpen, onUnpin, onSelectKey, shouldIgnoreClick }) {
    const item = el('div', 'grid-stack-item');
    const content = el('div', 'grid-stack-item-content sx-tile');
    content.dataset.kind = tile.kind;
    content.tabIndex = 0;
    content.setAttribute('role', 'button');

    const head = el('header', 'sx-tile-head');
    const title = el('span', 'sx-tile-title');
    const subtitle = el('span', 'sx-tile-sub');
    const unpin = el('button', 'sx-tile-unpin', '×');
    unpin.type = 'button';
    unpin.title = 'Odebrat z přehledu';
    unpin.setAttribute('aria-label', 'Odebrat z přehledu');
    const dot = el('span', 'sx-dot');
    head.append(title, subtitle, unpin, dot);

    const body = el('div', 'sx-tile-body');
    content.append(head, body);
    item.appendChild(content);

    const controller = {
        tile,
        item,
        widget: createWidget(tile.kind, body, { mode: 'tile', onSelectKey }),
        sub: null,
        setTile(next) {
            controller.tile = next;
            title.textContent = next.title;
            title.title = next.title;
            content.setAttribute('aria-label', `${next.title} – otevřít detail`);
            subtitle.textContent = next.subtitle;
            controller.sub?.setKeys(next.keys);
            controller.refresh();
        },
        refresh() {
            const entries = controller.tile.keys.map((key) => store.entry(key)).filter(Boolean);
            controller.widget.update(entries);
            controller.refreshStatus(entries);
        },
        refreshStatus(entries = controller.tile.keys.map((key) => store.entry(key)).filter(Boolean)) {
            const status = worstStatus(entries.map((entry) => entry.status));
            if (dot.dataset.status !== status) {
                dot.dataset.status = status;
                dot.title = STATUS_LABELS[status];
            }
        },
        setSelected(selected) {
            content.classList.toggle('is-selected', selected);
        },
        destroy() {
            controller.sub?.unsubscribe();
            controller.widget.destroy();
        },
    };

    content.addEventListener('click', () => {
        if (!shouldIgnoreClick()) {
            onOpen(controller.tile);
        }
    });
    content.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onOpen(controller.tile);
        }
    });
    unpin.addEventListener('click', (event) => {
        event.stopPropagation();
        onUnpin(controller.tile);
    });

    controller.sub = store.subscribe(tile.keys, () => controller.refresh());
    controller.setTile(tile);
    return controller;
}

export function createDashboard(container, { onOpen, onUnpin, onSelectKey }) {
    const grid = window.GridStack.init(
        {
            column: COLUMNS,
            cellHeight: 104,
            margin: 5,
            float: false,
            animate: true,
            columnOpts: {
                columnMax: COLUMNS,
                layout: (column, oldColumn, nodes, oldNodes) => relayout(column, oldColumn, nodes, oldNodes),
                breakpoints: [
                    { w: 1100, c: 8 },
                    { w: 760, c: 4 },
                    { w: 480, c: 2 },
                ],
            },
            resizable: { handles: 'se' },
            draggable: { cancel: 'button, input, .sx-seg' },
        },
        container,
    );

    const controllers = new Map();
    let suppressClickUntil = 0;
    let selectedId = null;

    const shouldIgnoreClick = () => performance.now() < suppressClickUntil;

    grid.on('dragstart resizestart', () => {
        suppressClickUntil = Number.POSITIVE_INFINITY;
    });
    grid.on('dragstop resizestop', () => {
        suppressClickUntil = performance.now() + CLICK_AFTER_DRAG_MS;
    });
    grid.on('change', () => persistLayout());

    /**
     * Column-count change: saved layout for the new count wins, otherwise the tile keeps its
     * natural size and is packed in reading order (plain scaling would stretch 1x1 binary
     * tiles across several cells and leave holes).
     */
    function relayout(column, oldColumn, nodes, oldNodes) {
        const saved = loadLayout()[String(column)] || {};
        const occupied = new Set();
        const cells = (node, fn) => {
            for (let y = node.y; y < node.y + node.h; y += 1) {
                for (let x = node.x; x < node.x + node.w; x += 1) {
                    if (fn(`${x},${y}`) === false) {
                        return false;
                    }
                }
            }
            return true;
        };
        const place = (node) => {
            cells(node, (cell) => occupied.add(cell));
            nodes.push(node);
        };

        nodes.forEach((node) => cells(node, (cell) => occupied.add(cell)));
        const unsaved = [];
        oldNodes.forEach((node) => {
            const pos = saved[node.id];
            if (pos) {
                node.w = Math.min(pos.w, column);
                node.h = pos.h;
                node.x = Math.min(pos.x, column - node.w);
                node.y = pos.y;
                place(node);
            } else {
                unsaved.push(node);
            }
        });

        unsaved.sort((a, b) => a.y - b.y || a.x - b.x);
        unsaved.forEach((node) => {
            const kind = controllers.get(node.id)?.tile.kind;
            const size = TILE_SIZES[kind] || TILE_SIZES.generic;
            node.w = Math.min(size.w, column);
            node.h = size.h;
            for (let y = 0; ; y += 1) {
                const x = [...Array(column - node.w + 1).keys()].find((cx) =>
                    cells({ x: cx, y, w: node.w, h: node.h }, (cell) => !occupied.has(cell)),
                );
                if (x !== undefined) {
                    node.x = x;
                    node.y = y;
                    break;
                }
            }
            place(node);
        });
    }

    /** Layout is stored per column count: { "6": { tileId: {x, y, w, h} }, "4": {...} }. */
    function persistLayout() {
        const column = String(grid.getColumn());
        const all = loadLayout();
        const next = { ...(all[column] || {}) };
        grid.getGridItems().forEach((item) => {
            const node = item.gridstackNode;
            if (node?.id) {
                next[node.id] = { x: node.x, y: node.y, w: node.w, h: node.h };
            }
        });
        saveLayout({ ...all, [column]: next });
    }

    const offStatus = store.onStatus((entry) => {
        controllers.forEach((controller) => {
            if (controller.tile.keys.includes(entry.key)) {
                controller.refresh();
            }
        });
    });

    function addTile(tile, saved) {
        const controller = createTileController(tile, {
            onOpen,
            onUnpin,
            onSelectKey,
            shouldIgnoreClick,
        });
        const size = TILE_SIZES[tile.kind] || TILE_SIZES.generic;
        const column = grid.getColumn();
        const pos = saved || null;
        grid.makeWidget(controller.item, {
            id: tile.id,
            w: pos?.w ?? Math.min(size.w, column),
            h: pos?.h ?? size.h,
            ...(pos ? { x: pos.x, y: pos.y } : { autoPosition: true }),
            minW: 1,
            minH: 1,
        });
        controller.setSelected(tile.id === selectedId);
        controllers.set(tile.id, controller);
    }

    function removeTile(id) {
        const controller = controllers.get(id);
        if (!controller) {
            return;
        }
        controllers.delete(id);
        controller.destroy();
        grid.removeWidget(controller.item, true, false);
    }

    return {
        sync(tiles) {
            const wanted = new Map(tiles.map((tile) => [tile.id, tile]));
            const saved = loadLayout()[String(grid.getColumn())] || {};
            grid.batchUpdate();
            [...controllers.keys()].forEach((id) => {
                if (!wanted.has(id)) {
                    removeTile(id);
                }
            });
            tiles.forEach((tile) => {
                const existing = controllers.get(tile.id);
                if (existing) {
                    existing.setTile(tile);
                } else {
                    addTile(tile, saved[tile.id]);
                }
            });
            grid.batchUpdate(false);
        },

        resetLayout(tiles) {
            saveLayout({});
            [...controllers.keys()].forEach(removeTile);
            this.sync(tiles);
            persistLayout();
        },

        setSelected(id) {
            selectedId = id;
            controllers.forEach((controller, tileId) => controller.setSelected(tileId === id));
        },

        destroy() {
            offStatus();
            controllers.forEach((controller) => controller.destroy());
            controllers.clear();
            grid.destroy(false);
        },
    };
}
