/* Map page rendering and goal interaction */
const mapState = {
    initialized: false,
    canvas: null,
    ctx: null,
    drawScheduled: false,

    /* Data from websocket */
    map: null, /* { frameId, width, height, resolution, origin:{x,y}, data:[] } */
    robotPose: null, /* { x, y, yaw, inMapFrame } */
    navPath: null, /* [{x,y}, ...] */
    lidarScan: null, /* { angle_min, angle_increment, max_range, ranges } */

    /* View controls */
    zoom: 1.0,
    followRobot: false, /* false => keep map origin (0,0) in center */
    showLidar: false,
    margin: 20,
    viewRotationRad: Math.PI / 2, /* Additional 180 deg rotation */

    /* Goal interaction */
    goalMode: 'inactive', /* inactive | waiting_direction */
    goalPending: null, /* {x, y, yaw} */
    goalCommitted: null, /* {x, y, yaw} */
};

const BASE_FRAME_PRIORITY = ['base_footprint', 'base_link'];
const GRID_STEP_METERS = 1.0;

/* ------------------------------
 * Initialization
 * ------------------------------ */
window.initMap = function initMap() {
    const canvas = document.getElementById('mapCanvas');
    if (!canvas) {
        console.error('Map canvas not found');
        return;
    }

    mapState.canvas = canvas;
    mapState.ctx = canvas.getContext('2d');
    mapState.initialized = true;

    updateCanvasSize();
    window.addEventListener('resize', updateCanvasSize);
    canvas.addEventListener('click', handleCanvasClick);
    canvas.addEventListener('contextmenu', (event) => {
        event.preventDefault();
        cancelGoal();
    });

    const zoomSlider = document.getElementById('mapZoom');
    if (zoomSlider) {
        zoomSlider.value = String(mapState.zoom);
        zoomSlider.addEventListener('input', (event) => {
            mapState.zoom = clamp(Number.parseFloat(event.target.value) || 1.0, 0.2, 6.0);
            requestDraw();
        });
    }

    const followRobotToggle = document.getElementById('autoCenterToggle');
    if (followRobotToggle) {
        followRobotToggle.checked = mapState.followRobot;
        followRobotToggle.addEventListener('change', (event) => {
            mapState.followRobot = Boolean(event.target.checked);
            requestDraw();
        });
    }

    const showLidarToggle = document.getElementById('showLidarToggle');
    if (showLidarToggle) {
        showLidarToggle.checked = mapState.showLidar;
        showLidarToggle.addEventListener('change', (event) => {
            mapState.showLidar = Boolean(event.target.checked);
            if (!mapState.showLidar) {
                mapState.lidarScan = null;
            }
            requestDraw();
        });
    }

    const cancelButton = document.getElementById('btnCancelGoal');
    if (cancelButton) {
        cancelButton.addEventListener('click', cancelGoal);
    }

    const sendButton = document.getElementById('btnSendGoal');
    if (sendButton) {
        sendButton.addEventListener('click', confirmGoal);
    }

    updateGoalUI();
    requestDraw();
};

function updateCanvasSize() {
    if (!mapState.canvas) return;
    const wrapper = mapState.canvas.parentElement;
    if (!wrapper) return;

    mapState.canvas.width = Math.max(1, wrapper.clientWidth);
    mapState.canvas.height = Math.max(1, wrapper.clientHeight);
    requestDraw();
}

function requestDraw() {
    if (!mapState.initialized || mapState.drawScheduled) return;
    mapState.drawScheduled = true;
    window.requestAnimationFrame(() => {
        mapState.drawScheduled = false;
        draw();
    });
}

/* ------------------------------
 * Input from websocket
 * ------------------------------ */
window.updateMapGrid = function updateMapGrid(payload) {
    mapState.map = normalizeMapPayload(payload);
    requestDraw();
};

