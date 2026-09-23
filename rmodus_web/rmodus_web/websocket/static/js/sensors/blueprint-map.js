/**
 * Topic → Blueprint SVG segment mapping.
 *
 * Sources (first match wins per field):
 *   1. web.ui.blueprint.segments  { svg_id: { topic, x?, y?, yaw?, size?, threshold? } }
 *   2. profile mounts             bumpers / cliff_sensors items (name, mount_offset, mount_rpy, size)
 *   3. name keywords              front / rear / left / right / fl / fr / rl / rr
 * Coordinates are base_link (x forward, y left) in metres, yaw in radians.
 */

export const DEFAULT_FOOTPRINT = [0.5, 0.5];
const DEFAULT_BUMPER_THICKNESS = 0.035;
const DEFAULT_BUMPER_SPAN_RATIO = 0.6;

/** Name keyword → [x, y] in half-footprint units + yaw of the segment. */
const NAME_POSITIONS = [
    [/front[_-]?left|^fl$/, [1, 1, 0]],
    [/front[_-]?right|^fr$/, [1, -1, 0]],
    [/rear[_-]?left|back[_-]?left|^rl$|^bl$/, [-1, 1, Math.PI]],
    [/rear[_-]?right|back[_-]?right|^rr$|^br$/, [-1, -1, Math.PI]],
    [/front|^f$/, [1, 0, 0]],
    [/rear|back|^b$/, [-1, 0, Math.PI]],
    [/left|^l$/, [0, 1, Math.PI / 2]],
    [/right|^r$/, [0, -1, -Math.PI / 2]],
];

function layout() {
    const cfg = window.__RMODUS_UI_CONFIG__;
    return (cfg && cfg.sensor_layout) || {};
}

export function footprint() {
    const fp = layout().footprint;
    return Array.isArray(fp) && fp.length >= 2 ? fp : DEFAULT_FOOTPRINT;
}

function configuredSegment(topic) {
    const segments = layout().segments || {};
    for (const [id, spec] of Object.entries(segments)) {
        if (spec && spec.topic === topic) {
            return { id, ...spec };
        }
    }
    return null;
}

function mountFor(topic) {
    return (layout().mounts || {})[topic] || null;
}

export function thresholdForTopic(topic) {
    const configured = configuredSegment(topic);
    if (typeof configured?.threshold === 'number') {
        return configured.threshold;
    }
    const mount = mountFor(topic);
    return typeof mount?.threshold === 'number' ? mount.threshold : null;
}

function poseFromNames(names, [length, width]) {
    const whole = names.filter(Boolean).map((text) => String(text).toLowerCase());
    const candidates = [...whole, ...whole.flatMap((text) => text.split(/[\s/·_-]+/)).filter(Boolean)];
    for (const [pattern, [fx, fy, yaw]] of NAME_POSITIONS) {
        if (candidates.some((token) => pattern.test(token))) {
            return { x: (fx * length) / 2, y: (fy * width) / 2, yaw };
        }
    }
    return null;
}

function sanitizeId(text) {
    return String(text || '').trim().replace(/[^A-Za-z0-9_-]+/g, '_') || 'segment';
}

/**
 * sensor (catalog entry) → { id, name, kind, pose | null, size, threshold }.
 * `id` is the SVG segment id (data-segment); pose null = not drawable, shown as a chip.
 */
export function resolveSegment(sensor) {
    const configured = configuredSegment(sensor.topic);
    const mount = mountFor(sensor.topic);
    const fp = footprint();
    const id = sanitizeId(configured?.id || mount?.name || sensor.label || sensor.sensor_id);
    const name = configured?.id || mount?.name || sensor.label || sensor.sensor_id;

    let pose = null;
    if (typeof configured?.x === 'number' && typeof configured?.y === 'number') {
        pose = { x: configured.x, y: configured.y, yaw: configured.yaw || 0 };
    } else if (typeof mount?.x === 'number' && typeof mount?.y === 'number') {
        pose = { x: mount.x, y: mount.y, yaw: mount.yaw || 0 };
    } else {
        pose = poseFromNames([configured?.id, mount?.name, sensor.label, sensor.topic.split('/').pop()], fp);
    }

    const size =
        configured?.size ||
        mount?.size ||
        (sensor.sensor_type === 'bumper' ? [DEFAULT_BUMPER_THICKNESS, fp[1] * DEFAULT_BUMPER_SPAN_RATIO] : null);

    return {
        id,
        name,
        kind: sensor.sensor_type,
        pose,
        size,
        threshold: thresholdForTopic(sensor.topic),
    };
}
