import { thresholdForTopic } from './blueprint-map.js';

export const BINARY_TYPES = new Set(['bumper', 'cliff']);
export const HISTORY_WINDOW_MS = 30000;

const DEFAULT_CLIFF_NORMALIZED = 0.8;

const STATE_LABELS = {
    bumper: { on: 'KONTAKT', off: 'volno' },
    cliff: { on: 'SCHOD', off: 'podlaha' },
};

/** true = collision (bumper contact) / cliff detected (range above threshold). */
export function binaryState(sensor, payload) {
    if (!sensor || !payload) {
        return null;
    }
    if (sensor.sensor_type === 'bumper') {
        return Boolean(payload.contact);
    }
    if (sensor.sensor_type === 'cliff') {
        const threshold = thresholdForTopic(sensor.topic);
        if (typeof threshold === 'number' && threshold > 0) {
            return payload.range > threshold;
        }
        return (payload.normalized_range ?? 0) > DEFAULT_CLIFF_NORMALIZED;
    }
    return null;
}

export function stateLabel(sensorType, state) {
    const labels = STATE_LABELS[sensorType] || { on: 'ANO', off: 'ne' };
    if (state === null || state === undefined) {
        return '—';
    }
    return state ? labels.on : labels.off;
}