window.updateMapUpdates = function updateMapUpdates(payload) {
    const update = normalizeMapPayload(payload);
    if (!update) return;

    if (!mapState.map) {
        mapState.map = update;
        requestDraw();
        return;
    }

    if (!canApplyMapUpdate(mapState.map, update)) {
        mapState.map = update;
        requestDraw();
        return;
    }

    applyMapUpdate(mapState.map, update);
    requestDraw();
};

window.updateNavPath = function updateNavPath(path) {
    mapState.navPath = Array.isArray(path) ? path : null;
    requestDraw();
};

window.updateGoalPose = function updateGoalPose(payload) {
    const normalized = normalizeGoalPayload(payload);
    if (!normalized) return;

    const mapFrameId = normalizeFrameId(mapState.map?.frameId) || 'map';
    if (normalized.frameId && normalized.frameId !== mapFrameId) {
        return;
    }

    mapState.goalCommitted = {
        x: normalized.x,
        y: normalized.y,
        yaw: normalized.yaw,
    };
    requestDraw();
};

window.updateRobotPose = function updateRobotPose(x, y, yaw) {
    setRobotPose(x, y, yaw, false);
};

window.updateRobotPosition = function updateRobotPosition(x, y, yaw) {
    setRobotPose(x, y, yaw, false);
};

window.updateLidarScan = function updateLidarScan(payload) {
    if (!mapState.showLidar) return;
    if (!payload || !Array.isArray(payload.ranges)) return;

    mapState.lidarScan = {
        angle_min: Number(payload.angle_min) || 0,
        angle_increment: Number(payload.angle_increment) || 0,
        max_range: Number(payload.max_range) || 0,
        ranges: payload.ranges,
    };
    requestDraw();
};

window.handleMapTfFrames = function handleMapTfFrames(payload) {
    const frames = Array.isArray(payload?.frames) ? payload.frames : [];
    if (frames.length === 0) return;

    const mapFrameId = normalizeFrameId(mapState.map?.frameId) || 'map';
    const childFrameMap = buildChildFrameMap(frames);

    for (const baseFrameId of BASE_FRAME_PRIORITY) {
        const baseFrame = childFrameMap.get(baseFrameId);
        if (!baseFrame) continue;

        const resolved = resolvePoseToRoot(childFrameMap, baseFrameId, mapFrameId);
        if (resolved) {
            setRobotPose(resolved.x, resolved.y, resolved.yaw, true);
            return;
        }
    }

    /* Fallback: raw base frame transform if map chain is unavailable */
    for (const baseFrameId of BASE_FRAME_PRIORITY) {
        const baseFrame = childFrameMap.get(baseFrameId);
        if (baseFrame) {
            setRobotPose(baseFrame.x, baseFrame.y, baseFrame.yaw, false);
            return;
        }
    }
};

function normalizeMapPayload(payload) {
    if (!payload || !Array.isArray(payload.data)) return null;
    const width = Number(payload.width) || 0;
    const height = Number(payload.height) || 0;
    const resolution = Number(payload.resolution) || 0;
    if (width <= 0 || height <= 0 || resolution <= 0) return null;

    return {
        frameId: normalizeFrameId(payload.frame_id) || 'map',
        width,
        height,
        resolution,
        origin: {
            x: Number(payload.origin?.x) || 0,
            y: Number(payload.origin?.y) || 0,
        },
        data: payload.data.slice(),
    };
}

function normalizeGoalPayload(payload) {
    if (!payload) return null;
    const x = Number(payload.x);
    const y = Number(payload.y);
    const yaw = Number(payload.yaw);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;

    return {
        x,
        y,
        yaw: Number.isFinite(yaw) ? yaw : 0,
        frameId: normalizeFrameId(payload.frame_id) || 'map',
    };
}

function canApplyMapUpdate(baseMap, update) {
    if (!baseMap || !update) return false;
    if (baseMap.frameId !== update.frameId) return false;
    if (!almostEqual(baseMap.resolution, update.resolution)) return false;
    return true;
}

