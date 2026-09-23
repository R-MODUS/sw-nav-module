export const CATEGORIES = [
    { id: 'collision', label: 'Kolize' },
    { id: 'kinematics', label: 'Kinematika' },
    { id: 'environment', label: 'Prostředí' },
    { id: 'other', label: 'Ostatní' },
];

export const SENSOR_TYPES = {
    bumper: { label: 'Nárazník', category: 'collision' },
    cliff: { label: 'Detekce schodu', category: 'collision' },
    imu: { label: 'IMU', category: 'kinematics' },
    odom: { label: 'Odometrie', category: 'kinematics' },
    optical_flow: { label: 'Optický tok', category: 'kinematics' },
    lidar: { label: 'LiDAR', category: 'environment' },
};

const FIELD_LABELS = {
    angle_min: 'Úhel min.',
    angle_increment: 'Krok úhlu',
    max_range: 'Max. dosah',
    min_range: 'Min. dosah',
    ranges: 'Vzdálenosti',
    orientation_x: 'Orientace x',
    orientation_y: 'Orientace y',
    orientation_z: 'Orientace z',
    orientation_w: 'Orientace w',
    linear_acceleration_x: 'Zrychlení x',
    linear_acceleration_y: 'Zrychlení y',
    linear_acceleration_z: 'Zrychlení z',
    angular_velocity_x: 'Úhlová rychlost x',
    angular_velocity_y: 'Úhlová rychlost y',
    angular_velocity_z: 'Úhlová rychlost z',
    yaw: 'Natočení (yaw)',
    contact: 'Kontakt',
    width: 'Šířka',
    range: 'Dosah',
    normalized_range: 'Normalizovaný dosah',
    field_of_view: 'Zorné pole',
    x: 'Poloha x',
    y: 'Poloha y',
    vx: 'Rychlost x',
    vy: 'Rychlost y',
    vz: 'Rychlost z',
    wx: 'Úhlová rychlost x',
    wy: 'Úhlová rychlost y',
    wz: 'Úhlová rychlost z',
    child_frame_id: 'Child frame',
};

export const STATUS_LABELS = {
    live: 'Aktivní',
    delayed: 'Zpožděno',
    offline: 'Bez dat',
};

export function sensorKey(sensorType, sensorId) {
    return `${sensorType}:${sensorId}`;
}

export function typeLabel(sensorType) {
    if (!sensorType) {
        return '—';
    }
    return SENSOR_TYPES[sensorType]?.label || String(sensorType).replace(/_/g, ' ');
}

export function typeCategory(sensorType) {
    return SENSOR_TYPES[sensorType]?.category || 'other';
}

export function fieldLabel(key) {
    return FIELD_LABELS[key] || key;
}

export function formatValue(value) {
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
    if (value === null || value === undefined || value === '') {
        return '—';
    }
    return String(value);
}

export function formatAge(ms) {
    if (ms == null) {
        return 'nikdy';
    }
    if (ms < 1000) {
        return 'právě teď';
    }
    if (ms < 60000) {
        return `před ${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
    }
    return `před ${Math.round(ms / 60000)} min`;
}

export const STATUS_RANK = { live: 0, delayed: 1, offline: 2 };

export function worstStatus(statuses) {
    let worst = 'live';
    let seen = false;
    statuses.forEach((status) => {
        seen = true;
        if (STATUS_RANK[status] > STATUS_RANK[worst]) {
            worst = status;
        }
    });
    return seen ? worst : 'offline';
}

export function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) {
        node.className = className;
    }
    if (text !== undefined) {
        node.textContent = text;
    }
    return node;
}
