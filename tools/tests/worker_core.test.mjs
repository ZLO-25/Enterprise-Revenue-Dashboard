/* 到價提醒 Worker 核心（worker/core.js）的測試：node --test tools/tests/worker_core.test.mjs
   全部用假的 GitHub（記憶體裡的檔案＋sha），不上網。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import * as C from '../../worker/core.js';

const KEY_BYTES = crypto.getRandomValues(new Uint8Array(32));
const KEY_B64 = C.b64e(KEY_BYTES);
const OTHER_B64 = C.b64e(crypto.getRandomValues(new Uint8Array(32)));
const ENV = { REPO: 'o/r', ORIGIN: 'https://zlo-25.github.io', ALERT_KEY: KEY_B64, GH_TOKEN: 'tok' };
const NOW = Date.UTC(2026, 10, 24, 1, 0, 0);

const rule = (o = {}) => ({ id: 'r1', code: 'nvda', kind: 'stock', name: 'NVIDIA', p: 150.5, dir: 'up', dirAuto: true, mode: 'price', n: '', on: true, since: '2026-11-20', created: '2026-11-24T00:00:00Z', updated: '2026-11-24T00:00:00Z', offAt: null, ...o });

/* 假的 GitHub：store.file＝{sha,text}；conflicts＝接下來有幾次 PUT 要回 409 */
function fakeGh(init) {
  const s = { file: init || null, puts: [], conflicts: 0, sha: 1, dispatched: [], bodies: [] };
  s.fetch = async (url, o = {}) => {
    const m = o.method || 'GET';
    if (url.includes('/dispatches')) { s.dispatched.push(JSON.parse(o.body)); return new Response(null, { status: 204 }); }
    if (m === 'GET') {
      if (!s.file) return new Response('{}', { status: 404 });
      return new Response(JSON.stringify({ sha: s.file.sha, content: C.b64e(new TextEncoder().encode(s.file.text)).replace(/(.{60})/g, '$1\n') }), { status: 200 });
    }
    const b = JSON.parse(o.body); s.bodies.push(b);
    if (s.conflicts > 0) { s.conflicts--; return new Response('{}', { status: 409 }); }
    if (s.file && b.sha !== s.file.sha) return new Response('{}', { status: 409 });
    s.file = { sha: 's' + (++s.sha), text: new TextDecoder().decode(C.b64d(b.content)) }; s.puts.push(b);
    return new Response('{}', { status: 200 });
  };
  return s;
}
async function envelope(op, keyB64 = KEY_B64, ts = NOW) {
  return JSON.stringify(await C.encryptJson({ ts, ...op }, await C.importKey(keyB64)));
}
const post = (body, origin = ENV.ORIGIN) => new Request('https://w.example/op', { method: 'POST', body, headers: { Origin: origin } });
const stored = async (gh) => C.decryptJson(JSON.parse(gh.file.text), await C.importKey(KEY_B64));

test('加解密來回，格式是 {iv,ct}', async () => {
  const k = await C.importKey(KEY_B64), f = await C.encryptJson({ a: '中文', b: [1, 2] }, k);
  assert.deepEqual(Object.keys(f).sort(), ['ct', 'iv', 'v']);
  assert.deepEqual(await C.decryptJson(f, k), { a: '中文', b: [1, 2] });
});

test('錯的金鑰 → 401，且完全不寫 GitHub', async () => {
  const gh = fakeGh();
  const r = await C.handleRequest(post(await envelope({ op: 'put', rule: rule() }, OTHER_B64)), ENV, gh.fetch, NOW);
  assert.equal(r.status, 401);
  assert.equal(gh.puts.length, 0);
});

test('過期或未來的時間戳 → 401', async () => {
  for (const ts of [NOW - 301000, NOW + 301000]) {
    const gh = fakeGh();
    const r = await C.handleRequest(post(await envelope({ op: 'put', rule: rule() }, KEY_B64, ts)), ENV, gh.fetch, NOW);
    assert.equal(r.status, 401); assert.equal(gh.puts.length, 0);
  }
  const gh = fakeGh();
  assert.equal((await C.handleRequest(post(await envelope({ op: 'put', rule: rule() }, KEY_B64, NOW - 299000)), ENV, gh.fetch, NOW)).status, 200);
});

test('封包格式不對 → 400', async () => {
  const r = await C.handleRequest(post('not json'), ENV, fakeGh().fetch, NOW);
  assert.equal(r.status, 400);
});