function applyMapUpdate(baseMap, update) {
    const colOffset = Math.round((update.origin.x - baseMap.origin.x) / baseMap.resolution);
    const rowOffset = Math.round((update.origin.y - baseMap.origin.y) / baseMap.resolution);

    if (colOffset < 0 || rowOffset < 0) {
        mapState.map = update;
        return;
    }
    if (colOffset + update.width > baseMap.width || rowOffset + update.height > baseMap.height) {
        mapState.map = update;
        return;
    }

    for (let row = 0; row < update.height; row += 1) {
        for (let col = 0; col < update.width; col += 1) {
            const dstCol = colOffset + col;
            const dstRow = rowOffset + row;
            const dstIndex = dstRow * baseMap.width + dstCol;
            const srcIndex = row * update.width + col;
            baseMap.data[dstIndex] = update.data[srcIndex];
        }
    }
}

/* ------------------------------
 * TF / robot pose helpers
 * ------------------------------ */
function normalizeFrameId(frameId) {
    if (!frameId) return '';
    return String(frameId).replace(/^\/+/, '');
}

function normalizeAngle(angle) {
    let value = Number(angle) || 0;
    while (value > Math.PI) value -= Math.PI * 2;
    while (value < -Math.PI) value += Math.PI * 2;
    return value;
}

function setRobotPose(x, y, yaw, inMapFrame) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    mapState.robotPose = {
        x,
        y,
        yaw: Number.isFinite(yaw) ? yaw : (mapState.robotPose?.yaw || 0),
        inMapFrame: Boolean(inMapFrame),
    };
    requestDraw();
}

function buildChildFrameMap(frames) {
    const map = new Map();
    frames.forEach((frame) => {
        const child = normalizeFrameId(frame?.child_frame_id);
        if (!child) return;
        map.set(child, {
            child,
            parent: normalizeFrameId(frame.parent_frame_id),
            x: Number(frame.x) || 0,
            y: Number(frame.y) || 0,
            yaw: Number(frame.yaw) || 0,
        });
    });
    return map;
}

function resolvePoseToRoot(childFrameMap, targetFrameId, rootFrameId) {
    const target = normalizeFrameId(targetFrameId);
    const root = normalizeFrameId(rootFrameId);
    if (!target || !root) return null;

    let currentId = target;
    let pose = { x: 0, y: 0, yaw: 0 };
    const visited = new Set();

    while (currentId && !visited.has(currentId)) {
        if (currentId === root) {
            return pose;
        }
        visited.add(currentId);

        const frame = childFrameMap.get(currentId);
        if (!frame) return null;

        const prevX = pose.x;
        const prevY = pose.y;
        const cosYaw = Math.cos(frame.yaw);
        const sinYaw = Math.sin(frame.yaw);

        pose = {
            x: frame.x + cosYaw * prevX - sinYaw * prevY,
            y: frame.y + sinYaw * prevX + cosYaw * prevY,
            yaw: normalizeAngle(frame.yaw + pose.yaw),
        };

        currentId = frame.parent;
    }

    return null;
}

/* ------------------------------
 * Rendering helpers
 * ------------------------------ */
function getViewport() {
    const canvasWidth = mapState.canvas.width;
    const canvasHeight = mapState.canvas.height;
    const margin = mapState.margin;
    const availWidth = Math.max(1, canvasWidth - margin * 2);
    const availHeight = Math.max(1, canvasHeight - margin * 2);

    let ppm = 45 * mapState.zoom;
    if (mapState.map) {
        const mapMetersX = mapState.map.width * mapState.map.resolution;
        const mapMetersY = mapState.map.height * mapState.map.resolution;
        const fitPpm = Math.min(availWidth / mapMetersX, availHeight / mapMetersY);
        ppm = Math.max(0.05, fitPpm * mapState.zoom);
    }

    const centerWorld = { x: 0, y: 0 };
    const pose = mapState.robotPose;
    const hasPose = pose && Number.isFinite(pose.x) && Number.isFinite(pose.y);
    /* Without occupancy map, lidar preview keeps the robot centered. */
    const lidarOnlyView = mapState.showLidar && !mapState.map;
    const shouldFollow =
        hasPose &&
        (
            (mapState.followRobot && pose.inMapFrame) ||
            lidarOnlyView
        );

    if (shouldFollow) {
        centerWorld.x = pose.x;
        centerWorld.y = pose.y;
    }

    return {
        margin,
        ppm,
        centerScreenX: margin + availWidth / 2,
        centerScreenY: margin + availHeight / 2,
        centerWorldX: centerWorld.x,
        centerWorldY: centerWorld.y,
        minX: centerWorld.x - availWidth / (2 * ppm),
        maxX: centerWorld.x + availWidth / (2 * ppm),
        minY: centerWorld.y - availHeight / (2 * ppm),
        maxY: centerWorld.y + availHeight / (2 * ppm),
        availWidth,
        availHeight,
    };
}

