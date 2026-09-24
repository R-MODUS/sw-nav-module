/* === KONFIGURACE A PROMĚNNÉ === */
let ws;
function testingMode() {
    return Boolean(window.__RMODUS_UI_CONFIG__ && window.__RMODUS_UI_CONFIG__.testing);
}

let userRole = 'spectator'; // Výchozí role; testing ji po připojení přepne na admina
const ADMIN_TOKEN_KEY = 'robot_admin_token';
let activePage = '';
let wsReconnectTimer = null;
let wsConnectTimer = null;
const WS_RECONNECT_DELAY_MS = 2000;
const WS_CONNECT_TIMEOUT_MS = 15000;
const JOYSTICK_SCRIPT_URLS = [
    'static/vendor/nipplejs.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.10.1/nipplejs.min.js',
];
const JOYSTICK_SCRIPT_LOAD_TIMEOUT_MS = 4000;
let joystickScriptPromise = null;
let gamepadListenersInitialized = false;

const NAV_TAB_ORDER = ['status', 'controls', 'map', 'sensors', 'tf', 'docs', 'config', 'settings', 'users'];

function prefsApi() {
    return window.RmodusUiPrefs || null;
}

function prefsEnabled() {
    const api = prefsApi();
    return api ? api.isEnabled() : true;
}

function getUiNavTabs() {
    const cfg = typeof window.__RMODUS_UI_CONFIG__ === 'object' && window.__RMODUS_UI_CONFIG__
        ? window.__RMODUS_UI_CONFIG__.nav_tabs
        : null;
    return cfg && typeof cfg === 'object' ? cfg : {};
}

function applyNavTabsVisibility() {
    const tabs = getUiNavTabs();
    NAV_TAB_ORDER.forEach((key) => {
        const el = document.getElementById(`nav-${key}`);
        if (!el) return;
        el.style.display = tabs[key] === false ? 'none' : '';
    });
}

function getInitialPageName() {
    const tabs = getUiNavTabs();
    const api = prefsApi();
    if (api && api.isEnabled()) {
        const saved = api.get('lastPage', null);
        if (saved && tabs[saved] !== false && document.getElementById(`nav-${saved}`)) {
            return saved;
        }
    }
    const chosen = NAV_TAB_ORDER.find((k) => tabs[k] !== false);
    return chosen || 'status';
}

function applySidebarCollapsed(collapsed) {
    const root = document.getElementById('app-root');
    if (root) {
        root.classList.toggle('sidebar-collapsed', collapsed);
    }
    const api = prefsApi();
    if (api && api.isEnabled()) {
        api.set('sidebarCollapsed', Boolean(collapsed));
    }
}

function initSidebarRail() {
    const expandBtn = document.getElementById('sidebar-expand-btn');
    const collapseBtn = document.getElementById('sidebar-collapse-btn');
    let collapsed = false;
    const api = prefsApi();
    if (api && api.isEnabled()) {
        collapsed = Boolean(api.get('sidebarCollapsed', false));
    }
    applySidebarCollapsed(collapsed);
    collapseBtn?.addEventListener('click', () => applySidebarCollapsed(true));
    expandBtn?.addEventListener('click', () => applySidebarCollapsed(false));
}

async function restartRmodusService(options) {
    const opts = options || {};
    const btn = document.getElementById('sidebar-restart-btn');
    if (!opts.skipConfirm) {
        if (!confirm(
            'Restartovat R-MODUS?\n\n'
            + 'Načte aktivní profil a krátce odpojí web. Pokračovat?'
        )) {
            return;
        }
    }
    if (btn) btn.disabled = true;
    const headers = { 'Content-Type': 'application/json' };
    try {
        const pin = localStorage.getItem(ADMIN_TOKEN_KEY);
        if (pin) headers['X-Admin-Pin'] = pin;
    } catch (_e) {
        /* ignore */
    }
    try {
        const res = await fetch('/api/system/restart', { method: 'POST', headers, body: '{}' });
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
        // Úspěch: žádný alert — služba se stejně odpojí; browser dialog je zbytečný.
    } catch (err) {
        alert(err.message || String(err));
        if (btn) btn.disabled = false;
    }
}

