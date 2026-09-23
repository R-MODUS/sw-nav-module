import { COLORS, createCanvasView, drawArrow, drawRobotMarker, drawWaiting } from './canvas.js';

const MIN_FULL_SCALE = 0.2;
const PEAK_DECAY = 0.98;

/** Velocity arrow in the robot frame (forward = up) + yaw-rate arc; odom adds a pose readout. */
export function createVectorWidget(host, { showPose = false } = {}) {
    let payload = null;
    let peak = MIN_FULL_SCALE;

    const view = createCanvasView(host, (ctx, w, h) => {
        const cx = w / 2;
        const cy = showPose ? h / 2 - 6 : h / 2;
        const radius = Math.max(4, Math.min(w, h - (showPose ? 18 : 0)) * 0.42);

        ctx.strokeStyle = COLORS.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.moveTo(cx - radius, cy);
        ctx.lineTo(cx + radius, cy);
        ctx.moveTo(cx, cy - radius);
        ctx.lineTo(cx, cy + radius);
        ctx.stroke();

        if (!payload) {
            drawWaiting(ctx, w, h);
            return;
        }

        const vx = payload.vx || 0;
        const vy = payload.vy || 0;
        const wz = payload.wz || 0;
        const scale = radius / peak;

        if (Math.abs(wz) > 1e-3) {
            const sweep = Math.max(-Math.PI * 1.5, Math.min(Math.PI * 1.5, wz));
            ctx.strokeStyle = COLORS.primary;
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(cx, cy, radius + 4, -Math.PI / 2, -Math.PI / 2 - sweep, sweep > 0);
            ctx.stroke();
        }

        drawRobotMarker(ctx, cx, cy, Math.max(4, radius * 0.12), 'rgba(0, 212, 255, 0.45)');
        drawArrow(ctx, cx, cy, cx - vy * scale, cy - vx * scale, COLORS.accent, 3);

        ctx.fillStyle = COLORS.text;
        ctx.font = '11px Inter, system-ui, sans-serif';
        ctx.fillText(`${Math.hypot(vx, vy).toFixed(2)} m/s`, 6, 14);
        ctx.fillStyle = COLORS.muted;
        ctx.textAlign = 'right';
        ctx.fillText(`ω ${wz.toFixed(2)}`, w - 6, 14);
        ctx.textAlign = 'start';

        if (showPose) {
            const yaw = Math.atan2(Math.sin(payload.yaw || 0), Math.cos(payload.yaw || 0));
            const yawDeg = (yaw * 180) / Math.PI;
            ctx.fillStyle = COLORS.muted;
            ctx.textAlign = 'center';
            ctx.fillText(
                `x ${(payload.x || 0).toFixed(2)}  y ${(payload.y || 0).toFixed(2)}  θ ${yawDeg.toFixed(0)}°`,
                w / 2,
                h - 6,
            );
            ctx.textAlign = 'start';
        }
    });

    return {
        update(entries) {
            payload = entries[0]?.payload || null;
            if (payload) {
                const speed = Math.hypot(payload.vx || 0, payload.vy || 0);
                peak = Math.max(MIN_FULL_SCALE, speed * 1.15, peak * PEAK_DECAY);
            }
            view.redraw();
        },
        destroy() {
            view.destroy();
        },
    };
}
