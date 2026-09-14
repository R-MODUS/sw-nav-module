(() => {
    const LIVE_STALE_MS = 3000;

    const SENSOR_TYPE_LABELS = {
        lidar: 'LiDAR',
        imu: 'IMU',
        bumper: 'Detekce kolizí',
        cliff: 'Detekce schodiště',
        optical_flow: 'Optický tok',
    };

    const METRIC_FIELD_LABELS = {
        angle_min: 'Úhel min.',
        angle_max: 'Úhel max.',
        angle_increment: 'Krok úhlu',
        time_increment: 'Krok času',
        scan_time: 'Doba skenu',
        range_min: 'Dosah min.',
        range_max: 'Dosah max.',
        max_range: 'Max. dosah',
        ranges: 'Vzdálenosti',
        intensities: 'Intenzity',
        linear_acceleration_x: 'Zrychlení x',
        linear_acceleration_y: 'Zrychlení y',
        linear_acceleration_z: 'Zrychlení z',
        angular_velocity_x: 'Úhlová rychlost x',
        angular_velocity_y: 'Úhlová rychlost y',
        angular_velocity_z: 'Úhlová rychlost z',
        yaw: 'Natáčení (yaw)',
        contact: 'Kontakt',
        width: 'Šířka',
        range: 'Dosah',
        normalized_range: 'Normalizovaný dosah',
        field_of_view: 'Zorné pole',
        vx: 'Rychlost x',
        vy: 'Rychlost y',
        vz: 'Rychlost z',
    };

    const TILE_METRIC_KEYS = {
        lidar: ['max_range', 'ranges'],
        imu: ['yaw', 'angular_velocity_z'],
        bumper: ['contact', 'width'],
        cliff: ['range', 'normalized_range'],
        optical_flow: ['vx', 'vy'],
    };

    const state = {
        catalog: [],
        latestByKey: {},
        lastSeenByKey: {},
        pinnedKeys: new Set(),
        expandedKey: null,
        prefsLoaded: false,
        liveTimer: null,
    };

    function prefsApi() {
        return window.RmodusUiPrefs || null;
    }

    function sensorKey(sensorType, sensorId) {
        return `${sensorType}:${sensorId}`;
    }

    function normalizeFrameId(frameId) {
        if (!frameId) {
            return null;
        }
        return String(frameId).replace(/^\/+/, '');
    }

    function sensorTypeDisplayName(sensorType) {
        if (!sensorType) {
            return '—';
        }
        return SENSOR_TYPE_LABELS[sensorType] || String(sensorType).replace(/_/g, ' ');
    }

    function metricFieldLabel(key) {
        return METRIC_FIELD_LABELS[key] || key;
    }

    function loadPrefs() {
        const api = prefsApi();
        if (!api || !api.isEnabled()) {
            state.prefsLoaded = false;
            return;
        }
        const pinned = api.get('sensors.pinned', null);
        if (Array.isArray(pinned)) {
            state.pinnedKeys = new Set(pinned.map(String));
            state.prefsLoaded = true;
        } else {
            state.prefsLoaded = false;
        }
    }

    function savePinned() {
        const api = prefsApi();
        if (!api || !api.isEnabled()) {
            return;
        }
        api.set('sensors.pinned', [...state.pinnedKeys]);
        state.prefsLoaded = true;
    }

    function groupedCatalog() {
        return state.catalog.reduce((acc, sensor) => {
            if (!acc[sensor.sensor_type]) {
                acc[sensor.sensor_type] = [];
            }
            acc[sensor.sensor_type].push(sensor);
            return acc;
        }, {});
    }

    function syncPinnedWithCatalog() {
        const validKeys = new Set(state.catalog.map((s) => sensorKey(s.sensor_type, s.sensor_id)));

        if (!state.prefsLoaded && state.catalog.length > 0) {
            state.pinnedKeys = new Set(validKeys);
            savePinned();
        } else {
            [...state.pinnedKeys].forEach((key) => {
                if (!validKeys.has(key)) {
                    state.pinnedKeys.delete(key);
                }
            });
            if (state.prefsLoaded) {
                savePinned();
            }
        }

        if (state.expandedKey && !state.pinnedKeys.has(state.expandedKey)) {
            state.expandedKey = null;
        }
    }

    function findSensorByKey(key) {
        return state.catalog.find((sensor) => sensorKey(sensor.sensor_type, sensor.sensor_id) === key) || null;
    }

    function isLive(key) {
        const seen = state.lastSeenByKey[key];
        return typeof seen === 'number' && Date.now() - seen < LIVE_STALE_MS;
    }

    function formatValue(value) {
        if (typeof value === 'number') {
            return Number.isInteger(value) ? String(value) : value.toFixed(3);
        }
        if (typeof value === 'boolean') {
            return value ? 'ano' : 'ne';
        }
        if (Array.isArray(value)) {
            return `${value.length} položek`;
        }
        if (value && typeof value === 'object') {
            return JSON.stringify(value);
        }
        return String(value);
    }

    function drawLidarPreview(canvas, payload) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#05080d';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const maxRadius = Math.min(canvas.width, canvas.height) * 0.42;

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        for (let radius = maxRadius / 3; radius <= maxRadius; radius += maxRadius / 3) {
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
            ctx.stroke();
        }

        if (!payload || !Array.isArray(payload.ranges)) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '12px Inter, system-ui, sans-serif';
            ctx.fillText('Čekám na sken…', 12, 22);
            return;
        }

        const maxRange = payload.max_range || Math.max(...payload.ranges, 0.1);
        ctx.fillStyle = '#ff9500';
        payload.ranges.forEach((range, index) => {
            if (!range || range <= 0) {
                return;
            }
            const angle = payload.angle_min + index * payload.angle_increment;
            const normalized = Math.min(range / maxRange, 1.0);
            const radius = normalized * maxRadius;
            const x = centerX - Math.sin(angle) * radius;
            const y = centerY - Math.cos(angle) * radius;
            ctx.fillRect(x, y, 2, 2);
        });
    }

    function drawImuPreview(canvas, payload) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#05080d';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const centerX = canvas.width * 0.28;
        const centerY = canvas.height / 2;
        const radius = Math.min(centerX, centerY) - 12;

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.stroke();

        if (!payload) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '12px Inter, system-ui, sans-serif';
            ctx.fillText('Čekám na IMU…', 12, 22);
            return;
        }

        ctx.strokeStyle = '#00d4ff';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
            centerX + Math.cos(payload.yaw || 0) * radius,
            centerY - Math.sin(payload.yaw || 0) * radius,
        );
        ctx.stroke();

        ctx.fillStyle = '#e2e8f0';
        ctx.font = '12px Inter, system-ui, sans-serif';
        ctx.fillText(`yaw ${formatValue(payload.yaw || 0)}`, canvas.width * 0.55, centerY);
    }

    function drawGenericPreview(canvas, sensor, payload) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#05080d';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '12px Inter, system-ui, sans-serif';

        if (!payload) {
            ctx.fillText('Čekám na data…', 12, 22);
            return;
        }

        if (sensor.sensor_type === 'bumper') {
            ctx.fillStyle = payload.contact ? '#ef4444' : '#22c55e';
            ctx.beginPath();
            ctx.roundRect(16, canvas.height / 2 - 24, canvas.width - 32, 48, 10);
            ctx.fill();
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 16px Inter, system-ui, sans-serif';
            ctx.fillText(payload.contact ? 'KONTAKT' : 'BEZ KONTAKTU', 28, canvas.height / 2 + 6);
            return;
        }

        if (sensor.sensor_type === 'cliff') {
            const normalized = Math.max(0, Math.min(1, payload.normalized_range ?? 0));
            ctx.fillStyle = '#1e293b';
            ctx.beginPath();
            ctx.roundRect(16, canvas.height / 2 - 12, canvas.width - 32, 24, 10);
            ctx.fill();
            ctx.fillStyle = '#00d4ff';
            ctx.beginPath();
            ctx.roundRect(16, canvas.height / 2 - 12, (canvas.width - 32) * normalized, 24, 10);
            ctx.fill();
            ctx.fillStyle = '#e2e8f0';
            ctx.fillText(`dosah ${formatValue(payload.range)}`, 16, canvas.height / 2 - 24);
            return;
        }

        if (sensor.sensor_type === 'optical_flow') {
            const originX = canvas.width / 2;
            const originY = canvas.height / 2;
            const scale = 60;
            ctx.strokeStyle = 'rgba(255,255,255,0.12)';
            ctx.beginPath();
            ctx.moveTo(16, originY);
            ctx.lineTo(canvas.width - 16, originY);
            ctx.moveTo(originX, 16);
            ctx.lineTo(originX, canvas.height - 16);
            ctx.stroke();
            ctx.strokeStyle = '#ff9500';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(originX, originY);
            ctx.lineTo(originX + (payload.vx || 0) * scale, originY - (payload.vy || 0) * scale);
            ctx.stroke();
            return;
        }

        ctx.fillText('Náhled pro tento typ není k dispozici.', 12, 22);
    }

    function drawPreview(canvas, sensor, payload) {
        if (!canvas || !sensor) {
            return;
        }
        if (sensor.sensor_type === 'lidar') {
            drawLidarPreview(canvas, payload);
            return;
        }
        if (sensor.sensor_type === 'imu') {
            drawImuPreview(canvas, payload);
            return;
        }
        drawGenericPreview(canvas, sensor, payload);
    }

    function tileMetricEntries(sensor, payload) {
        if (!payload) {
            return [];
        }
        const preferred = TILE_METRIC_KEYS[sensor.sensor_type] || Object.keys(payload).slice(0, 4);
        return preferred
            .filter((key) => Object.prototype.hasOwnProperty.call(payload, key))
            .slice(0, 4)
            .map((key) => [key, payload[key]]);
    }

    function renderCatalog() {
        const container = document.getElementById('sensor-catalog');
        const empty = document.getElementById('sensor-catalog-empty');
        const sensorCount = document.getElementById('sensor-count');
        const pinnedCount = document.getElementById('pinned-count');
        if (!container || !empty || !sensorCount || !pinnedCount) {
            return;
        }

        sensorCount.textContent = String(state.catalog.length);
        pinnedCount.textContent = String(state.pinnedKeys.size);
        container.innerHTML = '';

        if (state.catalog.length === 0) {
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';
        const groups = groupedCatalog();

        Object.entries(groups).forEach(([sensorType, sensors]) => {
            const group = document.createElement('div');
            group.className = 'sensor-group';

            const title = document.createElement('h3');
            title.textContent = sensorTypeDisplayName(sensorType);
            group.appendChild(title);

            const list = document.createElement('div');
            list.className = 'sensor-catalog-list';

            sensors.forEach((sensor) => {
                const key = sensorKey(sensor.sensor_type, sensor.sensor_id);
                const item = document.createElement('label');
                item.className = `sensor-catalog-item${state.pinnedKeys.has(key) ? ' is-pinned' : ''}`;

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = state.pinnedKeys.has(key);
                checkbox.addEventListener('change', () => {
                    if (checkbox.checked) {
                        state.pinnedKeys.add(key);
                    } else {
                        state.pinnedKeys.delete(key);
                        if (state.expandedKey === key) {
                            state.expandedKey = null;
                        }
                    }
                    savePinned();
                    renderAll();
                });

                const meta = document.createElement('div');
                meta.className = 'sensor-catalog-meta';
                meta.innerHTML = `<strong>${sensor.label}</strong><span>${sensor.topic}${
                    sensor.frame_id ? ` · ${sensor.frame_id}` : ''
                }</span>`;

                const dot = document.createElement('span');
                dot.className = `sensor-live-dot${isLive(key) ? ' is-live' : ''}`;
                dot.title = isLive(key) ? 'Živá data' : 'Bez recentních dat';

                item.appendChild(checkbox);
                item.appendChild(meta);
                item.appendChild(dot);
                list.appendChild(item);
            });

            group.appendChild(list);
            container.appendChild(group);
        });
    }

    function renderDashboard() {
        const container = document.getElementById('sensor-dashboard');
        const empty = document.getElementById('sensor-dashboard-empty');
        if (!container || !empty) {
            return;
        }

        container.innerHTML = '';
        const pinnedSensors = state.catalog.filter((sensor) =>
            state.pinnedKeys.has(sensorKey(sensor.sensor_type, sensor.sensor_id)),
        );

        if (pinnedSensors.length === 0) {
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';

        pinnedSensors.forEach((sensor) => {
            const key = sensorKey(sensor.sensor_type, sensor.sensor_id);
            const payload = state.latestByKey[key] || null;
            const live = isLive(key);

            const tile = document.createElement('button');
            tile.type = 'button';
            tile.className = `sensor-tile${state.expandedKey === key ? ' is-expanded' : ''}`;
            tile.addEventListener('click', () => {
                state.expandedKey = state.expandedKey === key ? null : key;
                renderAll();
            });

            const head = document.createElement('div');
            head.className = 'sensor-tile-head';
            head.innerHTML = `
                <div>
                    <strong>${sensor.label}</strong>
                    <span>${sensorTypeDisplayName(sensor.sensor_type)}</span>
                </div>
                <span class="sensor-tile-status${live ? ' is-live' : ''}">${live ? 'živé' : 'neaktivní'}</span>
            `;

            const canvas = document.createElement('canvas');
            canvas.width = 320;
            canvas.height = 140;
            drawPreview(canvas, sensor, payload);

            const metrics = document.createElement('div');
            metrics.className = 'sensor-tile-metrics';
            tileMetricEntries(sensor, payload).forEach(([metricKey, value]) => {
                const metric = document.createElement('div');
                metric.className = 'sensor-tile-metric';
                metric.innerHTML = `<span>${metricFieldLabel(metricKey)}</span><strong>${formatValue(value)}</strong>`;
                metrics.appendChild(metric);
            });

            tile.appendChild(head);
            tile.appendChild(canvas);
            if (metrics.childElementCount > 0) {
                tile.appendChild(metrics);
            }
            container.appendChild(tile);
        });
    }

    function renderMetrics(sensor, payload) {
        const metrics = document.getElementById('sensor-metrics');
        if (!metrics) {
            return;
        }
        metrics.innerHTML = '';

        if (!sensor || !payload) {
            metrics.innerHTML = '<div class="sensor-metric-empty">Pro tento senzor zatím nejsou data.</div>';
            return;
        }

        Object.entries(payload).forEach(([key, value]) => {
            if (Array.isArray(value) && value.length > 12) {
                return;
            }
            const metric = document.createElement('div');
            metric.className = 'sensor-metric';
            metric.innerHTML = `<span>${metricFieldLabel(key)}</span><strong>${formatValue(value)}</strong>`;
            metrics.appendChild(metric);
        });
    }

    function renderDetail() {
        const panel = document.getElementById('sensor-detail-panel');
        const title = document.getElementById('sensor-detail-title');
        const subtitle = document.getElementById('sensor-detail-subtitle');
        const badge = document.getElementById('sensor-detail-type');
        const rawOutput = document.getElementById('sensor-raw-output');
        const canvas = document.getElementById('sensorDetailCanvas');
        if (!panel || !title || !subtitle || !badge || !rawOutput || !canvas) {
            return;
        }

        const sensor = state.expandedKey ? findSensorByKey(state.expandedKey) : null;
        if (!sensor) {
            panel.hidden = true;
            return;
        }

        const payload = state.latestByKey[state.expandedKey] || null;
        panel.hidden = false;
        title.textContent = sensor.label;
        subtitle.textContent = `${sensor.topic}${sensor.frame_id ? ` · rám ${sensor.frame_id}` : ''}`;
        badge.textContent = sensorTypeDisplayName(sensor.sensor_type);
        rawOutput.textContent = payload ? JSON.stringify(payload, null, 2) : 'Čekání na první zprávu…';
        renderMetrics(sensor, payload);
        drawPreview(canvas, sensor, payload);
    }

    function renderAll() {
        renderCatalog();
        renderDashboard();
        renderDetail();
    }

    function wirePageControls() {
        const pinAll = document.getElementById('sensor-pin-all');
        const pinNone = document.getElementById('sensor-pin-none');
        const closeDetail = document.getElementById('sensor-detail-close');

        if (pinAll) {
            pinAll.onclick = () => {
                state.pinnedKeys = new Set(state.catalog.map((s) => sensorKey(s.sensor_type, s.sensor_id)));
                savePinned();
                renderAll();
            };
        }

        if (pinNone) {
            pinNone.onclick = () => {
                state.pinnedKeys.clear();
                state.expandedKey = null;
                savePinned();
                renderAll();
            };
        }

        if (closeDetail) {
            closeDetail.onclick = () => {
                state.expandedKey = null;
                renderAll();
            };
        }
    }

    window.initSensorsPage = function initSensorsPage() {
        loadPrefs();
        syncPinnedWithCatalog();
        wirePageControls();
        if (!state.liveTimer) {
            state.liveTimer = window.setInterval(() => {
                if (document.getElementById('sensor-catalog')) {
                    renderCatalog();
                    renderDashboard();
                }
            }, 1000);
        }
        renderAll();
    };

    window.handleSensorCatalog = function handleSensorCatalog(sensors) {
        state.catalog = Array.isArray(sensors) ? sensors : [];
        syncPinnedWithCatalog();
        if (document.getElementById('sensor-catalog')) {
            renderAll();
        }
    };

    window.handleSensorData = function handleSensorData(message) {
        if (!message || !message.sensor_type || !message.sensor_id) {
            return;
        }

        const matchingSensor = state.catalog.find(
            (sensor) => sensor.sensor_type === message.sensor_type && sensor.sensor_id === message.sensor_id,
        );
        if (matchingSensor && message.frame_id) {
            matchingSensor.frame_id = normalizeFrameId(message.frame_id);
        }

        const key = sensorKey(message.sensor_type, message.sensor_id);
        state.latestByKey[key] = message.payload;
        state.lastSeenByKey[key] = Date.now();

        if (document.getElementById('sensor-dashboard')) {
            renderCatalog();
            renderDashboard();
            if (state.expandedKey === key) {
                renderDetail();
            }
        }
    };
})();
