// Run with: node test_display.cjs (optional; Python tests do not need Node).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function loadUI() {
    const elements = new Map();
    const document = {
        querySelectorAll: () => [], addEventListener: () => {},
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, { addEventListener() {} });
            return elements.get(id);
        },
        createElement(tag) {
            return { tag, children: [], append(...items) { this.children.push(...items); } };
        }
    };
    const context = vm.createContext({ document, fetch: () => new Promise(() => {}) });
    vm.runInContext(fs.readFileSync(path.join(__dirname, 'static', 'app.js'), 'utf8'), context);
    return context;
}
const ui = loadUI();
test('UTC timestamp rolls over to the next day in Vietnam', () => {
    assert.equal(ui.formatDate('2026-10-29T23:21:42.158185+00:00'), '30/10/2026 06:21:42');
    assert.equal(ui.formatDate('2026-10-29T23:21:42Z'), '30/10/2026 06:21:42');
});
test('date-only warranty and ETA fields do not shift calendar days', () => {
    for (const key of ['expected_date', 'purchase_date', 'exp_date']) {
        assert.equal(ui.formatValue(key, '2026-11-01'), '01/11/2026');
    }
});
test('legacy timestamp and an explicit Vietnam offset represent the same instant', () => {
    assert.equal(ui.formatDate('2026-10-29T23:21:42'), '30/10/2026 06:21:42');
    assert.equal(ui.formatDate('2026-10-30T06:21:42+07:00'), '30/10/2026 06:21:42');
});
test('invalid and missing dates are not converted into invented dates', () => {
    for (const value of ['2026-02-30', 'not a date', '', null]) assert.equal(ui.formatDate(value), value);
});
test('old technician suffix is removed with whitespace and decomposed Unicode', () => {
    for (const name of ['KTV Thái Nguyên (mẫu)', ' KTV Thái Nguyên ( MẪU ) ', 'KTV Thái Nguyên (mẫu)'.normalize('NFD')]) {
        assert.equal(ui.formatValue('technician', name), 'KTV Thái Nguyên');
    }
    assert.equal(ui.formatValue('technician', 'Nguyễn Văn An'), 'Nguyễn Văn An');
});
test('tracking card uses formatted dates and technician names during rendering', () => {
    const root = { children: [], append(...items) { this.children.push(...items); } };
    ui.render({ requests: [{ created_at: '2026-10-29T23:21:42.158185+00:00', expected_date: '2026-11-01', technician: 'KTV Thái Nguyên (mẫu)' }] }, root);
    function text(node) { return (node.textContent || '') + (node.children || []).map(text).join(' '); }
    const output = text(root);
    assert.ok(output.includes('30/10/2026 06:21:42'));
    assert.ok(output.includes('01/11/2026'));
    assert.ok(output.includes('KTV Thái Nguyên'));
    assert.ok(!output.includes('(mẫu)') && !output.includes('+00:00'));
});