function initSidebarRestart() {
    document.getElementById('sidebar-restart-btn')?.addEventListener('click', restartRmodusService);
}

/* === HLAVNÍ LOGIKA APLIKACE === */

// Načítání stránek (SPA - Single Page Application)
window.loadPage = async function(pageName) {
    // Nenačítat znovu, pokud je již aktivní
    if (pageName === activePage) return;

    const tabs = getUiNavTabs();
    const anyNavEnabled = NAV_TAB_ORDER.some((k) => tabs[k] !== false);
    const navEl = document.getElementById(`nav-${pageName}`);
    const navHidden = !!(navEl && navEl.style.display === 'none');
    const forbidden = tabs[pageName] === false || navHidden;
    if (forbidden && anyNavEnabled) {
        const fallback = getInitialPageName();
        if (fallback !== pageName) {
            return window.loadPage(fallback);
        }
    }

    try {
        const response = await fetch(`static/pages/${pageName}.html`);
        if (!response.ok) {
            throw new Error(`Failed to load page: ${response.status} ${response.statusText}`);
        }
        const html = await response.text();
        document.getElementById('main-content').innerHTML = html;
        activePage = pageName;

        const prefs = prefsApi();
        if (prefs && prefs.isEnabled()) {
            prefs.set('lastPage', pageName);
        }

        // Označení aktivního odkazu v navigaci
        document.querySelectorAll('.nav-links li, .nav-links-bottom li').forEach(li => li.classList.remove('active'));
        const activeLink = document.getElementById(`nav-${pageName}`);
        if (activeLink) {
            activeLink.classList.add('active');
        }

        // Spuštění specifické inicializační logiky pro danou stránku
        // Používáme requestAnimationFrame a setTimeout, abychom zajistili, že DOM je plně vykreslen
        requestAnimationFrame(() => {
            setTimeout(() => {
                if (pageName === 'controls') {
                    initControlsPage();
                } else if (pageName === 'map') {
                    // initMap() je definována v map.js
                    if (typeof initMap === 'function') {
                        initMap();
                    } else {
                        console.error("initMap function not found. Was map.js loaded correctly?");
                    }
                } else if (pageName === 'sensors') {
                    if (typeof window.initSensorsPage === 'function') {
                        window.initSensorsPage();
                    } else {
                        console.error('initSensorsPage function not found. Was sensors.js loaded correctly?');
                    }
                } else if (pageName === 'tf') {
                    if (typeof window.initTfPage === 'function') {
                        window.initTfPage();
                    } else {
                        console.error('initTfPage function not found. Was tf/index.js loaded correctly?');
                    }
                } else if (pageName === 'config') {
                    if (typeof window.initProfilesPage === 'function') {
                        window.initProfilesPage();
                    } else {
                        console.error('initProfilesPage function not found. Was profiles.js loaded correctly?');
                    }
                } else if (pageName === 'settings') {
                    if (typeof window.initSettingsPage === 'function') {
                        window.initSettingsPage();
                    } else {
                        console.error('initSettingsPage function not found. Was settings.js loaded correctly?');
                    }
                }
            }, 50); // Krátké zpoždění pro jistotu
        });

    } catch (e) {
        console.error("Chyba při načítání stránky:", e);
        document.getElementById('main-content').innerHTML = `<div class="error-page"><h2>Chyba načítání</h2><p>Stránku se nepodařilo načíst. Zkuste to prosím znovu.</p></div>`;
    }
}

/* === INICIALIZACE PO NAČTENÍ STRÁNKY === */
function bootstrapApp() {
    applyNavTabsVisibility();
    initSidebarRail();
    initSidebarRestart();
    initWebSocket();
    updateUI();
    window.loadPage(getInitialPageName());
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrapApp, { once: true });
} else {
    bootstrapApp();
}

function loadScriptWithTimeout(src, timeoutMs) {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        let settled = false;
        const timer = setTimeout(() => {
            finish(new Error(`Timed out loading script: ${src}`));
        }, Math.max(500, timeoutMs || JOYSTICK_SCRIPT_LOAD_TIMEOUT_MS));

        const cleanup = () => {
            script.onload = null;
            script.onerror = null;
            clearTimeout(timer);
        };
        const finish = (error) => {
            if (settled) return;
            settled = true;
            cleanup();
            if (error) {
                script.remove();
                reject(error);
                return;
            }
            resolve();
        };

        script.src = src;
        script.async = true;
        script.defer = true;
        script.onload = () => finish(null);
        script.onerror = () => finish(new Error(`Failed to load script: ${src}`));
        document.head.appendChild(script);
    });
}

