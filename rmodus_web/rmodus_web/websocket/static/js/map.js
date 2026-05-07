/* Global state for map rendering */
const mapState = {
    initialized: false,
    canvas: null,
    ctx: null,
    
    /* Map data from /map topic */
    map: null,
    
    /* Robot pose from /tf */
    robotPose: null,
    
    /* Navigation path from /received_global_plan */
    navPath: null,
    
    /* UI state */
    zoom: 1.0,
    goalMode: 'inactive', /* 'inactive', 'waiting_position', 'waiting_direction' */
    goalPending: null, /* { x, y, yaw } at any step */
};

/* Initialize map rendering */
window.initMap = function() {
    const canvas = document.getElementById('mapCanvas');
    if (!canvas) {
        console.error('Map canvas not found!');
        return;
    }
    
    mapState.canvas = canvas;
    mapState.ctx = canvas.getContext('2d');
    mapState.initialized = true;
    
    /* Resize canvas to fill container */
    updateCanvasSize();
    window.addEventListener('resize', updateCanvasSize);
    
    /* Add click handler for goal setting */
    canvas.addEventListener('click', handleCanvasClick);
    
    /* Right-click to cancel */
    canvas.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        cancelGoal();
    });
    
    /* Add zoom slider handler */
    const zoomSlider = document.getElementById('mapZoom');
    if (zoomSlider) {
        zoomSlider.addEventListener('input', (e) => {
            mapState.zoom = parseFloat(e.target.value);
            draw();
        });
    }
    
    /* Setup buttons */
    const btnCancel = document.getElementById('btnCancelGoal');
    const btnSend = document.getElementById('btnSendGoal');
    
    if (btnCancel) {
        btnCancel.addEventListener('click', cancelGoal);
    }
    if (btnSend) {
        btnSend.addEventListener('click', confirmGoal);
    }
    
    console.log('Map initialized successfully');
    draw();
};

function updateCanvasSize() {
    const container = mapState.canvas.parentElement;
    mapState.canvas.width = container.clientWidth;
    mapState.canvas.height = container.clientHeight;
    draw();
}

/* Update map data from websocket */
window.updateMapGrid = function(data) {
    mapState.map = data;
    draw();
};

window.updateRobotPose = function(x, y, yaw) {
    mapState.robotPose = { x, y, yaw };
    draw();
};

window.updateNavPath = function(path) {
    mapState.navPath = path;
    draw();
};

window.handleTfFrames = function(data) {
    if (!data.frames) return;
    
    /* Find robot base frame */
    const baseFrame = data.frames.find(f => 
        f.child_frame_id === 'base_link' || 
        f.child_frame_id === 'base_footprint'
    );
    
    if (baseFrame) {
        mapState.robotPose = {
            x: baseFrame.x,
            y: baseFrame.y,
            yaw: baseFrame.yaw || 0
        };
        draw();
    }
};

/* Calculate viewport to center map in rectangular area */
function getViewport() {
    if (!mapState.map) return null;
    
    const canvasWidth = mapState.canvas.width;
    const canvasHeight = mapState.canvas.height;
    
    const mapWidth = mapState.map.width;
    const mapHeight = mapState.map.height;
    const resolution = mapState.map.resolution;
    
    /* Map dimensions in meters */
    const mapMetersX = mapHeight * resolution; /* height = X dimension */
    const mapMetersY = mapWidth * resolution;  /* width = Y dimension */
    
    /* Available draw area (with small margin) */
    const margin = 20;
    const availWidth = canvasWidth - margin * 2;
    const availHeight = canvasHeight - margin * 2;
    
    /* Calculate pixels per meter to fit map */
    let ppm = Math.min(
        availWidth / mapMetersY,
        availHeight / mapMetersX
    ) * mapState.zoom;
    ppm = Math.max(ppm, 0.1);
    
    /* Map origin and center in world coords */
    const mapOriginX = mapState.map.origin.x;
    const mapOriginY = mapState.map.origin.y;
    const mapCenterX = mapOriginX + mapMetersX / 2;
    const mapCenterY = mapOriginY + mapMetersY / 2;
    
    /* Viewport dimensions in world meters */
    const viewportMetersX = availHeight / ppm;
    const viewportMetersY = availWidth / ppm;
    
    /* Viewport bounds (centered on map) */
    const minX = mapCenterX - viewportMetersX / 2;
    const minY = mapCenterY - viewportMetersY / 2;
    
    return {
        ppm,
        margin,
        canvasWidth,
        canvasHeight,
        minX,
        minY,
        maxX: minX + viewportMetersX,
        maxY: minY + viewportMetersY,
        centerScreenX: margin + availWidth / 2,
        centerScreenY: margin + availHeight / 2,
        availWidth,
        availHeight
    };
}