test('put 新增、更新（保留 created）；del；delOff', async () => {
  const gh = fakeGh();
  const go = async (op) => C.handleRequest(post(await envelope(op)), ENV, gh.fetch, NOW);
  assert.equal((await go({ op: 'put', rule: rule() })).status, 200);
  assert.equal((await go({ op: 'put', rule: rule({ id: 'r2', code: 'ym', kind: 'fut', name: '小道瓊', on: false }) })).status, 200);
  assert.equal((await go({ op: 'put', rule: rule({ id: 'r3', on: false }) })).status, 200);
  let d = await stored(gh);
  assert.deepEqual(d.rules.map((x) => x.id), ['r1', 'r2', 'r3']);
  await go({ op: 'put', rule: rule({ p: 160, created: '2000-01-01T00:00:00Z' }) });
  d = await stored(gh);
  assert.equal(d.rules.find((x) => x.id === 'r1').p, 160);
  assert.equal(d.rules.find((x) => x.id === 'r1').created, '2026-11-24T00:00:00Z');   // created 以第一次為準
  await go({ op: 'delOff' });
  d = await stored(gh);
  assert.deepEqual(d.rules.map((x) => x.id), ['r1']);
  await go({ op: 'del', id: 'r1' });
  d = await stored(gh);
  assert.deepEqual(d.rules, []);
  assert.equal((await go({ op: 'del', id: 'nope' })).status, 200);       // 刪不存在的＝沒事
});

test('commit 訊息不含價格與代號', async () => {
  const gh = fakeGh();
  await C.handleRequest(post(await envelope({ op: 'put', rule: rule({ p: 150.5 }) })), ENV, gh.fetch, NOW);
  assert.equal(gh.puts[0].message, '到價提醒設定更新');
  assert.equal(gh.puts[0].branch, 'main');
  assert.ok(!/150|nvda/i.test(gh.file.text));                              // 檔案本身是密文
});

test('欄位白名單：多的欄位被丟掉、型別錯誤被拒絕', async () => {
  const gh = fakeGh();
  const go = async (r) => C.handleRequest(post(await envelope({ op: 'put', rule: r })), ENV, gh.fetch, NOW);
  assert.equal((await go({ ...rule(), evil: '<script>', __proto__x: 1 })).status, 200);
  assert.ok(!('evil' in (await stored(gh)).rules[0]));
  for (const bad of [rule({ p: NaN }), rule({ p: Infinity }), rule({ p: '150' }), rule({ p: -1 }), rule({ p: 0 }), rule({ id: 'a b' }), rule({ id: '' }),
    rule({ code: 'NVDA' }), rule({ kind: 'bond' }), rule({ dir: 'sideways' }), rule({ on: 'yes' }), rule({ since: '2026/11/20' }), rule({ n: 'x'.repeat(41) }),
    rule({ name: '' }), rule({ mode: 'pct', pct: 5 }), rule({ mode: 'pct', pct: 'a', base: { t: '2026-11-20', c: 100 } }), rule({ mode: 'pct', pct: -100, base: { t: '2026-11-20', c: 100 } }),
    rule({ base: { t: 'x', c: 1 } }), rule({ base: { t: '2026-11-20', c: -1 } }), rule({ created: 5 }), null, 'str', []]) {
    assert.equal((await go(bad)).status, 400, JSON.stringify(bad));
  }
  assert.equal((await go(rule({ id: 'p1', mode: 'pct', pct: -10, base: { t: '2026-11-20', c: 100 }, p: 90 }))).status, 200);
  assert.equal((await go(rule({ id: 'n1', n: '字'.repeat(40) }))).status, 200);          // 40 個中文字剛好
  const r = await C.handleRequest(post(await envelope({ op: 'hack' })), ENV, gh.fetch, NOW);
  assert.equal(r.status, 400);
});

test('最多 300 條：第 301 條被拒，但更新既有的仍可', async () => {
  const k = await C.importKey(KEY_B64);
  const rules = Array.from({ length: 300 }, (_, i) => rule({ id: 'x' + i }));
  const gh = fakeGh({ sha: 's1', text: JSON.stringify(await C.encryptJson({ v: 1, rules }, k)) });
  const go = async (r) => C.handleRequest(post(await envelope({ op: 'put', rule: r })), ENV, gh.fetch, NOW);
  assert.equal((await go(rule({ id: 'extra' }))).status, 400);
  assert.equal((await go(rule({ id: 'x5', p: 1 }))).status, 200);
  assert.equal((await stored(gh)).rules.length, 300);
});

test('GitHub 409：重試最多 3 次', async () => {
  let gh = fakeGh(); gh.conflicts = 2;
  assert.equal((await C.handleRequest(post(await envelope({ op: 'put', rule: rule() })), ENV, gh.fetch, NOW)).status, 200);
  assert.equal(gh.bodies.length, 3);                                        // 兩次衝突＋一次成功
  gh = fakeGh(); gh.conflicts = 3;
  const r = await C.handleRequest(post(await envelope({ op: 'put', rule: rule() })), ENV, gh.fetch, NOW);
  assert.equal(r.status, 409); assert.equal(gh.puts.length, 0);
});

test('現有檔解不開（換過密碼）→ 500，不覆蓋', async () => {
  const other = await C.importKey(OTHER_B64);
  const gh = fakeGh({ sha: 's1', text: JSON.stringify(await C.encryptJson({ v: 1, rules: [rule()] }, other)) });
  const before = gh.file.text;
  const r = await C.handleRequest(post(await envelope({ op: 'put', rule: rule({ id: 'z' }) })), ENV, gh.fetch, NOW);
  assert.equal(r.status, 500); assert.equal(gh.file.text, before);
});

