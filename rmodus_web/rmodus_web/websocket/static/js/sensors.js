(() => {
    const SENSOR_TYPE_LABELS = {
        lidar: 'LiDAR',
        imu: 'IMU',
        bumper: 'Nárazník',
        cliff: 'Propast',
        optical_flow: 'Optický tok',
    };

    /** Popisky běžných polí ROS zpráv v metrikách (neznámé klíče zůstanou jak jsou). */
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
        normalized_range: 'Normalizovaný dosah',
        vx: 'Rychlost x',
        vy: 'Rychlost y',
    };

    function sensorTypeDisplayName(sensorType) {
        if (!sensorType) {
            return '—';
        }
        return SENSOR_TYPE_LABELS[sensorType] || String(sensorType).replace(/_/g, ' ');
    }

    function metricFieldLabel(key) {
        return METRIC_FIELD_LABELS[key] || key;
    }

    const state = {
        catalog: [],
        frames: [],
        rootFrame: 'base_link',
        tfStale: true,
        latestByKey: {},
        selectedKey: null,
        robotView: null,
    };

    function sensorKey(sensorType, sensorId) {
        return `${sensorType}:${sensorId}`;
    }

    function normalizeFrameId(frameId) {
        if (!frameId) {
            return null;
        }
        return String(frameId).replace(/^\/+/, '');
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

    function ensureSelection() {
        if (state.selectedKey && state.catalog.some((sensor) => sensorKey(sensor.sensor_type, sensor.sensor_id) === state.selectedKey)) {
            return;
        }

        state.selectedKey = null;
        if (state.selectedKey || state.catalog.length === 0) {
            return;
        }
        const firstSensor = state.catalog[0];
        state.selectedKey = sensorKey(firstSensor.sensor_type, firstSensor.sensor_id);
    }

    function currentSensor() {
        ensureSelection();
        return state.catalog.find((sensor) => sensorKey(sensor.sensor_type, sensor.sensor_id) === state.selectedKey) || null;
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

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        for (let radius = 40; radius <= 120; radius += 40) {
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
            ctx.stroke();
        }

        const axisLen = Math.max(12, Math.min(20, Math.min(canvas.width, canvas.height) * 0.07));
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#ef4444';
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(centerX, centerY - axisLen);
        ctx.stroke();
        ctx.fillStyle = '#ef4444';
        ctx.font = '12px Inter, system-ui, sans-serif';
        ctx.fillText('X', centerX + 6, centerY - axisLen - 6);

        ctx.strokeStyle = '#22c55e';
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(centerX - axisLen, centerY);
        ctx.stroke();
        ctx.fillStyle = '#22c55e';
        ctx.fillText('Y', centerX - axisLen - 14, centerY - 6);

        if (!payload || !Array.isArray(payload.ranges)) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '14px Inter, system-ui, sans-serif';
            ctx.fillText('LiDAR data zatím nepřišla.', 20, 30);
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
            const radius = normalized * (Math.min(canvas.width, canvas.height) * 0.42);
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

        ctx.fillStyle = '#94a3b8';
        ctx.font = '14px Inter, system-ui, sans-serif';
        if (!payload) {
            ctx.fillText('Údaje IMU zatím nepřišly.', 20, 30);
            return;
        }

        const centerX = 120;
        const centerY = canvas.height / 2;
        const radius = 70;
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.stroke();

        ctx.strokeStyle = '#00d4ff';
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
            centerX + Math.cos(payload.yaw || 0) * radius,
            centerY - Math.sin(payload.yaw || 0) * radius,
        );
        ctx.stroke();

        const bars = [
            ['Úhlová z', payload.angular_velocity_z || 0, '#ff9500'],
            ['Zrychlení x', payload.linear_acceleration_x || 0, '#22c55e'],
            ['Zrychlení y', payload.linear_acceleration_y || 0, '#38bdf8'],
        ];

        bars.forEach(([label, value, color], index) => {
            const x = 250;
            const y = 70 + index * 64;
            const width = Math.min(220, Math.abs(value) * 60);
            ctx.fillStyle = '#1e293b';
            ctx.beginPath();
            ctx.roundRect(x, y, 240, 26, 10);
            ctx.fill();
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.roundRect(x, y, width, 26, 10);
            ctx.fill();
            ctx.fillStyle = '#e2e8f0';
            ctx.fillText(`${label}: ${formatValue(value)}`, x, y - 10);
        });
    }

    function renderMetrics(sensor, payload) {
        const metrics = document.getElementById('sensor-metrics');
        if (!metrics) {
            return;
        }
        metrics.innerHTML = '';

        if (!sensor || !payload) {
            metrics.innerHTML = '<div class="sensor-metric-empty">Pro vybraný senzor zatím nejsou k dispozici žádná data.</div>';
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

    function renderSensorDetail() {
        const title = document.getElementById('sensor-detail-title');
        const subtitle = document.getElementById('sensor-detail-subtitle');
        const badge = document.getElementById('sensor-detail-type');
        const rawOutput = document.getElementById('sensor-raw-output');
        const canvas = document.getElementById('sensorDetailCanvas');
        const sensor = currentSensor();

        if (!title || !subtitle || !badge || !rawOutput || !canvas) {
            return;
        }

        if (!sensor) {
            title.textContent = 'Výstup senzoru';
            subtitle.textContent = 'Vyberte senzor ze seznamu výše.';
            badge.textContent = '—';
            rawOutput.textContent = 'Není vybrán žádný senzor.';
            renderMetrics(null, null);
            drawLidarPreview(canvas, null);
            return;
        }

        const key = sensorKey(sensor.sensor_type, sensor.sensor_id);
        const payload = state.latestByKey[key] || null;

        title.textContent = sensor.label;
        subtitle.textContent = `${sensor.topic}${sensor.frame_id ? ` · rám ${sensor.frame_id}` : ''}`;
        badge.textContent = sensorTypeDisplayName(sensor.sensor_type);
        rawOutput.textContent = payload ? JSON.stringify(payload, null, 2) : 'Čekání na první zprávu…';
        renderMetrics(sensor, payload);

        if (sensor.sensor_type === 'lidar') {
            drawLidarPreview(canvas, payload);
            return;
        }

        if (sensor.sensor_type === 'imu') {
            drawImuPreview(canvas, payload);
            return;
        }

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#05080d';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '14px Inter, system-ui, sans-serif';
        ctx.fillText('Pro tento typ senzoru není definovaný grafický náhled.', 20, 30);
        if (payload && sensor.sensor_type === 'bumper') {
            ctx.fillStyle = payload.contact ? '#ef4444' : '#22c55e';
            ctx.beginPath();
            ctx.roundRect(20, 70, canvas.width - 40, 60, 12);
            ctx.fill();
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 18px Inter, system-ui, sans-serif';
            ctx.fillText(payload.contact ? 'KONTAKT' : 'BEZ KONTAKTU', 40, 108);
        }
        if (payload && sensor.sensor_type === 'cliff') {
            const normalized = Math.max(0, Math.min(1, payload.normalized_range ?? 0));
            ctx.fillStyle = '#1e293b';
            ctx.beginPath();
            ctx.roundRect(20, 80, canvas.width - 40, 32, 12);
            ctx.fill();
            ctx.fillStyle = '#00d4ff';
            ctx.beginPath();
            ctx.roundRect(20, 80, (canvas.width - 40) * normalized, 32, 12);
            ctx.fill();
        }
        if (payload && sensor.sensor_type === 'optical_flow') {
            const originX = canvas.width / 2;
            const originY = canvas.height / 2;
            const scale = 80;
            ctx.strokeStyle = '#ff9500';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(originX, originY);
            ctx.lineTo(originX + (payload.vx || 0) * scale, originY - (payload.vy || 0) * scale);
            ctx.stroke();
        }
    }

    function renderSelector() {
        const container = document.getElementById('sensor-selector');
        const empty = document.getElementById('sensor-selection-empty');
        const sensorCount = document.getElementById('sensor-count');
        if (!container || !empty || !sensorCount) {
            return;
        }

        sensorCount.textContent = String(state.catalog.length);
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

            const buttons = document.createElement('div');
            buttons.className = 'sensor-group-buttons';
            sensors.forEach((sensor) => {
                const button = document.createElement('button');
                button.className = 'sensor-select-button';
                const key = sensorKey(sensor.sensor_type, sensor.sensor_id);
                if (key === state.selectedKey) {
                    button.classList.add('active');
                }
                button.textContent = sensor.label;
                button.addEventListener('click', () => {
                    state.selectedKey = key;
                    if (state.robotView) {
                        state.robotView.setSelectedFrame(normalizeFrameId(sensor.frame_id));
                    }
                    renderSelector();
                    renderSensorDetail();
                });
                buttons.appendChild(button);
            });
            group.appendChild(buttons);
            container.appendChild(group);
        });
    }

    function renderTfState() {
        const frameCount = document.getElementById('tf-frame-count');
        const tfStatus = document.getElementById('tf-status');
        const rootBadge = document.getElementById('tf-root-frame');
        if (frameCount) {
            frameCount.textContent = String(state.frames.length);
        }
        if (tfStatus) {
            if (state.tfStale) {
                tfStatus.textContent = 'TF stream je neaktivní. Probíhá automatické obnovení…';
            } else {
                tfStatus.textContent =
                    state.frames.length > 0 ? 'Živý přehled TF je k dispozici.' : 'Čekání na data TF…';
            }
        }
        if (rootBadge) {
            rootBadge.textContent = state.rootFrame;
        }
    }

    function renderAll() {
        renderTfState();
        renderSelector();
        renderSensorDetail();
    }

    window.initSensorsPage = function initSensorsPage() {
        const canvas = document.getElementById('robotTfCanvas');
        const showLabelsInput = document.getElementById('tf-show-labels');
        const zoomInput = document.getElementById('tf-zoom');
        const zoomValue = document.getElementById('tf-zoom-value');

        if (canvas && typeof window.createRobotView === 'function') {
            state.robotView = window.createRobotView(canvas);
            state.robotView.setFrames(state.frames, state.rootFrame);
            const sensor = currentSensor();
            state.robotView.setSelectedFrame(sensor ? normalizeFrameId(sensor.frame_id) : null);

            if (showLabelsInput) {
                state.robotView.setShowLabels(showLabelsInput.checked);
                showLabelsInput.onchange = () => {
                    state.robotView.setShowLabels(showLabelsInput.checked);
                };
            }

            if (zoomInput) {
                const zoom = Number.parseFloat(zoomInput.value || '1.0');
                state.robotView.setZoom(zoom);
                    if (zoomValue) {
                        zoomValue.textContent = `${zoom.toFixed(1)}×`;
                    }
                zoomInput.oninput = () => {
                    const currentZoom = Number.parseFloat(zoomInput.value || '1.0');
                    state.robotView.setZoom(currentZoom);
                    if (zoomValue) {
                        zoomValue.textContent = `${currentZoom.toFixed(1)}×`;
                    }
                };
            }
        }
        renderAll();
    };

    window.handleSensorCatalog = function handleSensorCatalog(sensors) {
        state.catalog = Array.isArray(sensors) ? sensors : [];
        ensureSelection();
        renderAll();
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

        state.latestByKey[sensorKey(message.sensor_type, message.sensor_id)] = message.payload;
        const sensor = currentSensor();
        if (state.robotView && sensor) {
            state.robotView.setSelectedFrame(normalizeFrameId(sensor.frame_id));
        }
        renderSensorDetail();
    };

    window.handleSensorsTfFrames = function handleSensorsTfFrames(message) {
        state.frames = Array.isArray(message.frames) ? message.frames : [];
        state.rootFrame = normalizeFrameId(message.root_frame) || 'base_link';
        state.tfStale = state.frames.length === 0;
        if (state.robotView) {
            state.robotView.setFrames(state.frames, state.rootFrame);
            const sensor = currentSensor();
            state.robotView.setSelectedFrame(sensor ? normalizeFrameId(sensor.frame_id) : null);
        }
        renderTfState();
    };

    window.handleTfStatus = function handleTfStatus(message) {
        state.tfStale = Boolean(message && message.stale);
        renderTfState();
    };
})();
