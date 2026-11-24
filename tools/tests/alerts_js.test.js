/* assets/alerts.js 的純函式測試（node --test tools/tests/alerts_js.test.js）：到價判斷與 Python（tools/alerts.py）跑同一份案例 tools/tests/alerts_cases.json，
   另測建立／改價規則的邏輯。不需要瀏覽器：用 vm 載入檔案，沒有 document 時不會自動啟動。 */
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), path = require('path'), vm = require('vm');
const code = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'alerts.js'), 'utf8');
const A = vm.runInContext(code + '\n;ALERTS', vm.createContext({ console, crypto: globalThis.crypto, TextEncoder, TextDecoder, Blob, Response, atob, btoa, setTimeout, clearTimeout, Date, Math }));
const CASES = JSON.parse(fs.readFileSync(path.join(__dirname, 'alerts_cases.json'), 'utf8'));

test('到價判斷：共用案例', () => {
  for (const c of CASES.hit) assert.deepEqual(JSON.parse(JSON.stringify(A.hitFor(c.rule, c.bars))), c.hit, c.name);
});
test('到價紀錄有效／作廢：共用案例', () => {
  for (const c of CASES.valid) assert.equal(A.hitValid(c.rule, c.hit), c.valid, c.name);
});
test('方向自動與百分比價格：共用案例', () => {
  for (const c of CASES.dir) assert.equal(A.dirFor(c.p, c.last), c.dir);
  for (const c of CASES.pct) assert.ok(Math.abs(A.pctPrice(c.base, c.pct) - c.p) < 1e-4, JSON.stringify(c));
});
test('makeRule：價格與百分比、方向自動／手動、起算日與基準', () => {
  const item = { code: 'nvda', name: '輝達', kind: 'stock' }, last = { t: '2026-11-23', c: 100 };
  let r = A.makeRule(item, last, { mode: 'price', p: 110, dir: 'auto' });
  assert.deepEqual([r.dir, r.dirAuto, r.since, r.base.c, r.mode, r.on, r.p], ['up', true, '2026-11-23', 100, 'price', true, 110]);
  r = A.makeRule(item, last, { mode: 'price', p: 90, dir: 'auto' });
  assert.equal(r.dir, 'down');
  r = A.makeRule(item, last, { mode: 'pct', pct: -10, dir: 'auto' });
  assert.deepEqual([r.p, r.pct, r.dir, r.mode], [90, -10, 'down', 'pct']);
  r = A.makeRule(item, last, { mode: 'price', p: 90, dir: 'up' });
  assert.deepEqual([r.dir, r.dirAuto], ['up', false]);
  assert.ok(A.makeRule(item, last, { mode: 'price', p: 1, n: 'x'.repeat(60) }).n.length <= 40);
});
test('repriced：方向自動時重算；起算日重設；％ 模式更新 %', () => {
  const last = { t: '2026-11-24', c: 100 };
  const r = { id: 'a', p: 110, dir: 'up', dirAuto: true, mode: 'pct', pct: 10, base: { t: '2026-11-20', c: 100 }, since: '2026-11-20', on: true };
  const x = A.repriced(r, 95, last);
  assert.deepEqual([x.p, x.dir, x.since, x.pct], [95, 'down', '2026-11-24', -5]);
  const y = A.repriced(Object.assign({}, r, { dirAuto: false }), 95, last);
  assert.equal(y.dir, 'up');
});
test('setOn：重新開啟重設起算日並重算自動方向；關閉記時間', () => {
  const last = { t: '2026-11-24', c: 100 };
  const r = { p: 90, dir: 'up', dirAuto: true, since: '2026-11-01', on: false, offAt: 'x' };
  const o = A.setOn(r, true, last);
  assert.deepEqual([o.on, o.since, o.dir, o.offAt], [true, '2026-11-24', 'down', null]);
  const c = A.setOn(o, false, last);
  assert.equal(c.on, false); assert.ok(c.offAt);
});
