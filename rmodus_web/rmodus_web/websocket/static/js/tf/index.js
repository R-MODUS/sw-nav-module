/**
 * TF stránka: 3D scéna + strom rámů + detail vybraného rámu.
 *
 * Store žije po celou dobu aplikace (data tečou i mimo stránku). Zprávy
 * `tf_3d` jen mutují store; DOM se obnovuje timerem (UI_REFRESH_MS) a strom
 * se přestaví jen při změně topologie. Three.js se načte až při otevření stránky.
 */

import { HEALTH, TfStore } from './store.js';
import { TfTreeView } from './tree_view.js';
import { TfDetailsPanel } from './details.js';

const UI_REFRESH_MS = 200;
const DEFAULT_AXIS_SCALE = 0.12;

const store = new TfStore();

const page = {
    session: 0,
    root: null,
    scene: null,
    tree: null,
    details: null,
    timer: null,
    treeTopology: -1,
    fixedFrameOptions: '',
    selectedId: null,
    prefs: {
        showLabels: false,
        axisScale: DEFAULT_AXIS_SCALE,
        cameraMode: '3d',
        fixedFrame: null,
        collapsed: [],
    },
};

/* ---------- prefs ---------- */

function prefsApi() {
    const api = window.RmodusUiPrefs || null;
    return api && api.isEnabled() ? api : null;
}

function loadPrefs() {
    const api = prefsApi();
    const saved = api ? api.get('tf', {}) || {} : {};
    const p = page.prefs;
    if (typeof saved.showLabels === 'boolean') p.showLabels = saved.showLabels;
    if (Number.isFinite(saved.axisScale)) p.axisScale = saved.axisScale;
    if (saved.cameraMode === '2d' || saved.cameraMode === '3d') p.cameraMode = saved.cameraMode;
    if (typeof saved.fixedFrame === 'string') p.fixedFrame = saved.fixedFrame;
    if (Array.isArray(saved.collapsed)) p.collapsed = saved.collapsed.filter((id) => typeof id === 'string');
    if (typeof saved.selectedFrameId === 'string' || saved.selectedFrameId === null) {
        page.selectedId = saved.selectedFrameId;
    }
}

function savePrefs() {
    const api = prefsApi();
    if (!api) {
        return;
    }
    api.patch({ tf: { ...page.prefs, selectedFrameId: page.selectedId } });
}

function robotModelConfig() {
    const cfg = window.__RMODUS_UI_CONFIG__;
    return (cfg && cfg.robot_model) || {};
}

function fixedFrameId() {
    return page.prefs.fixedFrame || store.rootHint;
}

/* ---------- selection ---------- */

function selectFrame(frameId, source) {
    const id = frameId && store.has(frameId) ? frameId : null;
    page.selectedId = id;
    page.tree?.setSelected(id, { reveal: source === 'scene', store });
    page.scene?.setSelected(id);
    page.details?.update(store, id);
    savePrefs();
}

/* ---------- DOM refresh ---------- */

function $(selector) {
    return page.root ? page.root.querySelector(selector) : null;
}

function setText(selector, text) {
    const el = $(selector);
    if (el && el.textContent !== text) {
        el.textContent = text;
    }
}

function refreshFixedFrameSelect() {
    const select = $('#tf-fixed-frame');
    if (!select) {
        return;
    }
    const ids = store.sortedIds();
    const current = fixedFrameId();
    if (!ids.includes(current)) {
        ids.unshift(current);
    }
    const signature = ids.join('\n');
    if (signature !== page.fixedFrameOptions) {
        page.fixedFrameOptions = signature;
        select.replaceChildren(...ids.map((id) => new Option(id, id)));
    }
    select.value = current;
}

function refreshTopology() {
    if (page.treeTopology === store.topologyVersion) {
        return;
    }
    page.treeTopology = store.topologyVersion;
    page.tree?.rebuild(store);
    refreshFixedFrameSelect();
    const empty = $('#tf-tree-empty');
    if (empty) {
        empty.hidden = store.size > 0;
    }
    if (page.selectedId && store.size > 0 && !store.has(page.selectedId)) {
        selectFrame(null);
    }
}

function refreshStatus(now) {
    let warn = 0;
    let error = 0;
    store.frames.forEach((entry) => {
        const health = store.health(entry, now);
        if (health === HEALTH.WARN) warn += 1;
        if (health === HEALTH.ERROR) error += 1;
    });

    setText('#tf-frame-count', String(store.size));
    setText('#tf-fixed-frame-summary', fixedFrameId());
    setText('#tf-stale-count', String(warn + error));
    const staleItem = $('#tf-stale-summary');
    if (staleItem) {
        staleItem.dataset.health = error > 0 ? HEALTH.ERROR : warn > 0 ? HEALTH.WARN : HEALTH.OK;
    }

    let status;
    if (store.streamStale) {
        status = 'TF stream je neaktivní. Probíhá automatické obnovení…';
    } else if (store.size === 0) {
        status = 'Čekání na data TF…';
    } else if (error > 0 || warn > 0) {
        status = `Živý přehled TF · zpožděné rámy: ${warn}, zastaralé: ${error}`;
    } else {
        status = 'Živý přehled TF je k dispozici.';
    }
    setText('#tf-status', status);
    const statusEl = $('#tf-status');
    if (statusEl) {
        statusEl.dataset.stale = String(store.streamStale);
    }
}

