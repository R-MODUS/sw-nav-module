// Global state for map rendering
const mapState = {
    initialized: false,
    canvas: null,
    ctx: null,
    
    // Map data from /map topic
    map: null,
    mapUpdates: [],
    
    // Robot pose from /tf
    robotPose: null,
    
    // Navigation path from /received_global_plan
    navPath: null,
    
    // UI state
    zoom: 1.0,
    goalModeActive: false,
    goalPending: null,
    goalFinal: null,
};

// Initialize map rendering
window.initMap = function() {
    const canvas = document.getElementById('mapCanvas');
    if (!canvas) {
        console.error('Map canvas not found!');
        return;
    }
    
    mapState.canvas = canvas;
    mapState.ctx = canvas.getContext('2d');
    mapState.initialized = true;
    
    // Resize canvas to fill container
    updateCanvasSize();
    window.addEventListener('resize', updateCanvasSize);
    
    // Add click handler for goal setting
    canvas.addEventListener('click', handleCanvasClick);
    canvas.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        mapState.goalPending = null;
        mapState.goalFinal = null;
        draw();
    });
    
    // Add zoom slider handler
    const zoomSlider = document.getElementById('mapZoom');
    if (zoomSlider) {
        zoomSlider.addEventListener('input', (e) => {
            mapState.zoom = parseFloat(e.target.value);
            draw();
        });
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

// Update map data from websocket
window.updateMapGrid = function(data) {
    mapState.map = data;
    mapState.mapUpdates = [];
    draw();
};

window.updateMapUpdates = function(data) {
    if (mapState.mapUpdates.length > 100) {
        mapState.mapUpdates = mapState.mapUpdates.slice(-100);
    }
    mapState.mapUpdates.push(data);
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
    
    // Find robot base frame (usually "base_link")
    const baseFrame = data.frames.find(f => f.child_frame_id === 'base_link' || f.child_frame_id === 'base_footprint');
    if (baseFrame) {
        mapState.robotPose = {
            x: baseFrame.x,
            y: baseFrame.y,
            yaw: baseFrame.yaw || 0
        };
        draw();
    }
};

// Calculate viewport to center on map with padding
function getViewport() {
    if (!mapState.map) return null;
    
    const padding = 36;
    const mapWidth = mapState.map.width;
    const mapHeight = mapState.map.height;
    const resolution = mapState.map.resolution;
    
    const metersX = mapHeight * resolution; // map height = world X
    const metersY = mapWidth * resolution;  // map width = world Y
    
    // Available draw area
    const availWidth = mapState.canvas.width - padding * 2;
    const availHeight = mapState.canvas.height - padding * 2;
    
    // Pixels per meter, applying zoom
    let ppm = Math.min(
        availWidth / metersY,
        availHeight / metersX
    ) * mapState.zoom;
    ppm = Math.max(ppm, 0.1);
    
    // Center viewport on map center
    const mapOriginX = mapState.map.origin.x;
    const mapOriginY = mapState.map.origin.y;
    const mapCenterX = mapOriginX + metersX / 2;
    const mapCenterY = mapOriginY + metersY / 2;
    
    const viewportMetersX = availHeight / ppm;
    const viewportMetersY = availWidth / ppm;
    
    const minX = mapCenterX - viewportMetersX / 2;
    const minY = mapCenterY - viewportMetersY / 2;
    
    return {
        ppm,
        padding,
        minX,
        minY,
        maxX: minX + viewportMetersX,
        maxY: minY + viewportMetersY,
        centerScreenX: padding + availWidth / 2,
        centerScreenY: padding + availHeight / 2,
    };
}

// Convert world coordinates to canvas coordinates
function worldToScreen(x, y, viewport) {
    if (!viewport) return null;
    
    return {
        x: viewport.centerScreenX - (y - viewport.minY) * viewport.ppm,
        y: viewport.centerScreenY - (x - viewport.minX) * viewport.ppm,
    };
}

// Convert canvas coordinates to world coordinates
function screenToWorld(screenX, screenY, viewport) {
    if (!viewport) return null;
    
    return {
        x: viewport.minX + (viewport.centerScreenY - screenY) / viewport.ppm,
        y: viewport.minY + (viewport.centerScreenX - screenX) / viewport.ppm,
    };
}

// Main draw function
function draw() {
    if (!mapState.initialized) return;
    
    const viewport = getViewport();
    if (!viewport) {
        drawPlaceholder();
        return;
    }
    
    // Clear background
    drawBackground();
    
    // Draw grid
    drawGrid(viewport);
    
    // Draw occupancy grid
    if (mapState.map) {
        drawMap(viewport);
    }
    
    // Draw navigation path
    if (mapState.navPath) {
        drawNavPath(viewport);
    }
    
    // Draw goal preview
    if (mapState.goalPending) {
        drawGoalPreview(viewport);
    }
    
    // Draw robot
    if (mapState.robotPose) {
        drawRobot(viewport);
    }
}

function drawPlaceholder() {
    mapState.ctx.fillStyle = '#f6f3ee';
    mapState.ctx.fillRect(0, 0, mapState.canvas.width, mapState.canvas.height);
    
    mapState.ctx.fillStyle = '#999';
    mapState.ctx.font = '14px sans-serif';
    mapState.ctx.textAlign = 'center';
    mapState.ctx.fillText('Waiting for map data...', mapState.canvas.width / 2, mapState.canvas.height / 2);
}

function drawBackground() {
    const gradient = mapState.ctx.createLinearGradient(0, 0, 0, mapState.canvas.height);
    gradient.addColorStop(0, '#f6f3ee');
    gradient.addColorStop(1, '#ddd7cf');
    mapState.ctx.fillStyle = gradient;
    mapState.ctx.fillRect(0, 0, mapState.canvas.width, mapState.canvas.height);
}

function drawGrid(viewport) {
    const stepMeters = 1.0;
    mapState.ctx.strokeStyle = 'rgba(17, 24, 39, 0.08)';
    mapState.ctx.lineWidth = 1;
    
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
    
    mapState.ctx.fillStyle = 'rgba(60, 60, 60, 0.8)';
    
    for (let row = 0; row < height; row++) {
        for (let col = 0; col < width; col++) {
            const idx = row * width + col;
            const value = data[idx];
            
            // 0 = free, 100 = occupied, -1 = unknown
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
    const screen = worldToScreen(mapState.goalPending.x, mapState.goalPending.y, viewport);
    if (!screen) return;
    
    // Draw goal circle
    mapState.ctx.fillStyle = 'rgba(74, 222, 128, 0.5)';
    mapState.ctx.beginPath();
    mapState.ctx.arc(screen.x, screen.y, 15, 0, 2 * Math.PI);
    mapState.ctx.fill();
    
    // Draw heading indicator
    const headingLen = 20;
    const headingDx = Math.cos(mapState.goalPending.yaw) * headingLen;
    const headingDy = Math.sin(mapState.goalPending.yaw) * headingLen;
    
    mapState.ctx.strokeStyle = 'rgba(74, 222, 128, 0.8)';
    mapState.ctx.lineWidth = 2;
    mapState.ctx.beginPath();
    mapState.ctx.moveTo(screen.x, screen.y);
    mapState.ctx.lineTo(screen.x + headingDx, screen.y + headingDy);
    mapState.ctx.stroke();
}

function drawRobot(viewport) {
    if (!mapState.robotPose) return;
    
    const screen = worldToScreen(mapState.robotPose.x, mapState.robotPose.y, viewport);
    if (!screen) return;
    
    // Draw robot triangle
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
    
    if (!mapState.goalPending) {
        // First click: place goal
        mapState.goalPending = { x: world.x, y: world.y, yaw: 0 };
        draw();
    } else {
        // Second click: set heading and send goal
        const dx = world.x - mapState.goalPending.x;
        const dy = world.y - mapState.goalPending.y;
        mapState.goalPending.yaw = Math.atan2(dy, dx);
        mapState.goalFinal = { ...mapState.goalPending };
        
        // Send goal to backend
        if (window.sendGoalPoseCommand) {
            window.sendGoalPoseCommand(
                mapState.goalFinal.x,
                mapState.goalFinal.y,
                mapState.goalFinal.yaw
            );
        }
        
        mapState.goalPending = null;
        draw();
    }
}

// Export for use by app.js
window.mapState = mapState;