function worldToScreen(x, y, viewport) {
    const dx = x - viewport.centerWorldX;
    const dy = y - viewport.centerWorldY;
    const cosA = Math.cos(mapState.viewRotationRad);
    const sinA = Math.sin(mapState.viewRotationRad);
    const rx = cosA * dx - sinA * dy;
    const ry = sinA * dx + cosA * dy;

    return {
        x: viewport.centerScreenX + rx * viewport.ppm,
        y: viewport.centerScreenY - ry * viewport.ppm,
    };
}

function screenToWorld(screenX, screenY, viewport) {
    const rx = (screenX - viewport.centerScreenX) / viewport.ppm;
    const ry = -(screenY - viewport.centerScreenY) / viewport.ppm;
    const cosA = Math.cos(mapState.viewRotationRad);
    const sinA = Math.sin(mapState.viewRotationRad);
    const dx = cosA * rx + sinA * ry;
    const dy = -sinA * rx + cosA * ry;

    return {
        x: viewport.centerWorldX + dx,
        y: viewport.centerWorldY + dy,
    };
}

/* ------------------------------
 * Main draw
 * ------------------------------ */
function draw() {
    if (!mapState.initialized) return;
    const viewport = getViewport();
    const ctx = mapState.ctx;

    drawBackground(ctx);
    drawViewportBorder(ctx, viewport);
    drawGrid(ctx, viewport);
    drawMap(ctx, viewport);
    drawLidarScan(ctx, viewport);
    drawNavPath(ctx, viewport);
    drawGoals(ctx, viewport);
    drawRobot(ctx, viewport);
    if (mapState.map) {
        drawMapOriginMarker(ctx, viewport);
    }
}

function drawBackground(ctx) {
    ctx.fillStyle = '#5f6f6f';
    ctx.fillRect(0, 0, mapState.canvas.width, mapState.canvas.height);
}

function drawViewportBorder(ctx, viewport) {
    ctx.strokeStyle = 'rgba(0, 212, 255, 0.28)';
    ctx.lineWidth = 2;
    ctx.strokeRect(
        viewport.margin,
        viewport.margin,
        viewport.availWidth,
        viewport.availHeight
    );
}

function drawGrid(ctx, viewport) {
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)';
    ctx.lineWidth = 1;

    const startX = Math.ceil(viewport.minX / GRID_STEP_METERS) * GRID_STEP_METERS;
    for (let x = startX; x <= viewport.maxX; x += GRID_STEP_METERS) {
        const a = worldToScreen(x, viewport.minY, viewport);
        const b = worldToScreen(x, viewport.maxY, viewport);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
    }

    const startY = Math.ceil(viewport.minY / GRID_STEP_METERS) * GRID_STEP_METERS;
    for (let y = startY; y <= viewport.maxY; y += GRID_STEP_METERS) {
        const a = worldToScreen(viewport.minX, y, viewport);
        const b = worldToScreen(viewport.maxX, y, viewport);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
    }
}

