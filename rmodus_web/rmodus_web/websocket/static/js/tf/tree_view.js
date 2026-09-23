/**
 * Rekurzivní sbalitelný strom TF rámů.
 *
 * DOM se staví jen při změně topologie (rebuild). Živé hodnoty (zdraví, Hz)
 * mění updateLive() pouze u řádků, kde se změnil zobrazený text / stav.
 */

import { HEALTH } from './store.js';

const HEALTH_TITLES = {
    [HEALTH.OK]: 'Aktuální',
    [HEALTH.WARN]: 'Zpožděný',
    [HEALTH.ERROR]: 'Zastaralý',
    [HEALTH.STATIC]: 'Statický',
    [HEALTH.ROOT]: 'Kořen (bez vlastní transformace)',
};

function formatHz(hz) {
    if (hz === null) {
        return '';
    }
    return hz >= 10 ? `${Math.round(hz)} Hz` : `${hz.toFixed(1)} Hz`;
}

export class TfTreeView {
    constructor(container, { onSelect, collapsed, onCollapsedChange } = {}) {
        this.container = container;
        this.onSelect = onSelect || (() => {});
        this.onCollapsedChange = onCollapsedChange || (() => {});
        this.collapsed = new Set(collapsed || []);
        this.rows = new Map();
        this.selectedId = null;

        this.container.setAttribute('role', 'tree');
        this.container.addEventListener('click', (event) => this._handleClick(event));
        this.container.addEventListener('keydown', (event) => this._handleKey(event));
    }

    rebuild(store) {
        const { roots, children } = store.forest();
        this.rows.clear();
        const fragment = document.createDocumentFragment();
        roots.forEach((id) => fragment.appendChild(this._buildNode(store, id, children, 0, new Set())));
        this.container.replaceChildren(fragment);
        if (this.selectedId) {
            this.setSelected(this.selectedId, { reveal: false, store });
        }
        this.updateLive(store, performance.now());
    }

    _buildNode(store, id, children, depth, visited) {
        visited.add(id);
        const entry = store.get(id);
        const kids = (children.get(id) || []).filter((kid) => !visited.has(kid));
        const hasKids = kids.length > 0;
        const isCollapsed = hasKids && this.collapsed.has(id);

        const li = document.createElement('li');
        li.className = 'tf-tree-node';
        li.dataset.frame = id;
        li.setAttribute('role', 'treeitem');
        if (hasKids) {
            li.setAttribute('aria-expanded', String(!isCollapsed));
        }

        const row = document.createElement('div');
        row.className = 'tf-tree-row';
        row.tabIndex = 0;
        row.style.setProperty('--depth', String(depth));
        if (id === store.rootHint) {
            row.classList.add('is-fixed-hint');
        }

        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'tf-tree-toggle';
        toggle.tabIndex = -1;
        toggle.setAttribute('aria-label', 'Sbalit / rozbalit');
        toggle.hidden = !hasKids;

        const dot = document.createElement('span');
        dot.className = 'tf-health-dot';

        const name = document.createElement('span');
        name.className = 'tf-tree-name';
        name.textContent = id;

        const meta = document.createElement('span');
        meta.className = 'tf-tree-meta';

        row.append(toggle, dot, name, meta);
        li.appendChild(row);

        if (hasKids) {
            const group = document.createElement('ul');
            group.className = 'tf-tree-group';
            group.setAttribute('role', 'group');
            kids.forEach((kid) => group.appendChild(this._buildNode(store, kid, children, depth + 1, visited)));
            li.appendChild(group);
        }

        this.rows.set(id, { li, row, dot, meta, health: null, metaText: null, isStatic: entry && entry.isStatic });
        return li;
    }

    updateLive(store, now) {
        this.rows.forEach((refs, id) => {
            const entry = store.get(id);
            const health = store.health(entry, now);
            if (health !== refs.health) {
                refs.dot.dataset.health = health;
                refs.dot.title = HEALTH_TITLES[health] || '';
                refs.row.dataset.health = health;
                refs.health = health;
            }
            let metaText = '';
            if (entry && !entry.virtual) {
                metaText = entry.isStatic ? 'static' : formatHz(entry.hz);
            }
            if (metaText !== refs.metaText) {
                refs.meta.textContent = metaText;
                refs.metaText = metaText;
            }
        });
    }

    setSelected(id, { reveal = false, store = null } = {}) {
        if (this.selectedId && this.rows.has(this.selectedId)) {
            const prev = this.rows.get(this.selectedId);
            prev.row.classList.remove('is-selected');
            prev.li.removeAttribute('aria-selected');
        }
        this.selectedId = id;
        if (!id || !this.rows.has(id)) {
            return;
        }
        if (reveal && store) {
            this._expandAncestors(store, id);
        }
        const refs = this.rows.get(id);
        refs.row.classList.add('is-selected');
        refs.li.setAttribute('aria-selected', 'true');
        if (reveal) {
            refs.row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }

    _expandAncestors(store, id) {
        let changed = false;
        store.ancestors(id).forEach((ancestor) => {
            if (this.collapsed.delete(ancestor)) {
                changed = true;
                const refs = this.rows.get(ancestor);
                if (refs) {
                    refs.li.setAttribute('aria-expanded', 'true');
                }
            }
        });
        if (changed) {
            this.onCollapsedChange([...this.collapsed]);
        }
    }

    _toggleCollapsed(id, forceCollapsed) {
        const refs = this.rows.get(id);
        if (!refs || !refs.li.hasAttribute('aria-expanded')) {
            return;
        }
        const collapse = typeof forceCollapsed === 'boolean' ? forceCollapsed : !this.collapsed.has(id);
        if (collapse) {
            this.collapsed.add(id);
        } else {
            this.collapsed.delete(id);
        }
        refs.li.setAttribute('aria-expanded', String(!collapse));
        this.onCollapsedChange([...this.collapsed]);
    }

    _handleClick(event) {
        const node = event.target.closest('.tf-tree-node');
        if (!node || !this.container.contains(node)) {
            return;
        }
        const id = node.dataset.frame;
        if (event.target.closest('.tf-tree-toggle')) {
            this._toggleCollapsed(id);
            return;
        }
        const refs = this.rows.get(id);
        if (refs) {
            refs.row.focus({ preventScroll: true });
        }
        this.onSelect(this.selectedId === id ? null : id);
    }

    _visibleRows() {
        return [...this.container.querySelectorAll('.tf-tree-row')].filter((row) => row.offsetParent !== null);
    }

    _handleKey(event) {
        const row = event.target.closest('.tf-tree-row');
        if (!row) {
            return;
        }
        const id = row.parentElement.dataset.frame;
        const rows = this._visibleRows();
        const index = rows.indexOf(row);
        switch (event.key) {
            case 'ArrowDown':
                rows[Math.min(rows.length - 1, index + 1)]?.focus();
                break;
            case 'ArrowUp':
                rows[Math.max(0, index - 1)]?.focus();
                break;
            case 'ArrowRight':
                this._toggleCollapsed(id, false);
                break;
            case 'ArrowLeft':
                this._toggleCollapsed(id, true);
                break;
            case 'Enter':
            case ' ':
                this.onSelect(this.selectedId === id ? null : id);
                break;
            default:
                return;
        }
        event.preventDefault();
    }
}