/* Convert world coordinates to canvas coordinates */
function worldToScreen(x, y, viewport) {
    if (!viewport) return null;
    
    return {
        x: viewport.centerScreenX - (y - viewport.minY) * viewport.ppm,
        y: viewport.centerScreenY - (x - viewport.minX) * viewport.ppm,
    };
}

/* Convert canvas coordinates to world coordinates */
function screenToWorld(screenX, screenY, viewport) {
    if (!viewport) return null;
    
    return {
        x: viewport.minX + (viewport.centerScreenY - screenY) / viewport.ppm,
        y: viewport.minY + (viewport.centerScreenX - screenX) / viewport.ppm,
    };
}

/* Main draw function */
function draw() {
    if (!mapState.initialized) return;
    
    const viewport = getViewport();
    if (!viewport) {
        drawPlaceholder();
        return;
    }
    
    /* Clear background */
    drawBackground();
    
    /* Draw center rectangle border */
    drawMapBorder(viewport);
    
    /* Draw grid */
    drawGrid(viewport);
    
    /* Draw occupancy grid */
    if (mapState.map) {
        drawMap(viewport);
    }
    
    /* Draw navigation path */
    if (mapState.navPath) {
        drawNavPath(viewport);
    }
    
    /* Draw goal preview */
    if (mapState.goalPending) {
        drawGoalPreview(viewport);
    }
    
    /* Draw robot */
    if (mapState.robotPose) {
        drawRobot(viewport);
    }
}

function drawPlaceholder() {
    mapState.ctx.fillStyle = '#1a1f2e';
    mapState.ctx.fillRect(0, 0, mapState.canvas.width, mapState.canvas.height);
    
    mapState.ctx.fillStyle = '#666';
    mapState.ctx.font = '16px sans-serif';
    mapState.ctx.textAlign = 'center';
    mapState.ctx.fillText('Čekám na data mapy...', mapState.canvas.width / 2, mapState.canvas.height / 2);
}

function drawBackground() {
    const gradient = mapState.ctx.createLinearGradient(0, 0, 0, mapState.canvas.height);
    gradient.addColorStop(0, '#0f1419');
    gradient.addColorStop(1, '#1a1f2e');
    mapState.ctx.fillStyle = gradient;
    mapState.ctx.fillRect(0, 0, mapState.canvas.width, mapState.canvas.height);
}

function drawMapBorder(viewport) {
    /* Draw rectangular border around map area */
    mapState.ctx.strokeStyle = 'rgba(0, 212, 255, 0.3)';
    mapState.ctx.lineWidth = 2;
    
    mapState.ctx.strokeRect(
        viewport.margin,
        viewport.margin,
        viewport.availWidth,
        viewport.availHeight
    );
}

function drawGrid(viewport) {
    const stepMeters = 1.0;
    mapState.ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    mapState.ctx.lineWidth = 1;
    
    /* Vertical lines (X direction) */
    for (let x = Math.ceil(viewport.minX); x <= viewport.maxX; x += stepMeters) {
        const start = worldToScreen(x, viewport.minY, viewport);
        const end = worldToScreen(x, viewport.maxY, viewport);
        if (start && end) {
            mapState.ctx.beginPath();
            mapState.ctx.moveTo(start.x, start.y);
            mapState.ctx.lineTo(end.x, end.y);
            mapState.ctx.stroke();
        }
    }
    
    /* Horizontal lines (Y direction) */
    for (let y = Math.ceil(viewport.minY); y <= viewport.maxY; y += stepMeters) {
        const start = worldToScreen(viewport.minX, y, viewport);
        const end = worldToScreen(viewport.maxX, y, viewport);
        if (start && end) {
            mapState.ctx.beginPath();
            mapState.ctx.moveTo(start.x, start.y);
            mapState.ctx.lineTo(end.x, end.y);
            mapState.ctx.stroke();
        }
    }
}