function drawMap(ctx, viewport) {
    if (!mapState.map) return;

    const map = mapState.map;
    const resolution = map.resolution;
    const originX = map.origin.x;
    const originY = map.origin.y;
    const cellSize = Math.max(1, Math.ceil(resolution * viewport.ppm));

    const startCol = clampInt(Math.floor((viewport.minX - originX) / resolution), 0, map.width - 1);
    const endCol = clampInt(Math.ceil((viewport.maxX - originX) / resolution), 0, map.width - 1);
    const startRow = clampInt(Math.floor((viewport.minY - originY) / resolution), 0, map.height - 1);
    const endRow = clampInt(Math.ceil((viewport.maxY - originY) / resolution), 0, map.height - 1);

    for (let row = startRow; row <= endRow; row += 1) {
        const worldY = originY + (row + 0.5) * resolution;
        for (let col = startCol; col <= endCol; col += 1) {
            const idx = row * map.width + col;
            const value = map.data[idx];
            if (!Number.isFinite(value)) continue;

            if (value < 0) {
                ctx.fillStyle = '#7f8888';
            } else if (value > 50) {
                ctx.fillStyle = '#111111';
            } else {
                ctx.fillStyle = '#d7d7d7';
            }

            const worldX = originX + (col + 0.5) * resolution;
            const screen = worldToScreen(worldX, worldY, viewport);
            ctx.fillRect(
                Math.round(screen.x - cellSize / 2),
                Math.round(screen.y - cellSize / 2),
                cellSize,
                cellSize
            );
        }
    }
}

function drawNavPath(ctx, viewport) {
    if (!Array.isArray(mapState.navPath) || mapState.navPath.length === 0) return;

    ctx.strokeStyle = '#635bff';
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();

    mapState.navPath.forEach((point, index) => {
        if (!Number.isFinite(point?.x) || !Number.isFinite(point?.y)) return;
        const screen = worldToScreen(point.x, point.y, viewport);
        if (index === 0) ctx.moveTo(screen.x, screen.y);
        else ctx.lineTo(screen.x, screen.y);
    });

    ctx.stroke();
}

function getDrawRobotPose() {
    const pose = mapState.robotPose;
    if (pose && Number.isFinite(pose.x) && Number.isFinite(pose.y)) {
        return pose;
    }
    /* Lidar-only preview: keep the same robot glyph centered even without TF. */
    if (mapState.showLidar) {
        return { x: 0, y: 0, yaw: 0, inMapFrame: false };
    }
    return null;
}

function drawLidarScan(ctx, viewport) {
    if (!mapState.showLidar) return;
    const scan = mapState.lidarScan;
    if (!scan || !Array.isArray(scan.ranges) || scan.ranges.length === 0) return;

    const pose = getDrawRobotPose();
    if (!pose) return;

    const yaw = Number.isFinite(pose.yaw) ? pose.yaw : 0;
    const angleMin = Number(scan.angle_min) || 0;
    const angleInc = Number(scan.angle_increment) || 0;
    const maxRange = Number(scan.max_range) || 0;
    const pointSize = Math.max(2, Math.min(3, viewport.ppm * 0.04));

    ctx.fillStyle = 'rgba(255, 149, 0, 0.9)';
    for (let i = 0; i < scan.ranges.length; i += 1) {
        const range = Number(scan.ranges[i]);
        if (!Number.isFinite(range) || range <= 0) continue;
        if (maxRange > 0 && range > maxRange) continue;

        const angle = yaw + angleMin + i * angleInc;
        const worldX = pose.x + Math.cos(angle) * range;
        const worldY = pose.y + Math.sin(angle) * range;
        const screen = worldToScreen(worldX, worldY, viewport);
        ctx.fillRect(
            Math.round(screen.x - pointSize / 2),
            Math.round(screen.y - pointSize / 2),
            pointSize,
            pointSize
        );
    }
}

