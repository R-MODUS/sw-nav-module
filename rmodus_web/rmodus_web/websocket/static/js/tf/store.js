/**
 * TF data store: poslední transformace z `tf_3d` + odvozený strom a zdraví rámů.
 *
 * Zprávy mutují záznamy na místě a jen zvyšují čítače verzí. Konzumenti
 * (3D scéna v rAF, DOM na pomalém timeru) si verze porovnávají sami, takže
 * vysokofrekvenční TF nevyvolává žádné překreslování DOM.
 */

export const HEALTH = Object.freeze({
    OK: 'ok',
    WARN: 'warn',
    ERROR: 'error',
    STATIC: 'static',
    ROOT: 'root',
});

export function normalizeFrameId(frameId) {
    if (!frameId) {
        return null;
    }
    const id = String(frameId).replace(/^\/+/, '');
    return id || null;
}

function createEntry(id) {
    return {
        id,
        parent: null,
        // Rám, který se objevil jen jako parent (např. odom / map) – nemá vlastní transform.
        virtual: true,
        t: [0, 0, 0],
        q: [0, 0, 0, 1],
        isStatic: false,
        hz: null,
        ageAtRx: null,
        rxAt: 0,
        rev: 0,
    };
}

export class TfStore {
    constructor() {
        this.frames = new Map();
        this.rootHint = 'base_link';
        this.warnSec = 0.5;
        this.errorSec = 2.0;
        this.streamStale = true;
        this.dataVersion = 0;
        this.topologyVersion = 0;
        this._forestCache = null;
        this._forestVersion = -1;
    }

    applyTf3d(message) {
        const now = performance.now();
        const frames = Array.isArray(message && message.frames) ? message.frames : [];
        this.rootHint = normalizeFrameId(message.root_frame) || this.rootHint;
        if (Number.isFinite(message.stale_warn_sec)) {
            this.warnSec = message.stale_warn_sec;
        }
        if (Number.isFinite(message.stale_error_sec)) {
            this.errorSec = message.stale_error_sec;
        }

        let topologyChanged = false;
        for (const raw of frames) {
            const id = normalizeFrameId(raw.child);
            if (!id) {
                continue;
            }
            const parent = normalizeFrameId(raw.parent);
            let entry = this.frames.get(id);
            if (!entry) {
                entry = createEntry(id);
                this.frames.set(id, entry);
                topologyChanged = true;
            }
            if (entry.virtual || entry.parent !== parent) {
                topologyChanged = true;
            }
            entry.virtual = false;
            entry.parent = parent;
            if (Array.isArray(raw.t) && raw.t.length === 3) {
                entry.t[0] = raw.t[0];
                entry.t[1] = raw.t[1];
                entry.t[2] = raw.t[2];
            }
            if (Array.isArray(raw.q) && raw.q.length === 4) {
                entry.q[0] = raw.q[0];
                entry.q[1] = raw.q[1];
                entry.q[2] = raw.q[2];
                entry.q[3] = raw.q[3];
            }
            entry.isStatic = Boolean(raw.static);
            entry.hz = Number.isFinite(raw.hz) ? raw.hz : null;
            entry.ageAtRx = Number.isFinite(raw.age) ? raw.age : null;
            entry.rxAt = now;
            entry.rev += 1;

            if (parent && !this.frames.has(parent)) {
                this.frames.set(parent, createEntry(parent));
                topologyChanged = true;
            }
        }

        if (frames.length > 0) {
            this.streamStale = false;
        }
        this.dataVersion += 1;
        if (topologyChanged) {
            this.topologyVersion += 1;
        }
        return topologyChanged;
    }

    get size() {
        return this.frames.size;
    }

    has(id) {
        return this.frames.has(id);
    }

    get(id) {
        return this.frames.get(id) || null;
    }

    sortedIds() {
        return [...this.frames.keys()].sort((a, b) => a.localeCompare(b));
    }

    ageSec(entry, now = performance.now()) {
        if (!entry || entry.virtual || entry.ageAtRx === null) {
            return null;
        }
        return entry.ageAtRx + Math.max(0, now - entry.rxAt) / 1000;
    }

    health(entry, now = performance.now()) {
        if (!entry || entry.virtual) {
            return HEALTH.ROOT;
        }
        if (entry.isStatic) {
            return HEALTH.STATIC;
        }
        const age = this.ageSec(entry, now);
        if (age === null || age > this.errorSec) {
            return HEALTH.ERROR;
        }
        if (age > this.warnSec) {
            return HEALTH.WARN;
        }
        return HEALTH.OK;
    }

    /** { roots: string[], children: Map<id, string[]> } – cachované podle topologyVersion. */
    forest() {
        if (this._forestCache && this._forestVersion === this.topologyVersion) {
            return this._forestCache;
        }
        const children = new Map();
        const roots = [];
        for (const entry of this.frames.values()) {
            const parent = entry.parent && this.frames.has(entry.parent) ? entry.parent : null;
            if (!parent || this._isInCycle(entry.id)) {
                roots.push(entry.id);
                continue;
            }
            if (!children.has(parent)) {
                children.set(parent, []);
            }
            children.get(parent).push(entry.id);
        }
        const byName = (a, b) => a.localeCompare(b);
        children.forEach((list) => list.sort(byName));
        const hintChain = new Set([this.rootHint, ...this.ancestors(this.rootHint)]);
        roots.sort((a, b) => {
            const aHasHint = hintChain.has(a);
            const bHasHint = hintChain.has(b);
            if (aHasHint !== bHasHint) {
                return aHasHint ? -1 : 1;
            }
            return byName(a, b);
        });
        this._forestCache = { roots, children };
        this._forestVersion = this.topologyVersion;
        return this._forestCache;
    }

    /** Předci od přímého rodiče ke kořeni (bez samotného id). */
    ancestors(id) {
        const chain = [];
        const seen = new Set([id]);
        let entry = this.frames.get(id);
        while (entry && entry.parent && !seen.has(entry.parent)) {
            chain.push(entry.parent);
            seen.add(entry.parent);
            entry = this.frames.get(entry.parent);
        }
        return chain;
    }

    _isInCycle(id) {
        const seen = new Set();
        let current = this.frames.get(id);
        while (current && current.parent) {
            if (current.parent === id) {
                return true;
            }
            if (seen.has(current.parent)) {
                return false;
            }
            seen.add(current.parent);
            current = this.frames.get(current.parent);
        }
        return false;
    }
}

/** ROS RPY (pevné osy X-Y-Z = Rz·Ry·Rx) z kvaternionu [x, y, z, w]. */
export function quaternionToRpy(q) {
    const [x, y, z, w] = q;
    const roll = Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
    const sinPitch = Math.max(-1, Math.min(1, 2 * (w * y - z * x)));
    const pitch = Math.asin(sinPitch);
    const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
    return [roll, pitch, yaw];
}