test('GET /rules：回傳現有密文；沒檔案回 404', async () => {
  const gh = fakeGh();
  let r = await C.handleRequest(new Request('https://w.example/rules', { headers: { Origin: ENV.ORIGIN } }), ENV, gh.fetch, NOW);
  assert.equal(r.status, 404);
  await C.handleRequest(post(await envelope({ op: 'put', rule: rule() })), ENV, gh.fetch, NOW);
  r = await C.handleRequest(new Request('https://w.example/rules', { headers: { Origin: ENV.ORIGIN } }), ENV, gh.fetch, NOW);
  assert.equal(r.status, 200);
  const d = await C.decryptJson(await r.json(), await C.importKey(KEY_B64));
  assert.equal(d.rules.length, 1);
});

test('CORS：只允許網站網域與 localhost／127.0.0.1', async () => {
  const gh = fakeGh();
  const get = (origin) => C.handleRequest(new Request('https://w.example/rules', { headers: origin ? { Origin: origin } : {} }), ENV, gh.fetch, NOW);
  assert.equal((await get(ENV.ORIGIN)).headers.get('Access-Control-Allow-Origin'), ENV.ORIGIN);
  assert.equal((await get('http://localhost:8123')).headers.get('Access-Control-Allow-Origin'), 'http://localhost:8123');
  assert.equal((await get('http://127.0.0.1:3000')).headers.get('Access-Control-Allow-Origin'), 'http://127.0.0.1:3000');
  for (const o of ['https://evil.example', 'http://localhost.evil.com', 'https://zlo-25.github.io.evil.com', null]) assert.equal((await get(o)).headers.get('Access-Control-Allow-Origin'), null, String(o));
  const pre = await C.handleRequest(new Request('https://w.example/op', { method: 'OPTIONS', headers: { Origin: ENV.ORIGIN } }), ENV, gh.fetch, NOW);
  assert.equal(pre.status, 204);
  assert.match(pre.headers.get('Access-Control-Allow-Methods'), /POST/);
  const bad = await C.handleRequest(new Request('https://w.example/op', { method: 'OPTIONS', headers: { Origin: 'https://evil.example' } }), ENV, gh.fetch, NOW);
  assert.equal(bad.headers.get('Access-Control-Allow-Origin'), null);
});

test('scheduled：叫醒 alerts-daily（ref=main）', async () => {
  const gh = fakeGh();
  assert.equal(await C.dispatchDaily(ENV, gh.fetch), 204);
  assert.deepEqual(gh.dispatched, [{ ref: 'main' }]);
});

test('GitHub 讀取失敗 → 502，不寫', async () => {
  const f = async () => new Response('{}', { status: 500 });
  const r = await C.handleRequest(post(await envelope({ op: 'put', rule: rule() })), ENV, f, NOW);
  assert.equal(r.status, 502);
});

test('交叉相容：Python 端（tools/alerts.py enc）的格式也能解（zlib deflate）', async () => {
  // 以 node 的 zlib.deflateSync 模擬 Python zlib.compress，確認 DecompressionStream('deflate') 讀得懂
  const zlib = await import('node:zlib');
  const k = await C.importKey(KEY_B64), iv = crypto.getRandomValues(new Uint8Array(12));
  const z = zlib.deflateSync(Buffer.from(JSON.stringify({ rules: [{ id: 'q' }] })));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, k, z));
  assert.deepEqual(await C.decryptJson({ iv: C.b64e(iv), ct: C.b64e(ct) }, k), { rules: [{ id: 'q' }] });
});

test('Python（tools/alerts.py）加密的檔案，Worker 解得開；Worker 加密的，Python 解得開', async () => {
  const cp = await import('node:child_process'), path = await import('node:path'), url = await import('node:url');
  const root = path.resolve(path.dirname(url.fileURLToPath(import.meta.url)), '..', '..');
  const k = await C.importKey(KEY_B64);
  const py = (code, input) => cp.spawnSync('python3', ['-c', code], { cwd: root, input, encoding: 'utf8', env: { ...process.env, KEY: KEY_B64 } });
  const a = py('import sys,os,base64,json; sys.path.insert(0,"tools"); import alerts as A; print(json.dumps(A.enc({"rules":[{"id":"中文"}]}, base64.b64decode(os.environ["KEY"]))))');
  assert.equal(a.status, 0, a.stderr);
  assert.deepEqual(await C.decryptJson(JSON.parse(a.stdout), k), { rules: [{ id: '中文' }] });
  const f = await C.encryptJson({ rules: [{ id: 'x', n: '備註' }] }, k);
  const b = py('import sys,os,base64,json; sys.path.insert(0,"tools"); import alerts as A; print(json.dumps(A.dec(json.load(sys.stdin), base64.b64decode(os.environ["KEY"])), ensure_ascii=False))', JSON.stringify(f));
  assert.equal(b.status, 0, b.stderr);
  assert.deepEqual(JSON.parse(b.stdout), { rules: [{ id: 'x', n: '備註' }] });
});
