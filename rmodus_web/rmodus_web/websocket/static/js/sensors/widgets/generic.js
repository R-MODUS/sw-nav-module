import { el, fieldLabel, formatValue } from '../meta.js';

const MAX_FIELDS = 4;

export function createGenericWidget(host) {
    const list = el('dl', 'sx-readouts is-generic');
    host.appendChild(list);
    let signature = '';

    return {
        update(entries) {
            const payload = entries[0]?.payload;
            if (!payload) {
                list.replaceChildren(el('dd', 'sx-muted', 'Čekám na data…'));
                signature = '';
                return;
            }
            const keys = Object.keys(payload)
                .filter((key) => !Array.isArray(payload[key]) && typeof payload[key] !== 'object')
                .slice(0, MAX_FIELDS);
            const nextSignature = keys.join(',');
            if (nextSignature !== signature) {
                signature = nextSignature;
                list.replaceChildren();
                keys.forEach((key) => {
                    list.appendChild(el('dt', null, fieldLabel(key)));
                    list.appendChild(el('dd', null)).dataset.field = key;
                });
            }
            list.querySelectorAll('dd[data-field]').forEach((node) => {
                node.textContent = formatValue(payload[node.dataset.field]);
            });
        },
        destroy() {
            list.remove();
        },
    };
}
