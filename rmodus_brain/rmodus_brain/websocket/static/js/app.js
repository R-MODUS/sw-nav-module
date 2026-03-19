/* === KONFIGURACE A PROMĚNNÉ === */
let ws;
let userRole = 'spectator'; // Výchozí role
const ADMIN_TOKEN_KEY = 'robot_admin_token';
let activePage = '';

/* === HLAVNÍ LOGIKA APLIKACE === */

// Načítání stránek (SPA - Single Page Application)
window.loadPage = async function(pageName) {
    // Nenačítat znovu, pokud je již aktivní
    if (pageName === activePage) return;

    try {
        const response = await fetch(`static/pages/${pageName}.html`);
        if (!response.ok) {
            throw new Error(`Failed to load page: ${response.status} ${response.statusText}`);
        }
        const html = await response.text();
        document.getElementById('main-content').innerHTML = html;
        activePage = pageName;

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
                    initJoysticks();
                    initGamepad();
                } else if (pageName === 'map') {
                    // initMap() je definována v map.js
                    if (typeof initMap === 'function') {
                        initMap();
                    } else {
                        console.error("initMap function not found. Was map.js loaded correctly?");
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
document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    updateUI();
    // Načtení výchozí stránky
    window.loadPage('status');
});


/* === WEBSOCKET LOGIKA === */
function initWebSocket() {
    const connElem = document.getElementById("conn");
    ws = new WebSocket(`ws://${location.host}/ws`);

    ws.onopen = () => {
        if (connElem) {
            connElem.textContent = "✅ Připojeno";
            connElem.style.color = "green";
        }
        requestAdminFromToken();
    };

    ws.onclose = () => {
        if (connElem) {
            connElem.textContent = "❌ Odpojeno";
            connElem.style.color = "red";
        }
        userRole = 'spectator';
        updateUI();
        // Zkusíme se znovu připojit po 2 sekundách
        setTimeout(initWebSocket, 2000);
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

                case "role_update":
                    userRole = data.role;
                    if (userRole === 'admin' && window.prompt_pin) {
                         localStorage.setItem(ADMIN_TOKEN_KEY, window.prompt_pin);
                    }
                    updateUI();
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

/* === ODESÍLÁNÍ PŘÍKAZŮ Z JOYSTICKU / GAMEPADU === */
function sendJoystickData(y, x, rotation) {
    if (ws && ws.readyState === WebSocket.OPEN && userRole !== 'spectator') {
        const payload = {
            type: "cmd_joy",
            linear_y: parseFloat(y),
            linear_x: parseFloat(x),
            angular_z: parseFloat(rotation)
        };
        ws.send(JSON.stringify(payload));
    }
}

const joyManager = {
    move: null,
    rotate: null
};

function initJoysticks() {
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
            if (data.vector) sendJoystickData(data.vector.y, data.vector.x, 0);
        }).on('end', () => sendJoystickData(0, 0, 0));
    }

    if (rotateZone) {
        joyManager.rotate = nipplejs.create({ zone: rotateZone, ...commonOptions, color: '#ff9500' });
        joyManager.rotate.on('move', (evt, data) => {
            if (data.vector) sendJoystickData(0, 0, -data.vector.x);
        }).on('end', () => sendJoystickData(0, 0, 0));
    }
}

let gamepadInterval = null;

function initGamepad() {
    const statusElem = document.getElementById('gamepad-status');
    if (statusElem) statusElem.textContent = 'Hledám gamepad...';

    window.addEventListener("gamepadconnected", (e) => {
        if (statusElem) {
            statusElem.textContent = `✅ Gamepad připojen: ${e.gamepad.id}`;
            statusElem.style.color = 'green';
        }
        if (!gamepadInterval) {
            gamepadInterval = setInterval(pollGamepads, 100);
        }
    });

    window.addEventListener("gamepaddisconnected", () => {
        if (statusElem) {
            statusElem.textContent = 'Gamepad odpojen.';
            statusElem.style.color = '#888';
        }
        clearInterval(gamepadInterval);
        gamepadInterval = null;
    });
}

function pollGamepads() {
    const gamepads = navigator.getGamepads();
    if (gamepads[0]) {
        const gp = gamepads[0];
        const deadZone = 0.15;

        let y = -gp.axes[1];
        let x = gp.axes[0];
        let rotation = gp.axes[2];

        if (Math.abs(y) < deadZone) y = 0;
        if (Math.abs(x) < deadZone) x = 0;
        if (Math.abs(rotation) < deadZone) rotation = 0;
        
        if (userRole !== 'spectator' && (y !== 0 || x !== 0 || rotation !== 0)) {
            sendJoystickData(y.toFixed(2), x.toFixed(2), rotation.toFixed(2));
        }
    }
}