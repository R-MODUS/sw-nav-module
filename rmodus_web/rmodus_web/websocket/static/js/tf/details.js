/**
 * Panel detailu vybraného rámu. Pole jsou v HTML jako [data-field="…"];
 * update() přepisuje jen texty, které se změnily.
 */

import { HEALTH, quaternionToRpy } from './store.js';

const HEALTH_LABELS = {
    [HEALTH.OK]: 'Aktuální',
    [HEALTH.WARN]: 'Zpožděný',
    [HEALTH.ERROR]: 'Zastaralý',
    [HEALTH.STATIC]: 'Statický',
    [HEALTH.ROOT]: 'Kořen',
};

const RAD2DEG = 180 / Math.PI;
const DASH = '—';

function fmt(value, digits) {
    return Number.isFinite(value) ? value.toFixed(digits) : DASH;
}

function formatAge(age) {
    if (age === null) {
        return DASH;
    }
    if (age < 1) {
        return `${Math.round(age * 1000)} ms`;
    }
    if (age < 120) {
        return `${age.toFixed(1)} s`;
    }
    return `${Math.floor(age / 60)} min`;
}

export class TfDetailsPanel {
    constructor(root) {
        this.root = root;
        this.fields = new Map();
        root.querySelectorAll('[data-field]').forEach((el) => this.fields.set(el.dataset.field, el));
        this.body = root.querySelector('[data-role="details-body"]');
        this.empty = root.querySelector('[data-role="details-empty"]');
        this.cache = new Map();
        this.lastHealth = null;
    }

    _set(key, text) {
        if (this.cache.get(key) === text) {
            return;
        }
        this.cache.set(key, text);
        const el = this.fields.get(key);
        if (el) {
            el.textContent = text;
        }
    }

    update(store, frameId, now = performance.now()) {
        const entry = frameId ? store.get(frameId) : null;
        if (this.body) {
            this.body.hidden = !entry;
        }
        if (this.empty) {
            this.empty.hidden = Boolean(entry);
        }
        if (!entry) {
            return;
        }

        const health = store.health(entry, now);
        if (health !== this.lastHealth) {
            this.root.dataset.health = health;
            this.lastHealth = health;
        }

        this._set('name', entry.id);
        this._set('parent', entry.parent || DASH);
        this._set('health', HEALTH_LABELS[health] || DASH);
        this._set('kind', entry.virtual ? 'bez transformace' : entry.isStatic ? '/tf_static' : '/tf');

        const hasTf = !entry.virtual;
        const [tx, ty, tz] = entry.t;
        const [qx, qy, qz, qw] = entry.q;
        this._set('tx', hasTf ? fmt(tx, 4) : DASH);
        this._set('ty', hasTf ? fmt(ty, 4) : DASH);
        this._set('tz', hasTf ? fmt(tz, 4) : DASH);
        this._set('qx', hasTf ? fmt(qx, 4) : DASH);
        this._set('qy', hasTf ? fmt(qy, 4) : DASH);
        this._set('qz', hasTf ? fmt(qz, 4) : DASH);
        this._set('qw', hasTf ? fmt(qw, 4) : DASH);

        const rpy = hasTf ? quaternionToRpy(entry.q) : [NaN, NaN, NaN];
        ['roll', 'pitch', 'yaw'].forEach((axis, i) => {
            this._set(`${axis}_rad`, Number.isFinite(rpy[i]) ? `${rpy[i].toFixed(4)} rad` : DASH);
            this._set(`${axis}_deg`, Number.isFinite(rpy[i]) ? `${(rpy[i] * RAD2DEG).toFixed(2)}°` : DASH);
        });

        let hzText = DASH;
        if (hasTf && entry.isStatic) {
            hzText = 'statický';
        } else if (entry.hz !== null) {
            hzText = `${entry.hz.toFixed(1)} Hz`;
        }
        this._set('hz', hzText);
        this._set('age', formatAge(store.ageSec(entry, now)));
    }
}