function drawRobot(ctx, viewport) {
    const pose = getDrawRobotPose();
    if (!pose) return;
    drawDirectionalMarker(ctx, viewport, pose, {
        front: 0.34,
        rear: 0.25,
        halfWidth: 0.2,
        fillStyle: '#2f5eff',
        strokeStyle: '#dbe8ff',
        headingStyle: '#8df08d',
        headingLength: 0.52,
    });
}

function drawGoalMarker(ctx, viewport, goal, active = false) {
    drawDirectionalMarker(ctx, viewport, goal, {
        front: 0.3,
        rear: 0.22,
        halfWidth: 0.17,
        fillStyle: active ? 'rgba(24, 196, 132, 0.7)' : 'rgba(24, 196, 132, 0.45)',
        strokeStyle: active ? 'rgba(166, 255, 223, 0.95)' : 'rgba(166, 255, 223, 0.75)',
        headingStyle: active ? 'rgba(24, 240, 160, 0.95)' : 'rgba(24, 240, 160, 0.75)',
        headingLength: 0.48,
    });
}

function drawGoals(ctx, viewport) {
    if (mapState.goalCommitted) {
        drawGoalMarker(ctx, viewport, mapState.goalCommitted, false);
    }
    if (mapState.goalPending) {
        drawGoalMarker(ctx, viewport, mapState.goalPending, true);
    }
}

function buildMarkerHull(pose, front, rear, halfWidth) {
    const yaw = Number.isFinite(pose.yaw) ? pose.yaw : 0;
    const fx = Math.cos(yaw);
    const fy = Math.sin(yaw);
    const sx = Math.cos(yaw + Math.PI / 2);
    const sy = Math.sin(yaw + Math.PI / 2);

    return [
        { x: pose.x + fx * front, y: pose.y + fy * front }, /* nose */
        {
            x: pose.x + fx * (front * 0.2) + sx * halfWidth,
            y: pose.y + fy * (front * 0.2) + sy * halfWidth,
        },
        {
            x: pose.x - fx * (rear * 0.7) + sx * (halfWidth * 0.8),
            y: pose.y - fy * (rear * 0.7) + sy * (halfWidth * 0.8),
        },
        { x: pose.x - fx * rear, y: pose.y - fy * rear }, /* tail */
        {
            x: pose.x - fx * (rear * 0.7) - sx * (halfWidth * 0.8),
            y: pose.y - fy * (rear * 0.7) - sy * (halfWidth * 0.8),
        },
        {
            x: pose.x + fx * (front * 0.2) - sx * halfWidth,
            y: pose.y + fy * (front * 0.2) - sy * halfWidth,
        },
    ];
}

function drawRoundedHullPath(ctx, screenPoints) {
    if (!Array.isArray(screenPoints) || screenPoints.length < 3) return;
    const count = screenPoints.length;
    const mid = (a, b) => ({ x: (a.x + b.x) * 0.5, y: (a.y + b.y) * 0.5 });
    const firstMid = mid(screenPoints[0], screenPoints[1]);

    ctx.beginPath();
    ctx.moveTo(firstMid.x, firstMid.y);
    for (let i = 1; i <= count; i += 1) {
        const p = screenPoints[i % count];
        const next = screenPoints[(i + 1) % count];
        const m = mid(p, next);
        ctx.quadraticCurveTo(p.x, p.y, m.x, m.y);
    }
    ctx.closePath();
}

function drawDirectionalMarker(ctx, viewport, pose, style) {
    if (!pose || !Number.isFinite(pose.x) || !Number.isFinite(pose.y)) return;

    const hull = buildMarkerHull(pose, style.front, style.rear, style.halfWidth);
    const hullScreen = hull.map((point) => worldToScreen(point.x, point.y, viewport));
    const centerScreen = worldToScreen(pose.x, pose.y, viewport);
    const yaw = Number.isFinite(pose.yaw) ? pose.yaw : 0;
    const headingEnd = worldToScreen(
        pose.x + Math.cos(yaw) * style.headingLength,
        pose.y + Math.sin(yaw) * style.headingLength,
        viewport
    );

    ctx.fillStyle = style.fillStyle;
    drawRoundedHullPath(ctx, hullScreen);
    ctx.fill();

    ctx.strokeStyle = style.strokeStyle;
    ctx.lineWidth = 1.4;
    ctx.stroke();

    ctx.strokeStyle = style.headingStyle;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(centerScreen.x, centerScreen.y);
    ctx.lineTo(headingEnd.x, headingEnd.y);
    ctx.stroke();
}