function drawMap(viewport) {
    if (!mapState.map || !mapState.map.data) return;
    
    const resolution = mapState.map.resolution;
    const width = mapState.map.width;
    const height = mapState.map.height;
    const originX = mapState.map.origin.x;
    const originY = mapState.map.origin.y;
    const data = mapState.map.data;
    
    mapState.ctx.fillStyle = 'rgba(80, 80, 80, 0.7)';
    
    for (let row = 0; row < height; row++) {
        for (let col = 0; col < width; col++) {
            const idx = row * width + col;
            const value = data[idx];
            
            /* 0 = free, 100 = occupied, -1 = unknown */
            if (value > 50) {
                const x = originX + col * resolution;
                const y = originY + row * resolution;
                const screen = worldToScreen(x, y, viewport);
                
                if (screen) {
                    const size = Math.max(1, Math.ceil(viewport.ppm * resolution));
                    mapState.ctx.fillRect(screen.x - size/2, screen.y - size/2, size, size);
                }
            }
        }
    }
}

function drawNavPath(viewport) {
    if (!mapState.navPath || mapState.navPath.length === 0) return;
    
    mapState.ctx.strokeStyle = '#4f46e5';
    mapState.ctx.lineWidth = 2;
    mapState.ctx.lineCap = 'round';
    mapState.ctx.lineJoin = 'round';
    
    mapState.ctx.beginPath();
    for (let i = 0; i < mapState.navPath.length; i++) {
        const point = mapState.navPath[i];
        const screen = worldToScreen(point.x, point.y, viewport);
        if (screen) {
            if (i === 0) {
                mapState.ctx.moveTo(screen.x, screen.y);
            } else {
                mapState.ctx.lineTo(screen.x, screen.y);
            }
        }
    }
    mapState.ctx.stroke();
}

function drawGoalPreview(viewport) {
    if (!mapState.goalPending) return;
    
    const screen = worldToScreen(mapState.goalPending.x, mapState.goalPending.y, viewport);
    if (!screen) return;
    
    /* Draw goal circle */
    mapState.ctx.fillStyle = 'rgba(74, 222, 128, 0.4)';
    mapState.ctx.beginPath();
    mapState.ctx.arc(screen.x, screen.y, 15, 0, 2 * Math.PI);
    mapState.ctx.fill();
    
    /* Draw goal border */
    mapState.ctx.strokeStyle = 'rgba(74, 222, 128, 0.8)';
    mapState.ctx.lineWidth = 2;
    mapState.ctx.stroke();
    
    /* Draw heading indicator if direction is set */
    if (mapState.goalMode === 'waiting_direction') {
        const headingLen = 25;
        const headingDx = Math.cos(mapState.goalPending.yaw) * headingLen;
        const headingDy = Math.sin(mapState.goalPending.yaw) * headingLen;
        
        mapState.ctx.strokeStyle = 'rgba(74, 222, 128, 1)';
        mapState.ctx.lineWidth = 2;
        mapState.ctx.beginPath();
        mapState.ctx.moveTo(screen.x, screen.y);
        mapState.ctx.lineTo(screen.x + headingDx, screen.y + headingDy);
        mapState.ctx.stroke();
        
        /* Arrow tip */
        const arrowSize = 8;
        mapState.ctx.beginPath();
        mapState.ctx.moveTo(screen.x + headingDx, screen.y + headingDy);
        mapState.ctx.lineTo(screen.x + headingDx - Math.cos(mapState.goalPending.yaw - 0.3) * arrowSize,
                           screen.y + headingDy - Math.sin(mapState.goalPending.yaw - 0.3) * arrowSize);
        mapState.ctx.lineTo(screen.x + headingDx - Math.cos(mapState.goalPending.yaw + 0.3) * arrowSize,
                           screen.y + headingDy - Math.sin(mapState.goalPending.yaw + 0.3) * arrowSize);
        mapState.ctx.closePath();
        mapState.ctx.fill();
    }
}

