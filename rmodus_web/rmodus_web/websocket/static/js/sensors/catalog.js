import { CATEGORIES, el, sensorKey, STATUS_LABELS, typeCategory, typeLabel } from './meta.js';
import { get, replace, set } from './prefs.js';
import { store } from './store.js';
import { WIDGET_ITEMS } from './tiles.js';

/** Collapsible, category-grouped sensor tree with pin checkboxes and live status dots. */
export function createCatalog(root, { isPinned, setPinned, onOpenSensor }) {
    const tree = root.querySelector('[data-role="tree"]');
    const search = root.querySelector('[data-role="search"]');
    const collapseBtn = root.querySelector('[data-role="collapse"]');
    const collapsedGroups = { ...get('sensors.groupsCollapsed', {}) };
    const dots = new Map();
    let filter = '';

    root.classList.toggle('is-collapsed', Boolean(get('sensors.catalogCollapsed', false)));

    collapseBtn?.addEventListener('click', () => {
        const collapsed = !root.classList.contains('is-collapsed');
        root.classList.toggle('is-collapsed', collapsed);
        set('sensors.catalogCollapsed', collapsed);
    });

    search?.addEventListener('input', () => {
        filter = search.value.trim().toLowerCase();
        render();
    });

    function matches(sensor) {
        if (!filter) {
            return true;
        }
        return [sensor.label, sensor.topic, sensor.sensor_type, typeLabel(sensor.sensor_type)]
            .filter(Boolean)
            .some((text) => String(text).toLowerCase().includes(filter));
    }

    function paintDot(dot, status) {
        dot.dataset.status = status;
        dot.title = STATUS_LABELS[status];
    }

    function renderRow(sensor) {
        const key = sensorKey(sensor.sensor_type, sensor.sensor_id);
        const row = el('li', 'sx-row');
        row.classList.toggle('is-pinned', isPinned(key));

        const checkbox = el('input');
        checkbox.type = 'checkbox';
        checkbox.checked = isPinned(key);
        checkbox.title = checkbox.checked ? 'Odebrat z přehledu' : 'Přidat do přehledu';
        checkbox.setAttribute('aria-label', `V přehledu: ${sensor.label || sensor.sensor_id}`);
        checkbox.addEventListener('change', () => setPinned([key], checkbox.checked));

        const dot = el('span', 'sx-dot');
        paintDot(dot, store.entry(key)?.status || 'offline');
        dots.set(key, dot);

        const name = el('button', 'sx-row-name');
        name.type = 'button';
        name.title = `${sensor.topic}${sensor.frame_id ? ` · ${sensor.frame_id}` : ''}\nKlik = detail`;
        name.append(el('span', 'sx-row-label', sensor.label || sensor.sensor_id), el('span', 'sx-row-topic', sensor.topic));
        name.addEventListener('click', () => onOpenSensor(key));

        row.append(checkbox, dot, name);
        return row;
    }

    function renderGroup(category, sensors) {
        const keys = sensors.map((s) => sensorKey(s.sensor_type, s.sensor_id));
        const pinnedCount = keys.filter(isPinned).length;
        const collapsed = !filter && Boolean(collapsedGroups[category.id]);

        const group = el('section', `sx-group${collapsed ? ' is-collapsed' : ''}`);
        const head = el('div', 'sx-group-head');

        const all = el('input');
        all.type = 'checkbox';
        all.checked = pinnedCount === keys.length;
        all.indeterminate = pinnedCount > 0 && pinnedCount < keys.length;
        all.title = 'Vybrat celou skupinu';
        all.setAttribute('aria-label', `Celá skupina ${category.label}`);
        all.addEventListener('change', () => setPinned(keys, all.checked));

        const toggle = el('button', 'sx-group-toggle');
        toggle.type = 'button';
        toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(
            el('span', 'sx-caret', '▸'),
            el('span', 'sx-group-label', category.label),
            el('span', 'sx-group-count', `${pinnedCount}/${keys.length}`),
        );
        toggle.addEventListener('click', () => {
            collapsedGroups[category.id] = !collapsedGroups[category.id];
            replace('sensors.groupsCollapsed', collapsedGroups);
            render();
        });

        head.append(all, toggle);
        const list = el('ul', 'sx-group-list');
        sensors.forEach((sensor) => list.appendChild(renderRow(sensor)));
        group.append(head, list);
        return group;
    }

    function renderWidgetGroup() {
        const items = WIDGET_ITEMS.filter(
            (item) => !filter || `${item.label} ${item.hint}`.toLowerCase().includes(filter),
        );
        if (items.length === 0) {
            return null;
        }
        const collapsed = !filter && Boolean(collapsedGroups.widgets);
        const group = el('section', `sx-group is-widgets${collapsed ? ' is-collapsed' : ''}`);
        const head = el('div', 'sx-group-head');
        const toggle = el('button', 'sx-group-toggle');
        toggle.type = 'button';
        toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(el('span', 'sx-caret', '▸'), el('span', 'sx-group-label', 'Widgety'));
        toggle.addEventListener('click', () => {
            collapsedGroups.widgets = !collapsedGroups.widgets;
            replace('sensors.groupsCollapsed', collapsedGroups);
            render();
        });
        head.appendChild(toggle);

        const list = el('ul', 'sx-group-list');
        items.forEach((item) => {
            const row = el('li', 'sx-row is-widget');
            row.classList.toggle('is-pinned', isPinned(item.key));
            const checkbox = el('input');
            checkbox.type = 'checkbox';
            checkbox.checked = isPinned(item.key);
            checkbox.setAttribute('aria-label', `V přehledu: ${item.label}`);
            checkbox.addEventListener('change', () => setPinned([item.key], checkbox.checked));
            const icon = el('span', 'sx-widget-icon', '◇');
            const name = el('label', 'sx-row-name');
            name.title = item.hint;
            name.append(el('span', 'sx-row-label', item.label), el('span', 'sx-row-topic', item.hint));
            name.addEventListener('click', () => {
                checkbox.checked = !checkbox.checked;
                checkbox.dispatchEvent(new Event('change'));
            });
            row.append(checkbox, icon, name);
            list.appendChild(row);
        });
        group.append(head, list);
        return group;
    }

    function render() {
        dots.clear();
        tree.replaceChildren();
        const widgetGroup = renderWidgetGroup();
        if (widgetGroup) {
            tree.appendChild(widgetGroup);
        }
        const catalog = store.catalog;
        if (catalog.length === 0) {
            tree.appendChild(el('p', 'sx-muted sx-tree-empty', 'Čekám na katalog senzorů…'));
            return;
        }
        const byCategory = new Map(CATEGORIES.map((c) => [c.id, []]));
        catalog.filter(matches).forEach((sensor) => {
            byCategory.get(typeCategory(sensor.sensor_type)).push(sensor);
        });
        let shown = 0;
        CATEGORIES.forEach((category) => {
            const sensors = byCategory.get(category.id);
            if (sensors.length > 0) {
                shown += sensors.length;
                tree.appendChild(renderGroup(category, sensors));
            }
        });
        if (shown === 0 && !widgetGroup) {
            tree.appendChild(el('p', 'sx-muted sx-tree-empty', 'Nic neodpovídá hledání.'));
        }
    }

    const offStatus = store.onStatus((entry) => {
        const dot = dots.get(entry.key);
        if (dot) {
            paintDot(dot, entry.status);
        }
    });

    return {
        render,
        destroy() {
            offStatus();
        },
    };
}
