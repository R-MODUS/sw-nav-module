import { binaryState } from '../binary.js';
import { footprint, resolveSegment } from '../blueprint-map.js';
import { el } from '../meta.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const CLIFF_RADIUS = 0.028;
const MIN_BUMPER_THICKNESS = 0.035;
const MARGIN = 0.09;

function svg(tag, attrs = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
}

/** base_link (x fwd, y left) → SVG (x right, y down); forward = up. */
function toSvg(x, y) {
    return [-y, -x];
}

/**
 * Top-down robot outline. Each bumper / cliff sensor is one element with
 * data-segment="<svg id>" (see blueprint-map.js); state comes from the shared store.
 */
export function createBlueprintWidget(host, { mode, onSelectKey }) {
    const root = el('div', `sx-blueprint${mode === 'detail' ? ' is-detail' : ''}`);
    const svgRoot = svg('svg', { class: 'sx-blueprint-svg', preserveAspectRatio: 'xMidYMid meet' });
    const unplacedList = el('div', 'sx-blueprint-unplaced');
    root.append(svgRoot, unplacedList);
    host.appendChild(root);

    let signature = '';
    let parts = new Map();

    function select(event, key) {
        event.stopPropagation();
        onSelectKey?.(key);
    }

    function build(entries) {
        svgRoot.replaceChildren();
        unplacedList.replaceChildren();
        parts = new Map();

        const [length, width] = footprint();
        let minX = -width / 2;
        let maxX = width / 2;
        let minY = -length / 2;
        let maxY = length / 2;
        const extend = (sx, sy, pad) => {
            minX = Math.min(minX, sx - pad);
            maxX = Math.max(maxX, sx + pad);
            minY = Math.min(minY, sy - pad);
            maxY = Math.max(maxY, sy + pad);
        };

        const body = svg('g', { class: 'sx-blueprint-body' });
        body.appendChild(
            svg('rect', { x: -width / 2, y: -length / 2, width, height: length, rx: Math.min(width, length) * 0.12 }),
        );
        const chevron = Math.min(width, length) * 0.14;
        body.appendChild(
            svg('path', {
                class: 'sx-blueprint-heading',
                d: `M ${-chevron} ${chevron * 0.4} L 0 ${-chevron * 0.6} L ${chevron} ${chevron * 0.4}`,
            }),
        );
        svgRoot.appendChild(body);

        const labels = svg('g', { class: 'sx-blueprint-labels' });
        const fontSize = Math.max(length, width) * 0.09;

        entries.forEach((entry) => {
            if (!entry.sensor) {
                return;
            }
            const segment = resolveSegment(entry.sensor);
            if (!segment.pose) {
                const chip = el('button', 'sx-blueprint-chip', segment.name);
                chip.type = 'button';
                chip.dataset.segment = segment.id;
                chip.addEventListener('click', (event) => select(event, entry.key));
                unplacedList.appendChild(chip);
                parts.set(entry.key, chip);
                return;
            }

            const [sx, sy] = toSvg(segment.pose.x, segment.pose.y);
            let node;
            if (segment.kind === 'bumper') {
                const thickness = Math.max(segment.size[0], MIN_BUMPER_THICKNESS);
                const span = segment.size[1];
                node = svg('rect', {
                    x: -span / 2,
                    y: -thickness / 2,
                    width: span,
                    height: thickness,
                    rx: thickness / 2,
                    transform: `translate(${sx} ${sy}) rotate(${(-segment.pose.yaw * 180) / Math.PI})`,
                });
                extend(sx, sy, span / 2);
            } else {
                node = svg('circle', { cx: sx, cy: sy, r: CLIFF_RADIUS });
                extend(sx, sy, CLIFF_RADIUS);
            }
            node.setAttribute('class', `sx-seg is-${segment.kind}`);
            node.dataset.segment = segment.id;
            const title = svg('title');
            title.textContent = `${segment.name} · ${entry.sensor.topic}`;
            node.appendChild(title);
            node.addEventListener('click', (event) => select(event, entry.key));
            svgRoot.appendChild(node);

            const radial = Math.hypot(sx, sy) || 1;
            const lx = sx + (sx / radial) * fontSize * 1.6;
            const ly = sy + (sy / radial) * fontSize * 1.6 + fontSize * 0.35;
            const label = svg('text', { x: lx, y: ly, 'font-size': fontSize, 'text-anchor': 'middle' });
            label.textContent = segment.name;
            labels.appendChild(label);
            extend(lx, ly, fontSize * 1.4);

            parts.set(entry.key, node);
        });

        svgRoot.appendChild(labels);
        const pad = MARGIN * Math.max(length, width);
        svgRoot.setAttribute('viewBox', `${minX - pad} ${minY - pad} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`);
        unplacedList.hidden = unplacedList.childElementCount === 0;
    }

    function paint(entries) {
        let alarm = false;
        entries.forEach((entry) => {
            const node = parts.get(entry.key);
            if (!node) {
                return;
            }
            const active = Boolean(binaryState(entry.sensor, entry.payload));
            alarm = alarm || active;
            node.classList.toggle('is-hit', active);
            node.classList.toggle('is-offline', entry.status === 'offline');
        });
        root.classList.toggle('is-alarm', alarm);
    }

    return {
        update(entries) {
            const next = entries.map((e) => `${e.key}|${e.sensor?.label}|${e.sensor?.topic}`).join(',');
            if (next !== signature) {
                signature = next;
                build(entries);
            }
            paint(entries);
        },
        destroy() {
            root.remove();
        },
    };
}
