import { el } from '../meta.js';

const CAMERA = 'rotateX(-24deg) rotateY(-32deg)';
const FACES = ['front', 'back', 'left', 'right', 'top', 'bottom'];

function normalizedQuaternion(p) {
    const x = p.orientation_x || 0;
    const y = p.orientation_y || 0;
    const z = p.orientation_z || 0;
    const w = p.orientation_w || 0;
    const n = Math.hypot(x, y, z, w);
    return n > 1e-6 ? { x: x / n, y: y / n, z: z / n, w: w / n } : { x: 0, y: 0, z: 0, w: 1 };
}

export function eulerFromPayload(p) {
    const { x, y, z, w } = normalizedQuaternion(p);
    const roll = Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
    const pitch = Math.asin(Math.max(-1, Math.min(1, 2 * (w * y - z * x))));
    const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
    return { roll, pitch, yaw };
}

/**
 * ROS (x fwd, y left, z up) rotation → CSS (x right, y down, z to viewer) matrix3d.
 * CSS basis in ROS coords: x_css = -y, y_css = -z, z_css = -x; R_css = P·R·Pᵀ.
 */
function cssMatrix(p) {
    const { x, y, z, w } = normalizedQuaternion(p);
    const r = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ];
    const rosIndex = [1, 2, 0];
    const m = [0, 1, 2].map((i) => [0, 1, 2].map((j) => r[rosIndex[i]][rosIndex[j]]));
    return `matrix3d(${m[0][0]},${m[1][0]},${m[2][0]},0,${m[0][1]},${m[1][1]},${m[2][1]},0,${m[0][2]},${m[1][2]},${m[2][2]},0,0,0,0,1)`;
}

function deg(rad) {
    return `${((rad * 180) / Math.PI).toFixed(1)}°`;
}

export function createImuWidget(host, { mode }) {
    const root = el('div', `sx-imu${mode === 'detail' ? ' is-detail' : ''}`);
    const stage = el('div', 'sx-imu-stage');
    const camera = el('div', 'sx-imu-camera');
    const body = el('div', 'sx-imu-body');
    FACES.forEach((face) => {
        const node = el('div', `sx-imu-face is-${face}`);
        if (face === 'top') {
            node.textContent = '▲';
        }
        body.appendChild(node);
    });
    camera.style.transform = CAMERA;
    camera.appendChild(body);
    stage.appendChild(camera);

    const readouts = el('dl', 'sx-readouts');
    const fields = {};
    [
        ['roll', 'R'],
        ['pitch', 'P'],
        ['yaw', 'Y'],
        ['wz', 'ωz'],
    ].forEach(([key, label]) => {
        readouts.appendChild(el('dt', null, label));
        fields[key] = readouts.appendChild(el('dd', null, '—'));
    });

    root.append(stage, readouts);
    host.appendChild(root);

    const observer = new ResizeObserver(() => {
        const size = Math.max(24, Math.min(stage.clientWidth, stage.clientHeight) * 0.42);
        body.style.setProperty('--w', `${size}px`);
        body.style.setProperty('--d', `${size * 1.3}px`);
        body.style.setProperty('--h', `${size * 0.42}px`);
        stage.style.perspective = `${size * 6}px`;
    });
    observer.observe(stage);

    return {
        update(entries) {
            const p = entries[0]?.payload;
            root.classList.toggle('is-waiting', !p);
            if (!p) {
                return;
            }
            body.style.transform = cssMatrix(p);
            const { roll, pitch, yaw } = eulerFromPayload(p);
            fields.roll.textContent = deg(roll);
            fields.pitch.textContent = deg(pitch);
            fields.yaw.textContent = deg(yaw);
            fields.wz.textContent = `${(p.angular_velocity_z || 0).toFixed(2)}`;
        },
        destroy() {
            observer.disconnect();
            root.remove();
        },
    };
}