function drawMapOriginMarker(ctx, viewport) {
    const origin = worldToScreen(0, 0, viewport);
    const length = 10;

    ctx.strokeStyle = 'rgba(255, 80, 80, 0.95)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(origin.x - length, origin.y);
    ctx.lineTo(origin.x + length, origin.y);
    ctx.stroke();

    ctx.strokeStyle = 'rgba(80, 255, 120, 0.95)';
    ctx.beginPath();
    ctx.moveTo(origin.x, origin.y - length);
    ctx.lineTo(origin.x, origin.y + length);
    ctx.stroke();
}

/* ------------------------------
 * Goal UI and interactions
 * ------------------------------ */
function handleCanvasClick(event) {
    const viewport = getViewport();
    const rect = mapState.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const world = screenToWorld(x, y, viewport);

    if (mapState.goalMode === 'inactive') {
        mapState.goalMode = 'waiting_direction';
        mapState.goalPending = { x: world.x, y: world.y, yaw: 0 };
        updateGoalUI();
        requestDraw();
        return;
    }

    if (mapState.goalMode === 'waiting_direction' && mapState.goalPending) {
        const dx = world.x - mapState.goalPending.x;
        const dy = world.y - mapState.goalPending.y;
        if (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6) {
            mapState.goalPending.yaw = Math.atan2(dy, dx);
        }
        updateGoalUI();
        requestDraw();
    }
}

function confirmGoal() {
    const goal = mapState.goalPending;
    if (!goal) return;

    if (typeof window.sendGoalPoseCommand === 'function') {
        window.sendGoalPoseCommand(goal.x, goal.y, goal.yaw);
    }

    mapState.goalCommitted = { ...goal };
    cancelGoal();
}

function cancelGoal() {
    mapState.goalMode = 'inactive';
    mapState.goalPending = null;
    updateGoalUI();
    requestDraw();
}

function updateGoalUI() {
    const goalStatus = document.getElementById('goalStatus');
    const coordsPanel = document.getElementById('goalCoordinates');
    const goalX = document.getElementById('goalX');
    const goalY = document.getElementById('goalY');
    const goalYaw = document.getElementById('goalYaw');
    const cancelBtn = document.getElementById('btnCancelGoal');
    const sendBtn = document.getElementById('btnSendGoal');

    if (!mapState.goalPending) {
        if (goalStatus) goalStatus.textContent = 'Pro zadání cíle klikněte na mapu';
        if (coordsPanel) coordsPanel.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (sendBtn) sendBtn.style.display = 'none';
        return;
    }

    if (goalStatus) goalStatus.textContent = 'Druhým kliknutím určete směr';
    if (coordsPanel) {
        coordsPanel.style.display = 'block';
        if (goalX) goalX.textContent = mapState.goalPending.x.toFixed(2);
        if (goalY) goalY.textContent = mapState.goalPending.y.toFixed(2);
        if (goalYaw) goalYaw.textContent = (mapState.goalPending.yaw * 180 / Math.PI).toFixed(1);
    }
    if (cancelBtn) cancelBtn.style.display = 'block';
    if (sendBtn) sendBtn.style.display = 'block';
}

/* ------------------------------
 * Utility
 * ------------------------------ */
function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function clampInt(value, min, max) {
    if (max < min) return min;
    return Math.min(Math.max(value, min), max);
}

function almostEqual(a, b, epsilon = 1e-6) {
    return Math.abs((Number(a) || 0) - (Number(b) || 0)) <= epsilon;
}

/* Export for debugging from browser console */
window.mapState = mapState;