async function ensureJoystickLibrary() {
    if (typeof window.nipplejs !== 'undefined') {
        return true;
    }
    if (!joystickScriptPromise) {
        joystickScriptPromise = (async () => {
            for (const src of JOYSTICK_SCRIPT_URLS) {
                try {
                    await loadScriptWithTimeout(src, JOYSTICK_SCRIPT_LOAD_TIMEOUT_MS);
                    if (typeof window.nipplejs !== 'undefined') {
                        return true;
                    }
                } catch (err) {
                    console.warn(err);
                }
            }
            return false;
        })();
    }
    return joystickScriptPromise;
}

async function initControlsPage() {
    bindControlsPage();
    refreshControlsChrome();
    initGamepad();
    const hasJoystickLibrary = await ensureJoystickLibrary();
    if (!hasJoystickLibrary) {
        const hint = document.querySelector('.ctl-hint');
        if (hint) {
            hint.textContent = 'Knihovna joysticku se nenačetla. Zbývají klávesy W S A D a Q E.';
        }
        return;
    }
    initJoysticks();
}


/* === WEBSOCKET LOGIKA === */
function initWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
    }

    if (wsConnectTimer) {
        clearTimeout(wsConnectTimer);
        wsConnectTimer = null;
    }

    const connElem = document.getElementById("conn");
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${wsProtocol}://${location.host}/ws`);
    const socket = ws;

    wsConnectTimer = setTimeout(() => {
        if (socket.readyState === WebSocket.CONNECTING) {
            console.warn('WebSocket connect timeout. Retrying...');
            socket.close();
        }
    }, WS_CONNECT_TIMEOUT_MS);

    ws.onopen = () => {
        if (wsConnectTimer) {
            clearTimeout(wsConnectTimer);
            wsConnectTimer = null;
        }
        if (connElem) {
            connElem.textContent = "✅ Připojeno";
            connElem.style.color = "green";
        }
        if (testingMode()) {
            userRole = 'admin';
            updateUI();
        }
        refreshControlsChrome();
        requestAdminFromToken();
    };

    ws.onclose = () => {
        if (wsConnectTimer) {
            clearTimeout(wsConnectTimer);
            wsConnectTimer = null;
        }
        if (connElem) {
            connElem.textContent = "❌ Odpojeno";
            connElem.style.color = "red";
        }
        userRole = 'spectator';
        updateUI();
        refreshControlsChrome();
        // Zkusíme se znovu připojit po 2 sekundách
        wsReconnectTimer = setTimeout(initWebSocket, WS_RECONNECT_DELAY_MS);
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case "status":
                    const cpuElem = document.getElementById("cpu-val");
                    const ramElem = document.getElementById("ram-val");
                    const tempElem = document.getElementById("temp-val");

                    if (cpuElem) cpuElem.textContent = data.cpu.toFixed(1);
                    if (ramElem) ramElem.textContent = data.ram.toFixed(1);
                    if (tempElem) {
                        tempElem.textContent = data.temp.toFixed(1);
                        tempElem.style.color = data.temp > 60 ? "#ff4444" : "inherit";
                    }
                    break;

                case "odom":
                    // updateRobotPosition je nyní globální
                    if (typeof window.updateRobotPosition === "function") {
                        window.updateRobotPosition(data.x, data.y);
                    }
                    break;

                case "lidar":
                    // updateLidarScan je nyní globální
                    if (typeof window.updateLidarScan === "function") {
                        window.updateLidarScan(data);
                    }
                    break;

                case "sensor_catalog":
                    if (typeof window.handleSensorCatalog === "function") {
                        window.handleSensorCatalog(data.sensors);
                    }
                    break;

                case "sensor_data":
                    if (typeof window.handleSensorData === "function") {
                        window.handleSensorData(data);
                    }
                    break;

                case "tf_2d":
                    if (typeof window.handleMapTfFrames === "function") {
                        window.handleMapTfFrames(data);
                    }
                    /* Backward compatibility for legacy pages/scripts */
                    if (
                        typeof window.handleTfFrames === "function" &&
                        window.handleTfFrames !== window.handleMapTfFrames
                    ) {
                        window.handleTfFrames(data);
                    }
                    break;

                case "tf_3d":
                    if (typeof window.handleTfPage3d === "function") {
                        window.handleTfPage3d(data);
                    }
                    break;

                case "tf_status":
                    if (typeof window.handleTfPageStatus === "function") {
                        window.handleTfPageStatus(data);
                    }
                    break;

                case "map_grid":
                    if (typeof window.updateMapGrid === "function") {
                        window.updateMapGrid(data);
                    }
                    break;

                case "map_updates":
                    if (typeof window.updateMapUpdates === "function") {
                        window.updateMapUpdates(data);
                    }
                    break;

                case "nav_path":
                    if (typeof window.updateNavPath === "function") {
                        window.updateNavPath(data.path);
                    }
                    break;

                case "goal_pose":
                    if (typeof window.updateGoalPose === "function") {
                        window.updateGoalPose(data);
                    }
                    break;

                case "role_update":
                    userRole = data.role;
                    if (userRole === 'admin' && window.prompt_pin) {
                         localStorage.setItem(ADMIN_TOKEN_KEY, window.prompt_pin);
                    }
                    updateUI();
                    break;

                case "e_stop":
                    estopActive = Boolean(data.active);
                    estopKnown = true;
                    if (estopActive) {
                        stopCommand();
                    }
                    refreshControlsChrome();
                    break;

                case "user_list_update":
                    updateUserList(data.users);
                    break;
                
                case "error":
                    alert(`Server Error: ${data.message}`);
                    break;

                case "info":
                    console.info(`Server Info: ${data.message}`);
                    break;
            }
        } catch (e) {
            console.error("Chyba při parsování dat:", e);
        }
    };

    ws.onerror = (err) => {
        console.error("Chyba WebSocketu:", err);
        if (ws && ws.readyState === WebSocket.CONNECTING) {
            ws.close();
        }
    };
}