function drawRobot(viewport) {
    if (!mapState.robotPose) return;
    
    const screen = worldToScreen(mapState.robotPose.x, mapState.robotPose.y, viewport);
    if (!screen) return;
    
    /* Draw robot triangle */
    const size = 12;
    const angle = mapState.robotPose.yaw;
    
    mapState.ctx.save();
    mapState.ctx.translate(screen.x, screen.y);
    mapState.ctx.rotate(angle);
    
    mapState.ctx.fillStyle = '#7c3aed';
    mapState.ctx.beginPath();
    mapState.ctx.moveTo(size, 0);
    mapState.ctx.lineTo(-size/2, size);
    mapState.ctx.lineTo(-size/2, -size);
    mapState.ctx.closePath();
    mapState.ctx.fill();
    
    /* Draw glow */
    mapState.ctx.strokeStyle = 'rgba(124, 58, 237, 0.5)';
    mapState.ctx.lineWidth = 1;
    mapState.ctx.stroke();
    
    mapState.ctx.restore();
}

function handleCanvasClick(event) {
    const viewport = getViewport();
    if (!viewport) return;
    
    const rect = mapState.canvas.getBoundingClientRect();
    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;
    
    const world = screenToWorld(screenX, screenY, viewport);
    if (!world) return;
    
    if (mapState.goalMode === 'inactive') {
        /* First click: place goal position */
        mapState.goalPending = { x: world.x, y: world.y, yaw: 0 };
        mapState.goalMode = 'waiting_direction';
        updateGoalUI();
        draw();
    } else if (mapState.goalMode === 'waiting_direction') {
        /* Second click: set heading */
        const dx = world.x - mapState.goalPending.x;
        const dy = world.y - mapState.goalPending.y;
        
        if (dx !== 0 || dy !== 0) {
            mapState.goalPending.yaw = Math.atan2(dy, dx);
        }
        
        updateGoalUI();
        draw();
    }
}

function updateGoalUI() {
    const goalStatus = document.getElementById('goalStatus');
    const goalCoords = document.getElementById('goalCoordinates');
    const goalX = document.getElementById('goalX');
    const goalY = document.getElementById('goalY');
    const goalYaw = document.getElementById('goalYaw');
    const btnCancel = document.getElementById('btnCancelGoal');
    const btnSend = document.getElementById('btnSendGoal');
    const mapInstruction = document.getElementById('mapInstruction');
    
    if (!mapState.goalPending) {
        /* Inactive state */
        if (goalStatus) goalStatus.textContent = 'Klikněte na mapu pro zadání cíle';
        if (goalCoords) goalCoords.style.display = 'none';
        if (btnCancel) btnCancel.style.display = 'none';
        if (btnSend) btnSend.style.display = 'none';
        if (mapInstruction) mapInstruction.textContent = '1. Klik = vstupní bod';
    } else if (mapState.goalMode === 'waiting_direction') {
        /* Waiting for direction */
        if (goalStatus) goalStatus.textContent = '🎯 Klikněte znovu pro nastavení směru';
        if (goalCoords) {
            goalCoords.style.display = 'block';
            goalX.textContent = mapState.goalPending.x.toFixed(2);
            goalY.textContent = mapState.goalPending.y.toFixed(2);
            goalYaw.textContent = (mapState.goalPending.yaw * 180 / Math.PI).toFixed(1);
        }
        if (btnCancel) btnCancel.style.display = 'block';
        if (btnSend) btnSend.style.display = 'block';
        if (mapInstruction) mapInstruction.textContent = '2. Klik = finální směr (nebo tlačítko)';
    }
}

function confirmGoal() {
    if (!mapState.goalPending) return;
    
    /* Send goal to backend */
    if (window.sendGoalPoseCommand) {
        window.sendGoalPoseCommand(
            mapState.goalPending.x,
            mapState.goalPending.y,
            mapState.goalPending.yaw
        );
    }
    
    cancelGoal();
}

function cancelGoal() {
    mapState.goalMode = 'inactive';
    mapState.goalPending = null;
    updateGoalUI();
    draw();
}

/* Export for use by app.js */
window.mapState = mapState;
