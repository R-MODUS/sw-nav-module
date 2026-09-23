import { BINARY_TYPES } from './binary.js';
import { sensorKey, typeLabel } from './meta.js';

/** Virtual catalog items (not ROS sensors). Pinned like sensors, under their own key. */
export const BLUEPRINT_KEY = 'widget:blueprint';
export const WIDGET_ITEMS = [
    {
        key: BLUEPRINT_KEY,
        label: 'Robot Blueprint',
        hint: 'Obrys robota se všemi nárazníky a cliff senzory',
    },
];

const KIND_BY_TYPE = {
    bumper: 'binary',
    cliff: 'binary',
    lidar: 'lidar',
    imu: 'imu',
    optical_flow: 'flow',
    odom: 'odom',
};

/** Default grid size (12-column grid; one cell ≈ square). */
export const TILE_SIZES = {
    blueprint: { w: 4, h: 2 },
    binary: { w: 1, h: 1 },
    lidar: { w: 4, h: 2 },
    imu: { w: 2, h: 2 },
    odom: { w: 4, h: 1 },
    flow: { w: 2, h: 1 },
    generic: { w: 2, h: 1 },
};

export function binarySensorKeys(catalog) {
    return catalog
        .filter((sensor) => BINARY_TYPES.has(sensor.sensor_type))
        .map((sensor) => sensorKey(sensor.sensor_type, sensor.sensor_id));
}

export function sensorTile(sensor) {
    const key = sensorKey(sensor.sensor_type, sensor.sensor_id);
    return {
        id: `sensor:${key}`,
        kind: KIND_BY_TYPE[sensor.sensor_type] || 'generic',
        keys: [key],
        title: sensor.label || sensor.sensor_id,
        subtitle: typeLabel(sensor.sensor_type),
    };
}

export function blueprintTile(catalog) {
    const keys = binarySensorKeys(catalog);
    const n = keys.length;
    return {
        id: 'blueprint',
        kind: 'blueprint',
        keys,
        title: 'Robot Blueprint',
        subtitle: `${n} ${n === 1 ? 'senzor' : n > 1 && n < 5 ? 'senzory' : 'senzorů'}`,
    };
}

/**
 * Pinned items → tiles. Binary sensors get their own 1x1 tile; the Blueprint
 * (if pinned) independently aggregates every bumper / cliff sensor in the catalog.
 */
export function buildTiles(catalog, pinnedKeys) {
    const tiles = [];
    if (pinnedKeys.has(BLUEPRINT_KEY)) {
        tiles.push(blueprintTile(catalog));
    }
    catalog.forEach((sensor) => {
        if (pinnedKeys.has(sensorKey(sensor.sensor_type, sensor.sensor_id))) {
            tiles.push(sensorTile(sensor));
        }
    });
    return tiles;
}