/* === SPRÁVA OPRÁVNĚNÍ A UŽIVATELŮ === */

function updateUI() {
    const roleStatusElem = document.getElementById('role-status');
    const kickButton = document.querySelector('.permissions-controls .btn-kick');

    if (roleStatusElem) {
        roleStatusElem.textContent = userRole.charAt(0).toUpperCase() + userRole.slice(1);
        roleStatusElem.className = `role-label role-${userRole}`;
    }
    
    if (kickButton) {
        kickButton.style.display = userRole === 'admin' ? 'inline-block' : 'none';
    }

    if (userRole === 'spectator') {
        document.body.classList.add('is-spectator');
    } else {
        document.body.classList.remove('is-spectator');
    }
    refreshControlsChrome();
}

function updateUserList(users) {
    const container = document.getElementById('user-list-container');
    if (!container) return;

    container.innerHTML = '';
    users.forEach(user => {
        const userElement = document.createElement('div');
        userElement.className = 'user-item';
        
        let html = `
            <div class="user-info">
                <span class="user-ip">${user.id}</span>
                <span class="role-label role-${user.role}">${user.role}</span>
            </div>
        `;

        if (userRole === 'admin' && user.role === 'operator') {
            html += `<div class="user-actions">
                         <button class="btn-kick-small" onclick="kickOperator()">Odebrat</button>
                     </div>`;
        }

        userElement.innerHTML = html;
        container.appendChild(userElement);
    });
}

function requestControl(role) {
    const pin = prompt(`Zadejte PIN pro roli '${role}':`);
    if (pin) {
        if (role === 'admin') window.prompt_pin = pin; 
        
        ws.send(JSON.stringify({
            type: role === 'admin' ? 'request_admin' : 'request_operator',
            pin: pin
        }));
    }
}

function requestAdminFromToken() {
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    if (token) {
        ws.send(JSON.stringify({ type: 'request_admin', pin: token }));
    }
}

function kickOperator() {
    if (userRole === 'admin') {
        if (confirm("Opravdu chcete odebrat práva aktuálnímu operátorovi?")) {
            ws.send(JSON.stringify({ type: 'kick_operator' }));
        }
    } else {
        alert("Tuto akci může provést pouze admin.");
    }
}

