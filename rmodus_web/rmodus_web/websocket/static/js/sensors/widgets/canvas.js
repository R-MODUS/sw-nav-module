const MIN_DRAW_W = 24;
const MIN_DRAW_H = 8;

export const COLORS = {
    bg: '#05080d',
    grid: 'rgba(255, 255, 255, 0.08)',
    axis: 'rgba(255, 255, 255, 0.16)',
    text: '#e2e8f0',
    muted: '#94a3b8',
    primary: '#00d4ff',
    accent: '#ff9500',
    danger: '#ef4444',
    success: '#22c55e',
};

/**
 * Canvas that tracks its host size (DPR aware). draw(ctx, w, h) runs on resize and on redraw().
 */
export function createCanvasView(host, draw) {
    const canvas = document.createElement('canvas');
    canvas.className = 'sx-canvas';
    host.appendChild(canvas);
    const ctx = canvas.getContext('2d');
    let width = 0;
    let height = 0;

    function redraw() {
        if (width < MIN_DRAW_W || height < MIN_DRAW_H || !canvas.isConnected) {
            return;
        }
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = COLORS.bg;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        const dpr = canvas.width / width;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        draw(ctx, width, height);
    }

    const observer = new ResizeObserver(() => {
        const rect = host.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = Math.max(1, Math.floor(rect.width));
        height = Math.max(1, Math.floor(rect.height));
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        redraw();
    });
    observer.observe(host);

    return {
        redraw,
        destroy() {
            observer.disconnect();
            canvas.remove();
        },
    };
}

export function drawWaiting(ctx, w, h, text = 'Čekám na data…') {
    ctx.fillStyle = COLORS.muted;
    ctx.font = '11px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, w / 2, h / 2);
    ctx.textAlign = 'start';
    ctx.textBaseline = 'alphabetic';
}

export function drawArrow(ctx, x0, y0, x1, y1, color, width = 2.5) {
    const len = Math.hypot(x1 - x0, y1 - y0);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    if (len < 4) {
        return;
    }
    const head = Math.min(10, len * 0.4);
    const angle = Math.atan2(y1 - y0, x1 - x0);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x1 - head * Math.cos(angle - 0.45), y1 - head * Math.sin(angle - 0.45));
    ctx.lineTo(x1 - head * Math.cos(angle + 0.45), y1 - head * Math.sin(angle + 0.45));
    ctx.closePath();
    ctx.fill();
}

/** Small robot marker, forward = up. */
export function drawRobotMarker(ctx, cx, cy, size, color = COLORS.primary) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(cx, cy - size);
    ctx.lineTo(cx + size * 0.7, cy + size * 0.7);
    ctx.lineTo(cx, cy + size * 0.35);
    ctx.lineTo(cx - size * 0.7, cy + size * 0.7);
    ctx.closePath();
    ctx.fill();
}
