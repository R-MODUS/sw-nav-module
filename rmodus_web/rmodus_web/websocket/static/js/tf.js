(() => {
    const state = {
        frames: [],
        rootFrame: 'base_link',
        tfStale: true,
        selectedFrameId: null,
        showLabels: false,
        zoom: 2.0,
        robotView: null,
    };

    function prefsApi() {
        return window.RmodusUiPrefs || null;
    }

    function loadTfPrefs() {
        const api = prefsApi();
        if (!api || !api.isEnabled()) {
            return;
        }
        const tfPrefs = api.get('tf', {}) || {};
        if (typeof tfPrefs.showLabels === 'boolean') {
            state.showLabels = tfPrefs.showLabels;
        }
        if (typeof tfPrefs.zoom === 'number') {
            state.zoom = tfPrefs.zoom;
        }
        if (typeof tfPrefs.selectedFrameId === 'string' || tfPrefs.selectedFrameId === null) {
            state.selectedFrameId = tfPrefs.selectedFrameId;
        }
    }

    function saveTfPrefs() {
        const api = prefsApi();
        if (!api || !api.isEnabled()) {
            return;
        }
        api.patch({
            tf: {
                showLabels: state.showLabels,
                zoom: state.zoom,
                selectedFrameId: state.selectedFrameId,
            },
        });
    }

    function normalizeFrameId(frameId) {
        if (!frameId) {
            return null;
        }
        return String(frameId).replace(/^\/+/, '');
    }

    function frameIdsFromSnapshot() {
        const ids = new Set([state.rootFrame]);
        state.frames.forEach((frame) => {
            if (frame.parent_frame_id) {
                ids.add(normalizeFrameId(frame.parent_frame_id));
            }
            if (frame.child_frame_id) {
                ids.add(normalizeFrameId(frame.child_frame_id));
            }
        });
        return [...ids].filter(Boolean).sort((a, b) => a.localeCompare(b));
    }

    function renderStatus() {
        const frameCount = document.getElementById('tf-frame-count');
        const tfStatus = document.getElementById('tf-status');
        const rootBadge = document.getElementById('tf-root-frame');
        const rootSummary = document.getElementById('tf-root-frame-summary');

        if (frameCount) {
            frameCount.textContent = String(frameIdsFromSnapshot().length);
        }
        if (rootBadge) {
            rootBadge.textContent = state.rootFrame;
        }
        if (rootSummary) {
            rootSummary.textContent = state.rootFrame;
        }
        if (tfStatus) {
            if (state.tfStale) {
                tfStatus.textContent = 'TF stream je neaktivní. Probíhá automatické obnovení…';
            } else if (state.frames.length > 0) {
                tfStatus.textContent = 'Živý přehled TF je k dispozici.';
            } else {
                tfStatus.textContent = 'Čekání na data TF…';
            }
        }
    }

    function renderFrameList() {
        const list = document.getElementById('tf-frame-list');
        const empty = document.getElementById('tf-frame-empty');
        if (!list || !empty) {
            return;
        }

        const ids = frameIdsFromSnapshot();
        list.innerHTML = '';

        if (ids.length === 0) {
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';
        ids.forEach((frameId) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `tf-frame-item${state.selectedFrameId === frameId ? ' is-selected' : ''}`;
            button.textContent = frameId;
            if (frameId === state.rootFrame) {
                button.classList.add('is-root');
            }
            button.addEventListener('click', () => {
                state.selectedFrameId = state.selectedFrameId === frameId ? null : frameId;
                if (state.robotView) {
                    state.robotView.setSelectedFrame(state.selectedFrameId);
                }
                saveTfPrefs();
                renderFrameList();
            });
            list.appendChild(button);
        });
    }

    function ensureRobotView() {
        const canvas = document.getElementById('robotTfCanvas');
        if (!canvas || typeof window.createRobotView !== 'function') {
            return;
        }
        if (!state.robotView) {
            state.robotView = window.createRobotView(canvas);
        }
        state.robotView.setFrames(state.frames, state.rootFrame);
        state.robotView.setSelectedFrame(state.selectedFrameId);

        const showLabelsInput = document.getElementById('tf-show-labels');
        const zoomInput = document.getElementById('tf-zoom');
        const zoomValue = document.getElementById('tf-zoom-value');

        if (showLabelsInput) {
            showLabelsInput.checked = state.showLabels;
            state.robotView.setShowLabels(state.showLabels);
            showLabelsInput.onchange = () => {
                state.showLabels = showLabelsInput.checked;
                state.robotView.setShowLabels(state.showLabels);
                saveTfPrefs();
            };
        }

        if (zoomInput) {
            zoomInput.value = String(state.zoom);
            state.robotView.setZoom(state.zoom);
            if (zoomValue) {
                zoomValue.textContent = `${Number(state.zoom).toFixed(1)}×`;
            }
            zoomInput.oninput = () => {
                const currentZoom = Number.parseFloat(zoomInput.value || '2.0');
                state.zoom = currentZoom;
                state.robotView.setZoom(currentZoom);
                if (zoomValue) {
                    zoomValue.textContent = `${currentZoom.toFixed(1)}×`;
                }
                saveTfPrefs();
            };
        }
    }

    function renderAll() {
        ensureRobotView();
        renderStatus();
        renderFrameList();
    }

    window.initTfPage = function initTfPage() {
        state.robotView = null;
        loadTfPrefs();
        renderAll();
    };

    window.handleTfPageFrames = function handleTfPageFrames(message) {
        state.frames = Array.isArray(message.frames) ? message.frames : [];
        state.rootFrame = normalizeFrameId(message.root_frame) || 'base_link';
        state.tfStale = state.frames.length === 0;
        if (state.selectedFrameId && !frameIdsFromSnapshot().includes(state.selectedFrameId)) {
            state.selectedFrameId = null;
        }
        if (document.getElementById('robotTfCanvas')) {
            renderAll();
        }
    };

    window.handleTfPageStatus = function handleTfPageStatus(message) {
        state.tfStale = Boolean(message && message.stale);
        if (document.getElementById('tf-status')) {
            renderStatus();
        }
    };
})();