function refreshUi() {
    if (!page.root || !page.root.isConnected) {
        teardown();
        return;
    }
    const now = performance.now();
    refreshTopology();
    page.tree?.updateLive(store, now);
    page.details?.update(store, page.selectedId, now);
    refreshStatus(now);
}

/* ---------- controls ---------- */

function bindControls() {
    const p = page.prefs;

    page.root.querySelectorAll('[data-camera-mode]').forEach((button) => {
        const sync = () => {
            page.root.querySelectorAll('[data-camera-mode]').forEach((b) => {
                const active = b.dataset.cameraMode === p.cameraMode;
                b.classList.toggle('is-active', active);
                b.setAttribute('aria-pressed', String(active));
            });
        };
        button.addEventListener('click', () => {
            p.cameraMode = button.dataset.cameraMode;
            page.scene?.setCameraMode(p.cameraMode);
            sync();
            savePrefs();
        });
        sync();
    });

    const labels = $('#tf-show-labels');
    if (labels) {
        labels.checked = p.showLabels;
        labels.addEventListener('change', () => {
            p.showLabels = labels.checked;
            page.scene?.setShowLabels(p.showLabels);
            savePrefs();
        });
    }

    const axis = $('#tf-axis-scale');
    const axisValue = $('#tf-axis-scale-value');
    const showAxis = () => {
        if (axisValue) axisValue.textContent = `${Math.round(p.axisScale * 100)} cm`;
    };
    if (axis) {
        axis.value = String(p.axisScale);
        showAxis();
        axis.addEventListener('input', () => {
            p.axisScale = Number.parseFloat(axis.value) || DEFAULT_AXIS_SCALE;
            page.scene?.setAxisScale(p.axisScale);
            showAxis();
        });
        axis.addEventListener('change', savePrefs);
    }

    const fixed = $('#tf-fixed-frame');
    if (fixed) {
        fixed.addEventListener('change', () => {
            p.fixedFrame = fixed.value === store.rootHint ? null : fixed.value;
            page.scene?.setFixedFrame(fixedFrameId());
            refreshStatus(performance.now());
            savePrefs();
        });
    }

    $('#tf-reset-view')?.addEventListener('click', () => page.scene?.resetView());
    $('#tf-focus-frame')?.addEventListener('click', () => {
        if (page.selectedId) page.scene?.focusFrame(page.selectedId);
    });
}

/* ---------- lifecycle ---------- */

async function mountScene(session) {
    const viewport = $('#tf-viewport');
    if (!viewport) {
        return;
    }
    try {
        const { createTfScene } = await import('./scene.js');
        if (session !== page.session || !viewport.isConnected) {
            return;
        }
        const scene = createTfScene(viewport, store, { onPick: (id) => selectFrame(id, 'scene') });
        const p = page.prefs;
        scene.setRobotModel(robotModelConfig());
        scene.setAxisScale(p.axisScale);
        scene.setShowLabels(p.showLabels);
        scene.setFixedFrame(fixedFrameId());
        scene.setCameraMode(p.cameraMode);
        scene.setSelected(page.selectedId);
        page.scene = scene;
        viewport.classList.remove('is-loading');
    } catch (err) {
        console.error('TF 3D scéna se nepodařila spustit:', err);
        viewport.classList.remove('is-loading');
        viewport.classList.add('is-error');
        const message = document.createElement('div');
        message.className = 'tf-viewport-message';
        message.textContent = 'Nelze spustit 3D zobrazení (WebGL není dostupné nebo se nenačetla knihovna Three.js).';
        viewport.appendChild(message);
    }
}

function teardown() {
    if (page.timer) {
        clearInterval(page.timer);
        page.timer = null;
    }
    page.scene?.dispose();
    page.scene = null;
    page.tree = null;
    page.details = null;
    page.root = null;
}

window.initTfPage = function initTfPage() {
    teardown();
    const root = document.querySelector('.tf-page');
    if (!root) {
        return;
    }
    page.session += 1;
    page.root = root;
    page.treeTopology = -1;
    page.fixedFrameOptions = '';
    loadPrefs();

    page.tree = new TfTreeView(root.querySelector('#tf-tree'), {
        collapsed: page.prefs.collapsed,
        onSelect: (id) => selectFrame(id, 'tree'),
        onCollapsedChange: (collapsed) => {
            page.prefs.collapsed = collapsed;
            savePrefs();
        },
    });
    page.details = new TfDetailsPanel(root.querySelector('#tf-details'));

    bindControls();
    refreshUi();
    page.tree.setSelected(page.selectedId, { reveal: true, store });
    page.timer = setInterval(refreshUi, UI_REFRESH_MS);
    mountScene(page.session);
};

window.handleTfPage3d = function handleTfPage3d(message) {
    const topologyChanged = store.applyTf3d(message);
    if (topologyChanged && page.root) {
        refreshTopology();
    }
};

window.handleTfPageStatus = function handleTfPageStatus(message) {
    store.streamStale = Boolean(message && message.stale);
    if (page.root) {
        refreshStatus(performance.now());
    }
};
