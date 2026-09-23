import { binaryState, stateLabel } from './binary.js';
import { el, fieldLabel, formatAge, formatValue, STATUS_LABELS, worstStatus } from './meta.js';
import { store } from './store.js';
import { createWidget } from './widgets/index.js';

const TEXT_REFRESH_MS = 250;
const JSON_ARRAY_PREVIEW = 24;

function previewJson(payload) {
    return JSON.stringify(
        payload,
        (_key, value) => {
            if (Array.isArray(value) && value.length > JSON_ARRAY_PREVIEW) {
                return [...value.slice(0, JSON_ARRAY_PREVIEW), `… +${value.length - JSON_ARRAY_PREVIEW} položek`];
            }
            if (typeof value === 'number' && !Number.isInteger(value)) {
                return Number(value.toFixed(4));
            }
            return value;
        },
        2,
    );
}

/**
 * Right slide-out detail. Target = a tile ({ kind, keys, title, subtitle }).
 * Visual updates every frame; metrics / JSON are throttled.
 */
export function createDrawer(root, { onOpen, onClose }) {
    const q = (role) => root.querySelector(`[data-role="${role}"]`);
    const nodes = {
        dot: q('dot'),
        title: q('title'),
        badge: q('badge'),
        meta: q('meta'),
        visual: q('visual'),
        children: q('children'),
        metrics: q('metrics'),
        raw: q('raw'),
        copy: q('copy'),
        close: q('close'),
    };

    let target = null;
    let widget = null;
    let sub = null;
    let textTimer = null;
    let lastText = 0;

    nodes.close.addEventListener('click', () => close());
    nodes.copy.addEventListener('click', () => {
        const entries = currentEntries();
        const data = entries.length === 1 ? entries[0].payload : Object.fromEntries(entries.map((e) => [e.key, e.payload]));
        navigator.clipboard?.writeText(JSON.stringify(data, null, 2));
        nodes.copy.textContent = 'Zkopírováno';
        window.setTimeout(() => {
            nodes.copy.textContent = 'Kopírovat';
        }, 1200);
    });
    const onKey = (event) => {
        if (event.key === 'Escape' && target) {
            close();
        }
    };
    document.addEventListener('keydown', onKey);

    function currentEntries() {
        return target ? target.keys.map((key) => store.entry(key)).filter(Boolean) : [];
    }

    function renderMeta(entries) {
        const now = Date.now();
        const rows = [];
        if (entries.length === 1) {
            const { sensor, lastSeen, key } = entries[0];
            rows.push(['Topic', sensor?.topic]);
            rows.push(['Frame', sensor?.frame_id]);
            rows.push(['Typ zprávy', sensor?.message_type]);
            const hz = store.rateHz(key);
            rows.push(['Frekvence v UI', hz > 0 ? `${hz.toFixed(1)} Hz` : '—']);
            rows.push(['Poslední data', formatAge(lastSeen ? now - lastSeen : null)]);
        } else {
            rows.push(['Senzorů', String(entries.length)]);
            const newest = Math.max(0, ...entries.map((e) => e.lastSeen || 0));
            rows.push(['Poslední data', formatAge(newest ? now - newest : null)]);
        }
        nodes.meta.replaceChildren(
            ...rows.flatMap(([label, value]) => [el('dt', null, label), el('dd', null, value || '—')]),
        );
        const status = worstStatus(entries.map((e) => e.status));
        nodes.dot.dataset.status = status;
        nodes.dot.title = STATUS_LABELS[status];
    }

    let childRows = new Map();

    function buildChildren(entries) {
        childRows = new Map();
        nodes.children.hidden = entries.length < 2;
        nodes.children.replaceChildren();
        if (entries.length < 2) {
            return;
        }
        entries.forEach((entry) => {
            const row = el('button', 'sx-child');
            row.type = 'button';
            const dot = el('span', 'sx-dot');
            const state = el('span', 'sx-child-state');
            row.append(dot, el('span', 'sx-child-name', entry.sensor?.label || entry.key), state);
            row.addEventListener('click', () => openSensor(entry.key));
            nodes.children.appendChild(row);
            childRows.set(entry.key, { row, dot, state });
        });
    }

    function renderChildren(entries) {
        entries.forEach((entry) => {
            const child = childRows.get(entry.key);
            if (!child) {
                return;
            }
            const p = entry.payload;
            const active = binaryState(entry.sensor, p);
            let state = stateLabel(entry.sensor?.sensor_type, active);
            if (p && 'range' in p) {
                state = `${state} · ${formatValue(p.range)} m`;
            }
            child.dot.dataset.status = entry.status;
            child.state.textContent = state;
            child.row.classList.toggle('is-hit', Boolean(active));
        });
    }

    function renderMetrics(entries) {
        if (entries.length !== 1) {
            nodes.metrics.hidden = true;
        } else {
            const payload = entries[0].payload;
            nodes.metrics.hidden = false;
            if (!payload) {
                nodes.metrics.replaceChildren(el('p', 'sx-muted', 'Zatím žádná data.'));
            } else {
                nodes.metrics.replaceChildren(
                    ...Object.entries(payload)
                        .filter(([, value]) => !(Array.isArray(value) && value.length > 12))
                        .map(([key, value]) => {
                            const cell = el('div', 'sx-metric');
                            cell.append(el('span', null, fieldLabel(key)), el('strong', null, formatValue(value)));
                            return cell;
                        }),
                );
            }
        }
        const payloads = entries.length === 1 ? entries[0].payload : Object.fromEntries(entries.map((e) => [e.sensor?.label || e.key, e.payload]));
        nodes.raw.textContent = payloads ? previewJson(payloads) : 'Čekání na první zprávu…';
    }

    function renderText() {
        textTimer = null;
        lastText = performance.now();
        const entries = currentEntries();
        renderMeta(entries);
        renderChildren(entries);
        renderMetrics(entries);
    }

    function scheduleText() {
        if (textTimer) {
            return;
        }
        const wait = Math.max(0, TEXT_REFRESH_MS - (performance.now() - lastText));
        textTimer = window.setTimeout(renderText, wait);
    }

    function teardownTarget() {
        sub?.unsubscribe();
        sub = null;
        widget?.destroy();
        widget = null;
        if (textTimer) {
            window.clearTimeout(textTimer);
            textTimer = null;
        }
    }

    function open(tile) {
        teardownTarget();
        target = tile;
        root.classList.add('is-open');
        root.setAttribute('aria-hidden', 'false');
        nodes.title.textContent = tile.title;
        nodes.badge.textContent = tile.subtitle;
        nodes.visual.replaceChildren();
        nodes.visual.dataset.kind = tile.kind;
        widget = createWidget(tile.kind, nodes.visual, { mode: 'detail', onSelectKey: openSensor });
        const refresh = () => {
            widget.update(currentEntries());
            scheduleText();
        };
        sub = store.subscribe(tile.keys, refresh);
        buildChildren(currentEntries());
        refresh();
        renderText();
        onOpen?.(tile);
    }

    let resolveSensorTile = null;

    function openSensor(key) {
        const tile = resolveSensorTile?.(key);
        if (tile) {
            open(tile);
        }
    }

    function close() {
        if (!target) {
            return;
        }
        teardownTarget();
        target = null;
        root.classList.remove('is-open');
        root.setAttribute('aria-hidden', 'true');
        onClose?.();
    }

    const offTick = store.onTick(() => {
        if (target) {
            scheduleText();
        }
    });
    const offStatus = store.onStatus((entry) => {
        if (target?.keys.includes(entry.key)) {
            widget?.update(currentEntries());
            scheduleText();
        }
    });

    return {
        open,
        openSensor,
        close,
        get targetId() {
            return target?.id || null;
        },
        /** fn(key) → single-sensor tile used when drilling into a sensor. */
        setSensorTileResolver(fn) {
            resolveSensorTile = fn;
        },
        destroy() {
            teardownTarget();
            offTick();
            offStatus();
            document.removeEventListener('keydown', onKey);
        },
    };
}
