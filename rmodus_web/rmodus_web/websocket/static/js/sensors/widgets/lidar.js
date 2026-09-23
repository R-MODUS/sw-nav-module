import { COLORS, createCanvasView, drawRobotMarker, drawWaiting } from './canvas.js';

const FIT_SMOOTHING = 0.15;

export function createLidarWidget(host) {
    let payload = null;
    let viewRange = 0;

    function targetRange(data) {
        let farthest = 0;
        const ranges = data.ranges;
        for (let i = 0; i < ranges.length; i += 1) {
            if (ranges[i] > farthest) {
                farthest = ranges[i];
            }
        }
        const limit = data.max_range > 0 ? data.max_range : farthest;
        return Math.max(0.5, Math.min(limit, farthest * 1.1));
    }

    const view = createCanvasView(host, (ctx, w, h) => {
        const cx = w / 2;
        const cy = h / 2;
        const radius = Math.max(4, Math.min(w, h) * 0.46);

        ctx.strokeStyle = COLORS.grid;
        ctx.lineWidth = 1;
        for (let i = 1; i <= 3; i += 1) {
            ctx.beginPath();
            ctx.arc(cx, cy, (radius * i) / 3, 0, Math.PI * 2);
            ctx.stroke();
        }
        ctx.beginPath();
        ctx.moveTo(cx, cy - radius);
        ctx.lineTo(cx, cy + radius);
        ctx.moveTo(cx - radius, cy);
        ctx.lineTo(cx + radius, cy);
        ctx.stroke();

        if (!payload || !Array.isArray(payload.ranges)) {
            drawWaiting(ctx, w, h, 'Čekám na sken…');
            return;
        }

        const scale = radius / (viewRange || 1);
        const dot = w > 360 ? 2.5 : 2;
        const { ranges, angle_min: angleMin = 0, angle_increment: step = 0 } = payload;
        ctx.fillStyle = COLORS.accent;
        ctx.beginPath();
        for (let i = 0; i < ranges.length; i += 1) {
            const range = ranges[i];
            if (!range || range <= 0 || range > viewRange) {
                continue;
            }
            const angle = angleMin + i * step;
            const r = range * scale;
            ctx.rect(cx - Math.sin(angle) * r - dot / 2, cy - Math.cos(angle) * r - dot / 2, dot, dot);
        }
        ctx.fill();

        drawRobotMarker(ctx, cx, cy, Math.max(5, radius * 0.06));

        ctx.fillStyle = COLORS.muted;
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.fillText(`${(viewRange / 3).toFixed(1)} m / kruh`, 6, h - 6);
    });

    return {
        update(entries) {
            payload = entries[0]?.payload || null;
            if (payload && Array.isArray(payload.ranges)) {
                const target = targetRange(payload);
                viewRange = viewRange ? viewRange + FIT_SMOOTHING * (target - viewRange) : target;
            }
            view.redraw();
        },
        destroy() {
            view.destroy();
        },
    };
}
