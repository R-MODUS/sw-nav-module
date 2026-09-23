import { createBinaryWidget } from './binary.js';
import { createBlueprintWidget } from './blueprint.js';
import { createGenericWidget } from './generic.js';
import { createImuWidget } from './imu.js';
import { createLidarWidget } from './lidar.js';
import { createVectorWidget } from './vector.js';

const FACTORIES = {
    blueprint: createBlueprintWidget,
    binary: createBinaryWidget,
    lidar: createLidarWidget,
    imu: createImuWidget,
    flow: (host, opts) => createVectorWidget(host, { ...opts, showPose: false }),
    odom: (host, opts) => createVectorWidget(host, { ...opts, showPose: true }),
    generic: createGenericWidget,
};

/**
 * Widget contract: create(host, { mode: 'tile' | 'detail', onSelectKey })
 * → { update(entries), destroy() }; `entries` are store entries of the tile's sensors.
 */
export function createWidget(kind, host, opts) {
    return (FACTORIES[kind] || FACTORIES.generic)(host, opts);
}
