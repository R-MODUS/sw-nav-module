import { BINARY_TYPES, binaryState, HISTORY_WINDOW_MS } from './binary.js';
import { sensorKey } from './meta.js';

const HISTORY_PRUNE_SLACK = 256;

const LIVE_MIN_MS = 1500;
const OFFLINE_MIN_MS = 5000;
const LIVE_PERIODS = 3;
const OFFLINE_PERIODS = 10;
const RATE_EMA_ALPHA = 0.2;
const TICK_MS = 500;

/** Latest data per sensor key. Updates are coalesced into one flush per animation frame. */
function createStore() {
    const entries = new Map();
    const dirty = new Set();
    const dataSubs = new Set();
    const catalogSubs = new Set();
    const statusSubs = new Set();
    const tickSubs = new Set();
    let catalog = [];
    let flushScheduled = false;
    let tickTimer = null;

    function ensureEntry(key) {
        let entry = entries.get(key);
        if (!entry) {
            entry = {
                key,
                sensor: null,
                payload: null,
                lastSeen: 0,
                intervalEma: 0,
                status: 'offline',
                // Binary sensors: [timestamp ms, state] per message, newest last.
                history: [],
            };
            entries.set(key, entry);
        }
        return entry;
    }

    function recordHistory(entry, now) {
        const sensor = entry.sensor || { sensor_type: entry.key.split(':')[0], topic: '' };
        const state = binaryState(sensor, entry.payload);
        if (state === null) {
            return;
        }
        const history = entry.history;
        history.push([now, state]);
        const cutoff = now - HISTORY_WINDOW_MS;
        if (history.length > HISTORY_PRUNE_SLACK && history[HISTORY_PRUNE_SLACK][0] < cutoff) {
            let drop = 0;
            while (drop < history.length && history[drop][0] < cutoff) {
                drop += 1;
            }
            history.splice(0, drop);
        }
    }

    function computeStatus(entry, now) {
        if (!entry.lastSeen) {
            return 'offline';
        }
        const age = now - entry.lastSeen;
        const period = entry.intervalEma || 0;
        if (age < Math.max(LIVE_MIN_MS, period * LIVE_PERIODS)) {
            return 'live';
        }
        if (age < Math.max(OFFLINE_MIN_MS, period * OFFLINE_PERIODS)) {
            return 'delayed';
        }
        return 'offline';
    }

    function refreshStatus(entry, now) {
        const next = computeStatus(entry, now);
        if (next === entry.status) {
            return;
        }
        entry.status = next;
        statusSubs.forEach((fn) => fn(entry));
    }

    function flush() {
        flushScheduled = false;
        if (dirty.size === 0) {
            return;
        }
        const keys = new Set(dirty);
        dirty.clear();
        const now = Date.now();
        keys.forEach((key) => {
            const entry = entries.get(key);
            if (entry) {
                refreshStatus(entry, now);
            }
        });
        dataSubs.forEach((sub) => {
            for (const key of sub.keys) {
                if (keys.has(key)) {
                    sub.fn(keys);
                    return;
                }
            }
        });
    }

    function scheduleFlush() {
        if (!flushScheduled) {
            flushScheduled = true;
            requestAnimationFrame(flush);
        }
    }

    function tick() {
        const now = Date.now();
        entries.forEach((entry) => refreshStatus(entry, now));
        tickSubs.forEach((fn) => fn(now));
    }

    return {
        get catalog() {
            return catalog;
        },

        entry(key) {
            return entries.get(key) || null;
        },

        setCatalog(sensors) {
            catalog = Array.isArray(sensors) ? sensors : [];
            const valid = new Set();
            catalog.forEach((sensor) => {
                const key = sensorKey(sensor.sensor_type, sensor.sensor_id);
                valid.add(key);
                const entry = ensureEntry(key);
                const frameId = entry.sensor?.frame_id;
                entry.sensor = sensor;
                if (!sensor.frame_id && frameId) {
                    sensor.frame_id = frameId;
                }
            });
            [...entries.keys()].forEach((key) => {
                if (!valid.has(key)) {
                    entries.delete(key);
                }
            });
            catalogSubs.forEach((fn) => fn(catalog));
        },

        ingest(message) {
            if (!message || !message.sensor_type || !message.sensor_id) {
                return;
            }
            const key = sensorKey(message.sensor_type, message.sensor_id);
            const entry = ensureEntry(key);
            const now = Date.now();
            if (entry.lastSeen) {
                const interval = now - entry.lastSeen;
                entry.intervalEma = entry.intervalEma
                    ? entry.intervalEma + RATE_EMA_ALPHA * (interval - entry.intervalEma)
                    : interval;
            }
            entry.lastSeen = now;
            entry.payload = message.payload;
            if (entry.sensor && message.frame_id) {
                entry.sensor.frame_id = String(message.frame_id).replace(/^\/+/, '');
            }
            if (BINARY_TYPES.has(message.sensor_type)) {
                recordHistory(entry, now);
            }
            dirty.add(key);
            scheduleFlush();
        },

        rateHz(key) {
            const entry = entries.get(key);
            return entry && entry.intervalEma > 0 ? 1000 / entry.intervalEma : 0;
        },

        /** fn(changedKeys) is called at most once per frame when any of `keys` got new data. */
        subscribe(keys, fn) {
            const sub = { keys: new Set(keys), fn };
            dataSubs.add(sub);
            return {
                setKeys(next) {
                    sub.keys = new Set(next);
                },
                unsubscribe() {
                    dataSubs.delete(sub);
                },
            };
        },

        onCatalog(fn) {
            catalogSubs.add(fn);
            return () => catalogSubs.delete(fn);
        },

        onStatus(fn) {
            statusSubs.add(fn);
            return () => statusSubs.delete(fn);
        },

        onTick(fn) {
            tickSubs.add(fn);
            if (!tickTimer) {
                tickTimer = window.setInterval(tick, TICK_MS);
            }
            return () => {
                tickSubs.delete(fn);
                if (tickSubs.size === 0 && statusSubs.size === 0 && tickTimer) {
                    window.clearInterval(tickTimer);
                    tickTimer = null;
                }
            };
        },
    };
}

export const store = createStore();