/* === ODESÍLÁNÍ PŘÍKAZŮ Z MAPY === */
window.sendGoalPoseCommand = function(x, y, yaw) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        const payload = {
            type: "set_goal_pose",
            x: parseFloat(x),
            y: parseFloat(y),
            yaw: parseFloat(yaw)
        };
        ws.send(JSON.stringify(payload));
    }
}

/* === ODESÍLÁNÍ PŘÍKAZŮ Z JOYSTICKU / GAMEPADU === */
const SPEED_KEY = 'rmodus.controls.speed.v2';
let speedScale = readSpeedScale();
let estopActive = false;
let estopKnown = false;
let gamepadName = '';
const keyHold = { w: false, a: false, s: false, d: false, q: false, e: false };
let lastCmd = { y: 0, x: 0, r: 0 };

function readSpeedScale() {
    const raw = localStorage.getItem(SPEED_KEY);
    const saved = Number(raw);
    if (raw !== null && raw !== '' && Number.isFinite(saved) && saved >= 0 && saved <= 1) {
        return saved;
    }
    return 0.5;
}

function clampUnit(value) {
    return Math.max(-1, Math.min(1, value));
}

function keyVector() {
    let y = 0;
    let x = 0;
    let r = 0;
    if (keyHold.w) y += 1;
    if (keyHold.s) y -= 1;
    if (keyHold.d) x += 1;
    if (keyHold.a) x -= 1;
    if (keyHold.q) r += 1;
    if (keyHold.e) r -= 1;
    return { y, x, r, active: y !== 0 || x !== 0 || r !== 0 };
}

function mergedCommand() {
    const keys = keyVector();
    return {
        y: clampUnit(joyState.y + keys.y),
        x: clampUnit(joyState.x + keys.x),
        r: clampUnit(joyState.rotation + keys.r),
    };
}

function sendJoystickData(y, x, rotation) {
    const scale = speedScale;
    const sy = Number(y) * scale;
    const sx = Number(x) * scale;
    const sr = Number(rotation) * scale;
    lastCmd = { y: sy, x: sx, r: sr };
    paintCommandMeters();
    if (estopKnown && estopActive) {
        sy = 0;
        sx = 0;
        sr = 0;
    }
    if (ws && ws.readyState === WebSocket.OPEN && userRole !== 'spectator') {
        ws.send(JSON.stringify({
            type: 'cmd_joy',
            linear_y: sy,
            linear_x: sx,
            angular_z: sr,
        }));
    }
}

function paintCommandMeters() {
    const vx = document.getElementById('ctl-vx');
    const vy = document.getElementById('ctl-vy');
    const wz = document.getElementById('ctl-wz');
    if (vx) vx.textContent = lastCmd.y.toFixed(2);
    if (vy) vy.textContent = lastCmd.x.toFixed(2);
    if (wz) wz.textContent = lastCmd.r.toFixed(2);
    const arrow = document.getElementById('ctl-arrow');
    const dot = document.getElementById('ctl-dot');
    const arc = document.getElementById('ctl-arc');
    const reach = 46;
    const px = 80 + Math.max(-1, Math.min(1, lastCmd.x)) * reach;
    const py = 80 - Math.max(-1, Math.min(1, lastCmd.y)) * reach;
    if (arrow) {
        arrow.setAttribute('x2', px.toFixed(1));
        arrow.setAttribute('y2', py.toFixed(1));
    }
    if (dot) {
        dot.setAttribute('cx', px.toFixed(1));
        dot.setAttribute('cy', py.toFixed(1));
    }
    if (arc) {
        const sweep = Math.max(-1, Math.min(1, lastCmd.r));
        if (Math.abs(sweep) < 0.02) {
            arc.setAttribute('d', '');
        } else {
            const a0 = -Math.PI / 2;
            const a1 = a0 - sweep * Math.PI;
            const r = 58;
            const x0 = 80 + r * Math.cos(a0);
            const y0 = 80 + r * Math.sin(a0);
            const x1 = 80 + r * Math.cos(a1);
            const y1 = 80 + r * Math.sin(a1);
            const dir = sweep > 0 ? 0 : 1;
            arc.setAttribute('d', `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 0 ${dir} ${x1.toFixed(1)} ${y1.toFixed(1)}`);
        }
    }
    const chip = document.getElementById('ctl-cmd');
    if (!chip) return;
    const moving = Math.abs(lastCmd.y) + Math.abs(lastCmd.x) + Math.abs(lastCmd.r) > 0.001;
    chip.classList.toggle('is-live', moving);
    chip.querySelector('strong').textContent = moving ? 'jede' : 'stojí';
}

