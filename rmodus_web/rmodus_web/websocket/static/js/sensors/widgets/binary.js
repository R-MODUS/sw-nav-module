import { binaryState, HISTORY_WINDOW_MS, stateLabel } from '../binary.js';
import { el, formatValue } from '../meta.js';
import { COLORS, createCanvasView } from './canvas.js';

const SCROLL_FPS = 10;
const GRID_STEP_MS = 10000;

/**
 * Binary state. Tile mode: state only (compact 1x1). Detail mode adds a right-to-left
 * sparkline of the last HISTORY_WINDOW_MS (newest at the right edge).
 */
export function createBinaryWidget(host, { mode }) {
    const detail = mode === 'detail';
    const root = el('div', `sx-binary${detail ? ' is-detail' : ''}`);
    const row = el('div', 'sx-binary-row');
    const chip = el('span', 'sx-binary-chip', '—');
    const value = el('span', 'sx-binary-value');
    row.append(chip, value);
    root.appendChild(row);
    host.appendChild(root);

    let entry = null;
    let scrollTimer = null;
    let view = null;

    if (detail) {
        const sparkHost = el('div', 'sx-spark');
        root.appendChild(sparkHost);
        view = createCanvasView(sparkHost, drawSparkline);
    }

    function drawSparkline(ctx, w, h) {
        const now = Date.now();
        const pxPerMs = w / HISTORY_WINDOW_MS;
        const xOf = (t) => w - (now - t) * pxPerMs;

        ctx.strokeStyle = COLORS.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let t = GRID_STEP_MS; t < HISTORY_WINDOW_MS; t += GRID_STEP_MS) {
            const x = Math.round(w - t * pxPerMs) + 0.5;
            ctx.moveTo(x, 0);
            ctx.lineTo(x, h);
        }
        ctx.moveTo(0, h - 0.5);
        ctx.lineTo(w, h - 0.5);
        ctx.stroke();

        const history = entry?.history || [];
        const cutoff = now - HISTORY_WINDOW_MS;
        ctx.fillStyle = COLORS.danger;
        let anyTrue = false;
        for (let i = 0; i < history.length; i += 1) {
            const [t, state] = history[i];
            if (t < cutoff || !state) {
                continue;
            }
            anyTrue = true;
            const next = history[i + 1];
            const x0 = xOf(t);
            const x1 = next ? xOf(next[0]) : w;
            ctx.fillRect(Math.floor(x0), 1, Math.max(1, Math.ceil(x1 - x0)), h - 2);
        }

        ctx.fillStyle = COLORS.muted;
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.fillText(`−${HISTORY_WINDOW_MS / 1000} s`, 4, 11);
        ctx.textAlign = 'right';
        ctx.fillText('teď', w - 4, 11);
        ctx.textAlign = 'start';
        setScrolling(anyTrue);
    }

    function setScrolling(on) {
        if (on && !scrollTimer) {
            scrollTimer = window.setInterval(() => view?.redraw(), 1000 / SCROLL_FPS);
        } else if (!on && scrollTimer) {
            window.clearInterval(scrollTimer);
            scrollTimer = null;
        }
    }

    return {
        update(entries) {
            entry = entries[0] || null;
            const sensor = entry?.sensor;
            const state = binaryState(sensor, entry?.payload);
            chip.textContent = stateLabel(sensor?.sensor_type, state);
            chip.dataset.state = state === null ? 'none' : String(state);
            root.classList.toggle('is-offline', entry?.status === 'offline');
            value.textContent =
                sensor?.sensor_type === 'cliff' && entry?.payload ? `${formatValue(entry.payload.range)} m` : '';
            view?.redraw();
        },
        destroy() {
            setScrolling(false);
            view?.destroy();
            root.remove();
        },
    };
}
