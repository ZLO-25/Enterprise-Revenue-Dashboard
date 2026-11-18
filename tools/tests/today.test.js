// node --test tools/tests/today.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const T = require('../../assets/today.js');

test('台北日期跨日：UTC 16:30 已是台北隔天', () => {
  assert.equal(T.tpeDate(new Date('2026-11-18T16:30:00Z')), '2026-11-19');
  assert.equal(T.tpeDate(new Date('2026-12-31T16:00:00Z')), '2027-01-01');
  assert.equal(T.tpeDate(new Date('2026-11-18T15:59:00Z')), '2026-11-18');
});

test('週一起算：週日算上一週，跨年也對', () => {
  assert.equal(T.monday('2026-11-22'), '2026-11-16');   // 週日
  assert.equal(T.monday('2026-11-16'), '2026-11-16');   // 週一
  assert.equal(T.monday('2027-01-01'), '2026-12-28');   // 週五，跨年
});

const ev = (d, code, est) => ({ d, code, name: code, t: '財報', est: !!est, href: '#' });

test('pick：優先順序、已公告在預估前、最多 3 則並算 more', () => {
  const r = T.pick({
    today: '2026-11-18', limit: 3, statusHref: 's/', alerts: ['A', 'B', 'C'],
    events: [ev('2026-11-20', 'X', true), ev('2026-11-20', 'Y', false), ev('2026-11-18', 'Z', false), ev('2026-12-30', 'FAR', false)],
    lights: [{ d: '2026-11-17', code: 'a', k: 'om', name: '營業利益率', g: 'biz', from: 'y', to: 'r' }, { d: '2026-11-17', code: 'b', k: 'pe', g: 'val', from: 'g', to: 'r' }],
    signals: [{ d: '2026-11-17', code: 'c', name: '本益比', now: 30, kind: 'exceed' }],
  });
  assert.equal(r.items[0].kind, 'alert');
  assert.match(r.items[1].text, /^今天 Z/);
  assert.match(r.items[2].text, /Y .*已公告/);          // 已公告 Y 排在預估 X 前面
  assert.equal(r.more, 2);                              // X、體質燈號（估值燈號 val 不進體質；估值訊號不進「今天該看什麼」）
  assert.ok(!r.items.some(i => i.kind === 'signal'));
  assert.ok(!r.items.some(i => /FAR/.test(i.text)));    // 7 天外不顯示
});

test('pick：只有體質燈號變差才算（紅→黃不算）、舊的不顯示', () => {
  const r = T.pick({ today: '2026-11-18', lights: [{ d: '2026-11-01', code: 'a', k: 'om', g: 'biz', from: 'g', to: 'r' }, { d: '2026-11-17', code: 'b', k: 'om', g: 'biz', from: 'r', to: 'g' }, { d: '2026-11-17', code: 'c', k: 'om', g: 'biz', from: 'r', to: 'y' }] });
  assert.equal(r.items.length, 0);
});

test('pick：輔助（aux）指標的燈號變化不算體質轉差', () => {
  const r = T.pick({ today: '2026-11-18', lights: [{ d: '2026-11-17', code: 'a', k: 'revYoy', g: 'aux', from: 'g', to: 'r' }, { d: '2026-11-17', code: 'b', k: 'roe', g: 'biz', from: 'g', to: 'y' }] });
  assert.equal(r.items.length, 1);
  assert.match(r.items[0].text, /^體質燈號轉黃/);
});

test('weeks：90 天內分組、空週合併、邊界日期', () => {
  const evs = [ev('2026-11-18', 'A'), ev('2026-11-22', 'B'), ev('2026-12-10', 'C', true), ev('2027-02-16', 'OUT'), ev('2027-02-15', 'IN')];
  const W = T.weeks(evs, '2026-11-18', 90);              // 90 天後 = 2027-02-16
  const real = W.filter(w => !w.empty);
  assert.deepEqual(real[0].items.map(e => e.code), ['A', 'B']);   // 11/22 週日仍在 11/16 那一週
  assert.ok(W.some(w => w.empty));
  const all = real.flatMap(w => w.items.map(e => e.code));
  assert.ok(all.includes('IN') && all.includes('OUT'));  // 邊界含最後一天（2027-02-16）
});

test('weeks：今天以前的事件不在清單', () => {
  const W = T.weeks([ev('2026-11-17', 'OLD')], '2026-11-18', 30);
  assert.equal(W.flatMap(w => w.items).length, 0);
});

test('ics：只含已公告、全天事件、換行 CRLF', () => {
  const s = T.ics([ev('2026-12-01', 'CRWD'), ev('2026-12-09', 'AVGO', true)]);
  assert.match(s, /DTSTART;VALUE=DATE:20261201/);
  assert.match(s, /DTEND;VALUE=DATE:20261202/);
  assert.ok(!/AVGO/.test(s));
  assert.ok(s.includes('\r\n'));
});