function refreshControlsChrome() {
    const role = document.querySelector('#ctl-role strong');
    const link = document.querySelector('#ctl-link strong');
    const linkChip = document.getElementById('ctl-link');
    const estop = document.querySelector('#ctl-estop strong');
    const estopChip = document.getElementById('ctl-estop');
    const pad = document.querySelector('#ctl-pad strong');
    const lock = document.getElementById('ctl-lock');
    if (role) role.textContent = userRole;
    if (link && linkChip) {
        const open = ws && ws.readyState === WebSocket.OPEN;
        link.textContent = open ? 'připojeno' : 'odpojeno';
        linkChip.classList.toggle('is-live', open);
        linkChip.classList.toggle('is-bad', !open);
    }
    if (estop && estopChip) {
        estop.textContent = estopKnown ? (estopActive ? 'zamčeno' : 'volno') : '—';
        estopChip.classList.toggle('is-bad', estopKnown && estopActive);
        estopChip.classList.toggle('is-live', estopKnown && !estopActive);
    }
    if (pad) pad.textContent = gamepadName || 'nepřipojen';
    if (lock) lock.hidden = userRole !== 'spectator';
    paintCommandMeters();
}

function bindControlsPage() {
    const speed = document.getElementById('ctl-speed');
    const speedVal = document.getElementById('ctl-speed-val');
    if (speed) {
        speed.value = String(Math.round(speedScale * 100));
        if (speedVal) speedVal.textContent = `${speed.value} %`;
        speed.oninput = () => {
            speedScale = Number(speed.value) / 100;
            localStorage.setItem(SPEED_KEY, String(speedScale));
            if (speedVal) speedVal.textContent = `${speed.value} %`;
        };
    }
    const stop = document.getElementById('ctl-stop');
    if (stop) stop.onclick = () => stopCommand();
    const estopBtn = document.getElementById('ctl-estop-btn');
    if (estopBtn) estopBtn.onclick = () => sendControlMessage('e_stop_trigger');
    const resetBtn = document.getElementById('ctl-estop-reset');
    if (resetBtn) resetBtn.onclick = () => sendControlMessage('e_stop_reset');
}

function sendControlMessage(type) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type }));
}

function stopCommand() {
    Object.keys(keyHold).forEach((key) => { keyHold[key] = false; });
    joyState.y = 0;
    joyState.x = 0;
    joyState.rotation = 0;
    joyState.move = false;
    joyState.rotate = false;
    gamepadActive = false;
    updateJoyRepeat();
    sendJoystickData(0, 0, 0);
}

function onControlKey(event, down) {
    if (activePage !== 'controls') return;
    if (event.repeat) return;
    const tag = (event.target && event.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    const key = event.key.toLowerCase();
    if (!(key in keyHold)) return;
    event.preventDefault();
    if (userRole === 'spectator') return;
    keyHold[key] = down;
    const keys = keyVector();
    if (keys.active || !down) {
        sendJoyState();
        updateJoyRepeat();
    }
}

const joyManager = {
    move: null,
    rotate: null
};

// cmd_mux zahodí vstup po 0,5 s bez zprávy, proto držený joystick posílá stále.
const JOY_REPEAT_MS = 100;
const joyState = { y: 0, x: 0, rotation: 0, move: false, rotate: false };
let joyRepeatTimer = null;
let gamepadActive = false;

function sendJoyState() {
    const cmd = mergedCommand();
    sendJoystickData(cmd.y, cmd.x, cmd.r);
}

function updateJoyRepeat() {
    const active = joyState.move || joyState.rotate || keyVector().active;
    if (active && !joyRepeatTimer) {
        joyRepeatTimer = setInterval(sendJoyState, JOY_REPEAT_MS);
    } else if (!active && joyRepeatTimer) {
        clearInterval(joyRepeatTimer);
        joyRepeatTimer = null;
    }
}

function resetJoyState() {
    Object.assign(joyState, { y: 0, x: 0, rotation: 0, move: false, rotate: false });
    updateJoyRepeat();
}

function initJoysticks() {
    if (typeof window.nipplejs === 'undefined') {
        console.warn('nipplejs library is not available.');
        return;
    }
    if (joyManager.move) {
        joyManager.move.destroy();
        joyManager.move = null;
    }
    if (joyManager.rotate) {
        joyManager.rotate.destroy();
        joyManager.rotate = null;
    }
    resetJoyState();

    const commonOptions = {
        mode: 'static',
        position: { top: '50%', left: '50%' },
        size: 150,
        color: '#00d4ff',
        dynamicPage: true
    };

    const moveZone = document.getElementById('joy-move');
    const rotateZone = document.getElementById('joy-rotate');

    if (moveZone) {
        joyManager.move = nipplejs.create({ zone: moveZone, ...commonOptions });
        joyManager.move.on('move', (evt, data) => {
            if (!data.vector) return;
            joyState.y = data.vector.y;
            joyState.x = data.vector.x;
            joyState.move = true;
            sendJoyState();
            updateJoyRepeat();
        }).on('end', () => {
            joyState.y = 0;
            joyState.x = 0;
            joyState.move = false;
            sendJoyState();
            updateJoyRepeat();
        });
    }

    if (rotateZone) {
        joyManager.rotate = nipplejs.create({ zone: rotateZone, ...commonOptions, color: '#ff9500' });
        joyManager.rotate.on('move', (evt, data) => {
            if (!data.vector) return;
            joyState.rotation = -data.vector.x;
            joyState.rotate = true;
            sendJoyState();
            updateJoyRepeat();
        }).on('end', () => {
            joyState.rotation = 0;
            joyState.rotate = false;
            sendJoyState();
            updateJoyRepeat();
        });
    }
}

let gamepadInterval = null;

function setGamepadName(name) {
    gamepadName = name || '';
    const chip = document.getElementById('ctl-pad');
    if (chip) chip.classList.toggle('is-live', Boolean(gamepadName));
    refreshControlsChrome();
}

function initGamepad() {
    if (!gamepadListenersInitialized) {
        window.addEventListener('gamepadconnected', (e) => {
            setGamepadName(e.gamepad.id);
            if (!gamepadInterval) {
                gamepadInterval = setInterval(pollGamepads, 100);
            }
        });
        window.addEventListener('gamepaddisconnected', () => {
            setGamepadName('');
            clearInterval(gamepadInterval);
            gamepadInterval = null;
            if (gamepadActive) {
                gamepadActive = false;
                sendJoystickData(0, 0, 0);
            }
        });
        window.addEventListener('keydown', (event) => onControlKey(event, true));
        window.addEventListener('keyup', (event) => onControlKey(event, false));
        gamepadListenersInitialized = true;
    }
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    const connected = pads && pads[0];
    if (connected) {
        setGamepadName(connected.id);
        if (!gamepadInterval) {
            gamepadInterval = setInterval(pollGamepads, 100);
        }
    }
}

function pollGamepads() {
    const gamepads = navigator.getGamepads();
    if (gamepads[0]) {
        const gp = gamepads[0];
        const deadZone = 0.15;

        let y = -gp.axes[1];
        let x = gp.axes[0];
        let rotation = -gp.axes[2];

        if (Math.abs(y) < deadZone) y = 0;
        if (Math.abs(x) < deadZone) x = 0;
        if (Math.abs(rotation) < deadZone) rotation = 0;
        
        if (userRole === 'spectator') return;
        if (y !== 0 || x !== 0 || rotation !== 0) {
            gamepadActive = true;
            joyState.y = y;
            joyState.x = x;
            joyState.rotation = rotation;
            joyState.move = true;
            sendJoyState();
        } else if (gamepadActive) {
            gamepadActive = false;
            joyState.y = 0;
            joyState.x = 0;
            joyState.rotation = 0;
            joyState.move = false;
            sendJoyState();
        }
    }
}