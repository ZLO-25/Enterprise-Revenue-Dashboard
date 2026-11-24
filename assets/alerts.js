/* 到價提醒（ALERTS）：K 棒圖上的鈴鐺線、「到價提醒」頁、紅色提醒條。
   資料：data/alerts/rules.enc.json（提醒規則；只有 Cloudflare Worker 寫）、state.enc.json（到價紀錄；只有 GitHub Actions 的 tools/alerts.py 寫）、
         config.json（{"worker": 小幫手網址 | null}；null＝小幫手還沒設好，前端停用新增）。
   加密：與 data/kbar、data/futures 相同（AES-256-GCM，明文 = zlib(JSON)）；金鑰就是「看盤密碼」解鎖後存在這台裝置 localStorage 的那一把，所以只有解鎖過的裝置看得到提醒。
   寫入：瀏覽器把操作 {ts, op, rule|id} 用同一把金鑰加密 → POST 小幫手 /op → 小幫手驗證後改 repo。畫面先改（樂觀更新），失敗就還原並跳提示。
   到價判斷（hitFor）與 tools/alerts.py 的 hit_for 是同一套規則，兩邊跑同一份案例 tools/tests/alerts_cases.json：
     K 棒日期 > since 的第一根，dir=up：最高價 ≥ 目標；dir=down：最低價 ≤ 目標。缺最高／最低價的 K 棒略過。
   本檔不依賴 futures.js／kbar.js 才能載入（首頁只載本檔做提醒條）；畫線與解鎖表單用到 FUT 時才檢查它存在。 */
const ALERTS = (() => {
  const KEY_LS = 'erd-futures-key-v1', DISMISS_SS = 'erd-alerts-dismissed';
  const SOP = 'https://claude.ai/artifact/4DYc81V319Gu9scHSMvS72';
  const FUTS = ['ym', 'nq', 'tx'];
  const FUT_NAMES = { ym: '小道瓊', nq: '小那指', tx: '大台指' };
  const FUT_DP = { ym: 0, nq: 2, tx: 0 };
  let C = { base: 'data/alerts/', kbar: 'data/kbar/', fut: 'data/futures/', link: 'alerts/', watch: 'futures/' };
  const hasFUT = () => typeof FUT !== 'undefined';
  const S = { dp: {}, loaded: false, loading: null, locked: true, worker: null, cfg: null, err: '', rules: [], state: null, bars: {}, names: {}, items: [], barsP: {}, subs: new Set(), memo: new Map() };

  /* ---------- 小工具（不依賴其他檔） ---------- */
  const ls = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { } } };
  const ss = { get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { } } };
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const ub64 = (u) => { let s = ''; const a = new Uint8Array(u); for (let i = 0; i < a.length; i += 0x8000) s += String.fromCharCode(...a.subarray(i, i + 0x8000)); return btoa(s); };
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const fin = (x) => typeof x === 'number' && Number.isFinite(x);
  const fmt = (n, dp = 2) => n == null || !fin(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  const sgn = (n, dp = 1) => n == null || !fin(n) ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(dp) + '%';
  const mdd = (t) => t ? t.slice(5).replace('-', '/') : '';
  const dstr = (t) => t ? t.replace(/-/g, '/') : '';
  const kindOf = (code) => FUTS.includes(code) ? 'fut' : /^etf_/.test(code) ? 'etf' : 'stock';
  const dpOf = (code) => S.dp[code] ?? (FUTS.includes(code) ? FUT_DP[code] : ((S.items.find((i) => i.code === code) || {}).dp ?? 2));
  const nameOf = (code) => S.names[code] || FUT_NAMES[code] || code.toUpperCase();
  const newId = () => 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const getJSON = async (url) => { const r = await fetch(url, { cache: 'no-cache' }); if (!r.ok) { const e = new Error(url + ' ' + r.status); e.status = r.status; throw e; } return r.json(); };
  const emit = () => { S.memo.clear(); S.subs.forEach((f) => { try { f(); } catch (e) { console.error(e); } }); };
  const token = (n, fb) => { try { return (typeof T === 'function' ? T(n) : getComputedStyle(document.documentElement).getPropertyValue(n).trim()) || fb; } catch (e) { return fb; } };

  /* ---------- 到價判斷（與 tools/alerts.py 同一套） ---------- */
  function hitFor(rule, bars) {
    const since = rule.since || '', p = rule.p;
    if (!fin(p)) return null;
    const up = rule.dir === 'up';
    for (const b of bars || []) {
      if (b[0] <= since) continue;
      const v = up ? b[2] : b[3];
      if (!fin(v)) continue;
      if (up ? v >= p : v <= p) return { t: b[0], px: v, side: up ? 'h' : 'l', p };
    }
    return null;
  }
  /* state 裡的到價紀錄是否仍有效：改價、重新開啟（since 往後）、改方向都會作廢；已關閉的不算 */
  function hitValid(rule, hit) {
    if (!hit || !rule.on) return false;
    return (hit.t || '') > (rule.since || '') && hit.p === rule.p && hit.side === (rule.dir === 'up' ? 'h' : 'l');
  }
  const dirFor = (p, last) => p >= last ? 'up' : 'down';
  const pctPrice = (base, pct) => Math.round(base * (1 + pct / 100) * 1e4) / 1e4;

  function hitOf(r) {
    if (!r.on) return null;
    const st = S.state && S.state.hits && S.state.hits[r.id];
    if (st && hitValid(r, st)) return st;
    const bars = S.bars[r.code];
    if (!bars) return null;
    const k = [r.id, r.p, r.dir, r.since, bars.length, bars.length ? bars[bars.length - 1][0] : ''].join('|');
    if (!S.memo.has(k)) S.memo.set(k, hitFor(r, bars));
    return S.memo.get(k);
  }
  const statusOf = (r) => !r.on ? 'off' : hitOf(r) ? 'hit' : 'on';
  const lastOf = (code) => {
    const b = S.bars[code];
    if (b && b.length) { const x = b[b.length - 1]; return { t: x[0], c: x[4] }; }
    const l = S.state && S.state.last && S.state.last[code];
    return l ? { t: l.t, c: l.c } : null;
  };

  /* ---------- 加解密 ---------- */
  let keyRaw = null, keyObj = null;
  async function getKey() {
    const raw = ls.get(KEY_LS);
    if (!raw) { keyRaw = keyObj = null; return null; }
    if (raw !== keyRaw) { keyObj = await crypto.subtle.importKey('raw', b64(raw), 'AES-GCM', false, ['encrypt', 'decrypt']); keyRaw = raw; }
    return keyObj;
  }
  async function pipe(bytes, Stream) { return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new Stream('deflate'))).arrayBuffer()); }
  async function decryptJson(file, key) {
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(file.iv) }, key, b64(file.ct));
    return JSON.parse(new TextDecoder().decode(await pipe(plain, DecompressionStream)));
  }
  async function encryptJson(obj, key) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const z = await pipe(new TextEncoder().encode(JSON.stringify(obj)), CompressionStream);
    return { v: 1, iv: ub64(iv), ct: ub64(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, z)) };
  }

  /* ---------- 載入 ---------- */
  function init(o) { C = Object.assign({}, C, o || {}); }
  function setItems(items) { S.items = items || []; (items || []).forEach((i) => { if (i.name) S.names[i.code] = i.name; }); }
  function setNames(m) { Object.assign(S.names, m || {}); }
  const hasKey = () => !!ls.get(KEY_LS);

  function load(force) {
    // 先前沒解鎖、現在有金鑰了（在頁面上輸入密碼解鎖）→ 重新載入
    if (S.loading && !force && !(S.locked && S.loaded && hasKey())) return S.loading;
    S.loading = (async () => {
      S.err = '';
      try { S.cfg = await getJSON(C.base + 'config.json'); } catch (e) { S.cfg = { worker: null }; }
      S.worker = S.cfg && S.cfg.worker ? String(S.cfg.worker).replace(/\/+$/, '') : null;
      const key = await getKey();
      S.locked = !key;
      if (!key) { S.rules = []; S.state = null; S.loaded = true; emit(); return; }
      let file = null, from = '';
      if (S.worker) {
        try {
          const r = await fetch(S.worker + '/rules', { cache: 'no-store' });
          if (r.ok) { file = await r.json(); from = 'worker'; } else if (r.status === 404) { file = null; from = 'worker'; } else throw new Error('worker ' + r.status);
        } catch (e) { file = undefined; }
      }
      if (file === undefined || !S.worker) {                               // 小幫手讀不到：退回 Pages 上的檔（可能慢幾分鐘）
        try { file = await getJSON(C.base + 'rules.enc.json'); } catch (e) { file = null; }
      }
      S.fromWorker = from === 'worker';
      try { S.rules = file ? ((await decryptJson(file, key)).rules || []) : []; }
      catch (e) { S.rules = []; S.err = '提醒檔解不開（看盤密碼可能換過，請到小幫手重新部署）'; }
      try { const sf = await getJSON(C.base + 'state.enc.json'); S.state = await decryptJson(sf, key); } catch (e) { S.state = null; }
      S.loaded = true; emit();
    })().catch((e) => { S.err = '讀取失敗：' + (e && e.message || e); S.loaded = true; emit(); });
    return S.loading;
  }

  /* 某一檔的近期 K 棒（本檔自己解密，不依賴 kbar.js）；讀進來就拿去即時判斷到價 */
  function loadBars(code) {
    if (S.bars[code]) return Promise.resolve(S.bars[code]);
    if (S.barsP[code]) return S.barsP[code];
    S.barsP[code] = (async () => {
      const key = await getKey(); if (!key) return null;
      try {
        const f = await getJSON((kindOf(code) === 'fut' ? C.fut : C.kbar) + code + '.enc.json');
        const d = await decryptJson(f, key);
        feedBars(code, d.bars); return d.bars;
      } catch (e) { return null; }
    })();
    return S.barsP[code];
  }
  function feedBars(code, bars) {
    const old = S.bars[code];
    if (old && old.length === bars.length && old[old.length - 1][0] === bars[bars.length - 1][0] && old[old.length - 1][2] === bars[bars.length - 1][2]) return;
    S.bars[code] = bars; emit();
  }
  /* 還沒有到價紀錄的啟用中提醒：讀 K 棒即時判斷（同時最多 4 檔，上限 60 檔） */
  async function ensureLive() {
    await load();
    const codes = [...new Set(S.rules.filter((r) => r.on && !(S.state && S.state.hits && S.state.hits[r.id])).map((r) => r.code))].filter((c) => !S.bars[c]).slice(0, 60);
    const q = codes.slice();
    await Promise.all([0, 1, 2, 3].map(async () => { while (q.length) await loadBars(q.shift()); }));
  }

  /* ---------- 寫入（樂觀更新） ---------- */
  let chain = Promise.resolve();
  async function post(op) {
    if (!S.worker) throw new Error('小幫手還沒設定');
    const key = await getKey(); if (!key) throw new Error('還沒解鎖');
    const body = JSON.stringify(await encryptJson(Object.assign({ ts: Date.now() }, op), key));
    let r, j = null;
    try { r = await fetch(S.worker + '/op', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body }); } catch (e) { throw new Error('連不上小幫手（網路問題？）'); }
    try { j = await r.json(); } catch (e) { /* 非 JSON */ }
    if (!r.ok || !j || !j.ok) throw new Error((j && j.error) || ('小幫手回應 ' + r.status));
  }
  const send = (op) => { const p = chain.then(() => post(op)); chain = p.catch(() => { }); return p; };
  const canEdit = () => !S.locked && !!S.worker;
  function blocked() {
    if (S.locked) toast('還沒解鎖：請先輸入看盤密碼');
    else if (!S.worker) toast('還沒設定：到價提醒小幫手還沒部署，設定方法在「到價提醒」頁', { label: '前往', href: C.link });
    return !canEdit();
  }

  async function put(rule) {
    if (blocked()) return false;
    const prev = S.rules.find((r) => r.id === rule.id), now = new Date().toISOString();
    const next = Object.assign({}, rule, { updated: now, created: rule.created || now });
    S.rules = prev ? S.rules.map((r) => r.id === rule.id ? next : r) : S.rules.concat(next); emit();
    try { await send({ op: 'put', rule: next }); return true; }
    catch (e) {
      S.rules = prev ? S.rules.map((r) => r.id === rule.id ? prev : r) : S.rules.filter((r) => r.id !== rule.id); emit();
      toast(`沒存到：${e.message}，已還原`); return false;
    }
  }
  async function del(id, quiet) {
    if (blocked()) return false;
    const i = S.rules.findIndex((r) => r.id === id); if (i < 0) return true;
    const gone = S.rules[i];
    S.rules = S.rules.filter((r) => r.id !== id); emit();
    try { await send({ op: 'del', id }); if (!quiet) toast(`已刪除「${gone.name}」的提醒`, { label: '復原', fn: () => put(gone) }); return true; }
    catch (e) { S.rules.splice(Math.min(i, S.rules.length), 0, gone); emit(); toast(`沒刪掉：${e.message}，已還原`); return false; }
  }
  async function delOff() {
    if (blocked()) return false;
    const gone = S.rules.filter((r) => !r.on); if (!gone.length) return true;
    S.rules = S.rules.filter((r) => r.on); emit();
    try { await send({ op: 'delOff' }); toast(`已刪除 ${gone.length} 條已關閉的提醒`); return true; }
    catch (e) { S.rules = S.rules.concat(gone); emit(); toast(`沒刪掉：${e.message}，已還原`); return false; }
  }

  /* ---------- 建立與修改規則（純函式，頁面與圖上共用） ---------- */
  /* item：{code,name,kind}；last：{t,c}（最新一根 K 棒的日期與收盤）；o：{mode:'price'|'pct', p | pct, dir:'auto'|'up'|'down', n, snap?} */
  function makeRule(item, last, o) {
    const snap = o.snap || ((x) => Math.round(x * 100) / 100);
    const pct = o.mode === 'pct';
    const p = pct ? snap(pctPrice(last.c, o.pct)) : o.p;
    const dirAuto = !o.dir || o.dir === 'auto';
    const r = { id: newId(), code: item.code, kind: item.kind || kindOf(item.code), name: item.name, p, dir: dirAuto ? dirFor(p, last.c) : o.dir, dirAuto,
      mode: pct ? 'pct' : 'price', n: (o.n || '').slice(0, 40), on: true, since: last.t, base: { t: last.t, c: last.c }, offAt: null };
    if (pct) r.pct = o.pct;
    return r;
  }
  /* 改價（拖曳、改 % 或編輯）：方向自動時重算；起算日重設成最新 K 棒，舊的到價作廢 */
  function repriced(r, p, last, snap) {
    const x = Object.assign({}, r, { p, since: last.t });
    if (x.dirAuto) x.dir = dirFor(p, last.c);
    if (x.mode === 'pct') { x.base = x.base || { t: last.t, c: last.c }; x.pct = Math.round((p / x.base.c - 1) * 1e4) / 100; }
    return x;
  }
  const setOn = (r, on, last) => on ? Object.assign({}, r, { on: true, offAt: null, since: last ? last.t : r.since, dir: r.dirAuto && last ? dirFor(r.p, last.c) : r.dir }) : Object.assign({}, r, { on: false, offAt: new Date().toISOString() });
  const get = (code) => S.rules.filter((r) => r.code === code);
  const all = () => S.rules.slice();
  const on = (f) => { S.subs.add(f); return () => S.subs.delete(f); };

  /* 文字：方向、目標價、距最新收盤 */
  const dirWord = (r) => r.dir === 'up' ? '漲破' : '跌破';
  const labelOf = (r, st) => st === 'hit' ? '🔔 已到價' : st === 'off' ? '已關閉' : r.mode === 'pct' ? `🔔 ${sgn(r.pct, Math.abs(r.pct) % 1 ? 1 : 0)}` : `🔔 ${dirWord(r)}`;
  const distOf = (r) => { const l = lastOf(r.code); return l ? (r.p / l.c - 1) * 100 : null; };

  /* ---------- 樣式（只在用到時加進頁面；全部用 theme.css 的 token，淺色深色都看得清楚） ---------- */
  const CSS = `
:root{--al-red:#b3261e;--al-red-bg:#fdecea;--al-orange:#b85a00;--al-orange-bg:#fff1e3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--al-red:#e66767;--al-red-bg:#3a1d1d;--al-orange:#f0a35e;--al-orange-bg:#3a2a18}}
:root[data-theme="dark"]{--al-red:#e66767;--al-red-bg:#3a1d1d;--al-orange:#f0a35e;--al-orange-bg:#3a2a18}
.al-tool{font:inherit;font-size:.86rem;font-weight:700;color:var(--al-orange);background:var(--al-orange-bg);border:1px solid var(--al-orange)!important;border-radius:8px;padding:6px 14px;cursor:pointer;min-height:34px}
.seg .al-tool{border-radius:0;border-width:0 0 0 1px!important;border-color:var(--al-orange)!important}
.al-tool:hover{filter:brightness(.96)}.al-tool[aria-pressed="true"]{background:var(--al-orange);color:#fff;outline:2px solid var(--al-orange);outline-offset:1px}
.al-tool[aria-disabled="true"]{opacity:.65}
.seg .al-tool[aria-pressed="false"]{background:var(--al-orange-bg)!important;color:var(--al-orange)!important}
.seg .al-tool[aria-pressed="true"]{background:var(--al-orange)!important;color:#fff!important}
@media (max-width:640px){.al-tool,.seg .al-tool{min-height:40px}}
.al-drawing{cursor:crosshair}.al-onl{cursor:ns-resize}
.al-tb{position:absolute;left:8px;z-index:6;display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;padding:6px 8px;background:var(--surface);border:1px solid var(--line);border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.2);max-width:calc(100% - 16px);box-sizing:border-box}
.al-tb[hidden]{display:none}
.al-tb .al-tt{font-size:.86rem;color:var(--ink)}.al-tb .al-tt small{color:var(--muted)}
.al-tb .seg button{padding:5px 10px;font-size:.8rem}
.al-tb input.al-note{font:inherit;font-size:.85rem;width:150px;max-width:100%;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--page);color:var(--ink);box-sizing:border-box}
.al-tb label.al-pct{display:inline-flex;align-items:center;gap:4px;font-size:.85rem;color:var(--ink-2)}
.al-tb label.al-pct input{width:64px;font:inherit;font-size:.85rem;padding:5px 6px;border:1px solid var(--line);border-radius:6px;background:var(--page);color:var(--ink)}
.al-b{font:inherit;font-size:.82rem;color:var(--ink-2);background:transparent;border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box}
.al-b:hover{color:var(--ink);border-color:var(--axis)}.al-b.del{color:var(--bad-text)}.al-b.pri{background:var(--chip-bg);color:var(--chip-ink);border-color:transparent;font-weight:600}
@media (max-width:640px){.al-tb{left:6px;right:6px}.al-tb input.al-note{flex:1 1 140px;width:auto;min-height:40px}.al-b,.al-tb .seg button{min-height:40px}.al-tb label.al-pct input{min-height:40px}}
.al-badge{display:inline-flex;align-items:center;justify-content:center;margin-left:4px;padding:0 6px;border-radius:999px;background:var(--al-red);color:#fff;font-size:.72rem;font-weight:700;line-height:1.5}
.al-dot{display:inline-flex;align-items:center;gap:4px;margin-left:10px;padding:1px 8px;border-radius:999px;background:var(--al-red);color:#fff;font-size:.78rem;font-weight:700}
.al-dot::before{content:"";width:7px;height:7px;border-radius:50%;background:#fff}
.al-codelist{margin-top:10px}.al-codelist h3{font-size:.95rem;margin:0 0 6px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline}.al-codelist h3 a{font-size:.85rem;font-weight:500}
.al-banner{position:sticky;top:calc(env(safe-area-inset-top,0px) + 56px);z-index:30;display:flex;align-items:center;gap:10px;margin:0 0 -20px;padding:10px 14px;background:var(--al-red);color:#fff;border-radius:10px;font-size:.95rem;font-weight:600;box-sizing:border-box}
.al-banner[hidden]{display:none}.al-banner a{color:#fff;text-decoration:underline;white-space:nowrap}.al-banner .t{flex:1;min-width:0;overflow-wrap:anywhere}
.al-banner button{flex:none;font:inherit;color:#fff;background:rgba(255,255,255,.18);border:0;border-radius:8px;min-width:40px;min-height:40px;cursor:pointer;font-size:1rem}
@media (max-width:640px){.al-banner{font-size:.88rem;padding:8px 10px}}
.al-toasts{position:fixed;left:0;right:0;bottom:16px;z-index:99998;display:flex;flex-direction:column;align-items:center;gap:8px;pointer-events:none;padding:0 16px}
.al-toast{pointer-events:auto;display:flex;align-items:center;gap:12px;max-width:520px;min-height:44px;padding:8px 14px;background:var(--ink);color:var(--page);border-radius:10px;font-size:.9rem;box-shadow:0 4px 16px rgba(0,0,0,.3)}
.al-toast button,.al-toast a{font:inherit;font-weight:700;color:var(--page);background:transparent;border:1px solid currentColor;border-radius:6px;min-height:36px;padding:2px 12px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;white-space:nowrap}
/* 提醒頁與清單 */
.al-st{display:flex;flex-wrap:wrap;gap:6px 18px;padding:10px 14px;border:1px solid var(--line);border-radius:10px;background:var(--surface);font-size:.9rem;margin:0 0 14px}
.al-st b{color:var(--ink)}.al-st .bad{color:var(--bad-text);font-weight:600}.al-st .ok{color:var(--good-text);font-weight:600}
.al-add{border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:14px 16px;margin:0 0 16px}
.al-add h2{margin:0 0 10px;font-size:1.05rem}.al-form{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));align-items:start}
.al-form label,.al-f{display:flex;flex-direction:column;gap:4px;font-size:.84rem;color:var(--ink-2);min-width:0}
.al-form input,.al-form select,.al-ed input{font:inherit;font-size:.95rem;padding:8px 10px;min-height:42px;border:1px solid var(--line);border-radius:8px;background:var(--page);color:var(--ink);box-sizing:border-box;width:100%}
.al-form .seg button{min-height:42px;font-size:.9rem;padding:6px 14px}
.al-form .go{font:inherit;font-weight:700;min-height:44px;border:0;border-radius:8px;background:var(--accent);color:#fff;padding:8px 20px;cursor:pointer}
.al-form .go:disabled{opacity:.5;cursor:default}.al-hint{font-size:.82rem;color:var(--muted);margin:4px 0 0}
.al-grp{border:1px solid var(--line);border-radius:12px;background:var(--surface);margin:0 0 14px;overflow:hidden}
.al-grp>summary{cursor:pointer;padding:12px 16px;font-weight:700;font-size:1rem;display:flex;align-items:center;gap:10px;min-height:44px;box-sizing:border-box}
.al-grp>summary .n{font-weight:600;font-size:.82rem;color:var(--muted)}.al-grp.hit>summary{background:var(--al-red-bg);color:var(--al-red)}.al-grp.off>summary{color:var(--muted)}
.al-grp .al-gh{display:flex;justify-content:flex-end;padding:6px 16px 0}
.al-empty{padding:14px 16px;color:var(--muted);font-size:.9rem}
.al-r{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1.2fr) auto;gap:8px 16px;align-items:center;padding:12px 16px;border-top:1px solid var(--line)}
.al-r.hit{border-left:4px solid var(--al-red)}.al-r.on{border-left:4px solid var(--al-orange)}.al-r.off{border-left:4px solid var(--axis);color:var(--muted)}
.al-r .nm{font-weight:700;font-size:1rem}.al-r .nm a{color:inherit;text-decoration:none}.al-r .nm a:hover{text-decoration:underline}
.al-tag{display:inline-block;margin-left:6px;padding:0 8px;border-radius:999px;font-size:.76rem;font-weight:700;background:var(--chip-bg);color:var(--chip-ink)}
.al-r.hit .al-tag{background:var(--al-red);color:#fff}.al-r.on .al-tag{background:var(--al-orange-bg);color:var(--al-orange)}
.al-r .sub{font-size:.84rem;color:var(--ink-2);margin-top:2px;overflow-wrap:anywhere}.al-r .sub small{color:var(--muted)}.al-r.off .sub{color:var(--muted)}
.al-r .px{font-size:.9rem;font-variant-numeric:tabular-nums}.al-r .px small{color:var(--muted)}.al-r .gap{font-weight:700}
.al-r .act{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
.al-ed{grid-column:1/-1;display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));padding:10px;background:var(--page);border-radius:8px;align-items:end}
@media (max-width:720px){
  .al-r{grid-template-columns:1fr;gap:6px;padding:12px 14px}.al-r .act{justify-content:flex-start}.al-r .act .al-b{flex:1 1 auto;min-height:40px}
  .al-form{grid-template-columns:1fr}.al-st{font-size:.86rem}
}`;
  function css() {
    if (document.getElementById('al-css')) return;
    const s = document.createElement('style'); s.id = 'al-css'; s.textContent = CSS; (document.head || document.documentElement).appendChild(s);
  }

  /* ---------- 提示（toast） ---------- */
  function toast(msg, act, ms) {
    css();
    let box = document.querySelector('.al-toasts');
    if (!box) { box = document.createElement('div'); box.className = 'al-toasts'; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
    const t = document.createElement('div'); t.className = 'al-toast';
    t.innerHTML = `<span>${esc(msg)}</span>` + (act ? (act.href ? `<a href="${esc(act.href)}">${esc(act.label)}</a>` : `<button type="button">${esc(act.label)}</button>`) : '');
    const kill = () => { clearTimeout(tm); t.remove(); };
    if (act && act.fn) t.querySelector('button').addEventListener('click', () => { kill(); act.fn(); });
    box.appendChild(t);
    const tm = setTimeout(kill, ms || (act ? 6000 : 4500));
    return kill;
  }

  /* ---------- 工具列按鈕（和「水平線」並排） ---------- */
  const tool = { armed: false, subs: new Set() };
  function arm(v) { tool.armed = v; tool.subs.forEach((f) => f(v)); if (v && hasFUT() && FUT.arm) FUT.arm(false); }
  const BELL = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true" style="width:15px;height:15px;vertical-align:-2px;margin-right:4px"><path d="M8 2.2a3.8 3.8 0 0 0-3.8 3.8v2.4L2.8 11h10.4l-1.4-2.6V6A3.8 3.8 0 0 0 8 2.2z"/><path d="M6.5 13a1.6 1.6 0 0 0 3 0"/></svg>';
  function btn() { css(); return `<button type="button" class="al-tool" aria-pressed="false" title="到價提醒：按一下再點圖上的價位放提醒線（快速鍵 Alt+A：在游標位置放）；到價時會通知你">${BELL}<span class="al-tl">提醒</span></button>`; }
  function wire(root) {
    css();
    const sync = (v) => root.querySelectorAll('.al-tool').forEach((b) => { b.setAttribute('aria-pressed', String(v)); const l = b.querySelector('.al-tl'); if (l) l.textContent = v ? '點圖放提醒…' : '提醒'; });
    tool.subs.add(sync); sync(tool.armed);
    root.addEventListener('click', (e) => {
      const b = e.target.closest('.al-tool'); if (!b) return;
      if (tool.armed) { arm(false); return; }
      load().then(() => { if (!blocked()) arm(true); });
    });
    if (hasFUT() && FUT.tool && !FUT.tool._al) { FUT.tool._al = true; FUT.tool.subs.add((v) => { if (v && tool.armed) arm(false); }); }
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && tool.armed) arm(false); });
    load();
  }

  /* ---------- K 棒圖上的鈴鐺線 ---------- */
  /* chart／candle：lightweight-charts；box：圖的容器；d：K 棒資料（d.bars 是日 K）；q：價格小數位；rdOnly：唯讀（總覽牆小圖，只畫線＋角落徽章） */
  function attach(chart, candle, box, d, q, rdOnly) {
    if (!hasFUT()) return;
    css();
    if (box._alOff) box._alOff();
    const code = d.code, name = nameOf(code) === code.toUpperCase() && d.name ? d.name : nameOf(code);
    const step = d.kind === 'stock' ? 0.01 : (FUT.dp(d) ? 0.25 : 1), snap = (p) => Math.round(p / step) * step;
    const lb = d.bars[d.bars.length - 1], last = { t: lb[0], c: lb[4] };
    const pls = new Map(), minePrices = () => [...pls.values()].map((pl) => pl.options().price);
    const prevIsLine = candle._isLine;
    candle._isLine = (v) => (prevIsLine && prevIsLine(v)) || minePrices().some((p) => Math.abs(p - v) < 1e-9);   // 軸標籤用商品原本位數
    let sel = null, hover = null, drag = null, lastY = null, raf = 0;
    feedBarsQuiet(code, d.bars); S.dp[code] = q;
    const opt = (r, price) => {
      const st = statusOf(r), col = token(st === 'hit' ? '--neg' : st === 'off' ? '--tick' : '--s2', st === 'hit' ? '#e34948' : st === 'off' ? '#898781' : '#eb6834');
      const on_ = r.id === sel || r.id === hover;
      return { price, color: col, lineWidth: st === 'hit' ? 3 : on_ ? 2 : 1, lineStyle: st === 'hit' ? 0 : st === 'off' ? 1 : 2, axisLabelVisible: true, axisLabelColor: col, axisLabelTextColor: '#ffffff',
        title: (drag && drag.id === r.id ? `🔔 ${sgn((price / last.c - 1) * 100)}` : labelOf(r, st)) + (r.n && !(drag && drag.id === r.id) ? ' ' + r.n : '') };
    };
    function sync() {
      const now = get(code), ids = new Set(now.map((r) => r.id));
      pls.forEach((pl, id) => { if (!ids.has(id)) { candle.removePriceLine(pl); pls.delete(id); } });
      now.forEach((r) => { if (drag && drag.id === r.id) return; pls.has(r.id) ? pls.get(r.id).applyOptions(opt(r, r.p)) : pls.set(r.id, candle.createPriceLine(opt(r, r.p))); });
      if (sel && !ids.has(sel)) sel = null;
      badge(); if (!rdOnly) { bar(); list(); }
    }
    function badge() {   // 總覽牆卡片角落的小徽章
      const head = box.closest('.kb-card') && box.closest('.kb-card').querySelector('.kb-ch'); if (!head) return;
      const has = get(code).some((r) => statusOf(r) === 'hit'), b = head.querySelector('.al-badge');
      if (has && !b) head.insertAdjacentHTML('beforeend', '<span class="al-badge" title="這檔有提醒已到價">🔔</span>');
      else if (!has && b) b.remove();
    }
    if (rdOnly) {
      const off = on(sync);
      box._alOff = () => { off(); box._alOff = null; };
      box._alDbg = { lines: () => pls.size };
      load().then(sync); sync(); return;
    }

    /* 圖下方「這檔的提醒」清單 */
    const host = box.parentElement && box.parentElement.querySelector('.fut-lines');
    let lst = null;
    if (host) { lst = host.nextElementSibling && host.nextElementSibling.classList.contains('al-codelist') ? host.nextElementSibling : null; if (!lst) { lst = document.createElement('div'); lst.className = 'al-codelist'; host.after(lst); } }
    function list() {
      if (!lst) return;
      const L = get(code).slice().sort((a, b) => b.p - a.p);
      lst.innerHTML = `<h3>${esc(name)}的提醒（${L.length} 條）<a href="${esc(C.link)}">全部提醒 →</a></h3>` + (L.length ? L.map((r) => rowHTML(r, { compact: true })).join('') : `<p class="fut-note">還沒有提醒。按上面橘色的「🔔 提醒」，再點圖上想要的價位；到價時會通知你。${S.worker ? '' : '（小幫手還沒設定，暫時不能新增。）'}</p>`);
    }
    if (lst) lst.onclick = (e) => rowClick(e, last);

    /* 選取時浮出的小工具列 */
    const tb = document.createElement('div'); tb.className = 'al-tb'; tb.hidden = true; tb.setAttribute('role', 'toolbar'); tb.setAttribute('aria-label', '提醒設定'); box.appendChild(tb);
    let tbSig = '';
    function bar() {
      const r = sel && get(code).find((x) => x.id === sel);
      if (!r) { tb.hidden = true; tbSig = ''; return; }
      const sig = [r.id, r.mode, r.dir, r.dirAuto, r.on, r.p, statusOf(r), r.pct, r.n].join('|');
      if (tbSig === sig && !tb.hidden) { place(); return; }
      const st = statusOf(r), dist = (r.p / last.c - 1) * 100, dd = r.dirAuto ? 'auto' : r.dir;
      tb.innerHTML = `<span class="al-tt">${labelOf(r, st).replace('已關閉', '🔕 已關閉')} <b>${fmt(r.p, q)}</b> <small>距最新收盤 ${sgn(dist)}</small></span>` +
        `<span class="seg" data-g="dir" role="group" aria-label="方向">${[['auto', '自動'], ['up', '漲破'], ['down', '跌破']].map(([v, l]) => `<button type="button" data-dir="${v}" aria-pressed="${dd === v}">${l}</button>`).join('')}</span>` +
        `<span class="seg" data-g="mode" role="group" aria-label="價格或百分比">${[['price', '價格'], ['pct', '％']].map(([v, l]) => `<button type="button" data-mode="${v}" aria-pressed="${r.mode === v}">${l}</button>`).join('')}</span>` +
        (r.mode === 'pct' ? `<label class="al-pct">距收盤 <input type="number" inputmode="decimal" step="0.1" value="${r.pct}" aria-label="百分比">%</label>` : '') +
        `<input class="al-note" maxlength="40" placeholder="備註（最多 40 字）" aria-label="備註" value="${esc(r.n || '')}">` +
        `<button type="button" class="al-b" data-act="toggle">${r.on ? '關閉提醒' : '重新開啟'}</button><button type="button" class="al-b del" data-act="del">刪除</button><button type="button" class="al-b" data-act="x" aria-label="收起">✕</button>`;
      tbSig = sig;
      tb.hidden = false; place();
    }
    function place() {
      const r = sel && get(code).find((x) => x.id === sel); if (!r) return;
      const y = candle.priceToCoordinate(drag && drag.id === sel ? drag.p : r.p), h = chart.panes()[0].getHeight();
      if (y == null || y < 0 || y > h) { tb.style.visibility = 'hidden'; return; }
      tb.style.visibility = '';
      const narrow = box.clientWidth < 640;
      tb.style.top = narrow ? Math.max(2, Math.min(h - tb.offsetHeight - 2, y > h / 2 ? 4 : h - tb.offsetHeight - 4)) + 'px' : Math.max(2, Math.min(h - tb.offsetHeight - 2, y - tb.offsetHeight - 8)) + 'px';
    }
    const follow = () => { if (!sel || raf) return; raf = requestAnimationFrame(() => { raf = 0; place(); }); };
    chart.timeScale().subscribeVisibleLogicalRangeChange(follow);
    box.addEventListener('wheel', follow, { passive: true });
    const ro = new ResizeObserver(follow); ro.observe(box);
    const cur = () => get(code).find((x) => x.id === sel);
    tb.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b || !sel) return; const r = cur(); if (!r) return;
      if (b.dataset.dir) {
        const v = b.dataset.dir, x = Object.assign({}, r, { dirAuto: v === 'auto', dir: v === 'auto' ? dirFor(r.p, last.c) : v, since: last.t });
        put(x);
      } else if (b.dataset.mode) {
        if (b.dataset.mode === r.mode) return;
        put(b.dataset.mode === 'pct' ? Object.assign({}, r, { mode: 'pct', base: { t: last.t, c: last.c }, pct: Math.round((r.p / last.c - 1) * 1e4) / 100 })
          : (() => { const x = Object.assign({}, r, { mode: 'price' }); delete x.pct; return x; })());
      } else if (b.dataset.act === 'toggle') put(setOn(r, !r.on, last));
      else if (b.dataset.act === 'del') { const id = sel; sel = null; del(id); }
      else if (b.dataset.act === 'x') { sel = null; sync(); }
    });
    tb.addEventListener('change', (e) => {
      const r = cur(); if (!r) return;
      if (e.target.classList.contains('al-note')) put(Object.assign({}, r, { n: e.target.value.trim().slice(0, 40) }));
      else if (e.target.closest('.al-pct')) { const v = parseFloat(e.target.value); if (fin(v) && v > -100 && v <= 1000) put(repriced(Object.assign({}, r, { base: r.base || { t: last.t, c: last.c } }), snap(pctPrice((r.base || last).c, v)), last)); else toast('百分比要介於 −99.99 到 1000'); }
    });
    tb.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.target.blur(); });

    /* 滑鼠／手指位置 → 是哪一條鈴鐺線 */
    const rel = (e) => { const r = box.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    const inMain = (pt) => pt.y >= 0 && pt.y <= chart.panes()[0].getHeight();
    function hit(pt, touch) {
      if (!inMain(pt)) return null; let best = null, bd = touch ? 16 : 7;
      get(code).forEach((r) => { const y = candle.priceToCoordinate(r.p); if (y != null && Math.abs(y - pt.y) <= bd) { bd = Math.abs(y - pt.y); best = r; } });
      return best;
    }
    const setHover = (id) => { if (id === hover) return; hover = id; box.classList.toggle('al-onl', !!id); sync(); };
    function create(price) {
      if (blocked()) return;
      const r = makeRule({ code, name, kind: kindOf(code) }, last, { mode: 'price', p: Math.round(price * 1e4) / 1e4, dir: 'auto' });
      sel = r.id; put(r);
    }
    const onDown = (e) => {
      if (e.button > 0 || tb.contains(e.target)) return;
      const pt = rel(e), touch = e.pointerType === 'touch';
      if (tool.armed && inMain(pt)) {
        const p = candle.coordinateToPrice(pt.y); if (p == null) return;
        e.stopPropagation(); e.preventDefault(); arm(false); create(snap(p)); return;
      }
      const r = hit(pt, touch);
      if (!r) { if (sel) { sel = null; sync(); } return; }
      e.stopPropagation(); e.preventDefault();
      drag = { id: r.id, p: r.p, y0: pt.y, moved: false, pid: e.pointerId }; box.setPointerCapture(e.pointerId);
      sel = r.id; sync();
    };
    const onMove = (e) => {
      const pt = rel(e); lastY = inMain(pt) ? pt.y : null;
      if (e.buttons) follow();
      if (!drag) { if (e.pointerType !== 'touch') setHover(tool.armed ? null : (hit(pt) || {}).id || null); return; }
      if (!drag.moved && Math.abs(pt.y - drag.y0) < 3) return;
      const p = candle.coordinateToPrice(Math.max(0, Math.min(chart.panes()[0].getHeight(), pt.y))); if (p == null) return;
      drag.moved = true; drag.p = snap(p);
      const r = cur(); if (r && pls.get(drag.id)) { pls.get(drag.id).applyOptions(opt(r, drag.p)); tb.querySelector('.al-tt') && (tb.querySelector('.al-tt').innerHTML = `🔔 <b>${fmt(drag.p, q)}</b> <small>距最新收盤 ${sgn((drag.p / last.c - 1) * 100)}</small>`); place(); }
      e.stopPropagation();
    };
    const onUp = () => {
      if (!drag) return; const g = drag; drag = null;
      try { box.releasePointerCapture(g.pid); } catch (x) { }
      const r = get(code).find((x) => x.id === g.id);
      if (g.moved && r && g.p !== r.p) put(repriced(r, g.p, last)); else sync();
    };
    const onLeave = () => { lastY = null; if (!drag) setHover(null); };
    const swallow = (e) => { if (drag || (tool.armed && e.type !== 'touchmove')) { e.stopPropagation(); if (e.cancelable && e.type === 'touchmove') e.preventDefault(); } };
    const onKey = (e) => {
      if (/INPUT|TEXTAREA|SELECT/.test((e.target.tagName || ''))) return;
      if (sel && (e.key === 'Delete' || e.key === 'Backspace')) { e.preventDefault(); const id = sel; sel = null; del(id); }
      else if (sel && e.key === 'Escape') { sel = null; sync(); }
      else if (e.altKey && (e.key === 'a' || e.key === 'A' || e.code === 'KeyA') && lastY != null) { const p = candle.coordinateToPrice(lastY); if (p != null) { e.preventDefault(); create(snap(p)); } }
    };
    const onArm = (v) => box.classList.toggle('al-drawing', v);
    box.addEventListener('pointerdown', onDown, true); box.addEventListener('pointermove', onMove, true);
    box.addEventListener('pointerup', onUp, true); box.addEventListener('pointercancel', onUp, true); box.addEventListener('pointerleave', onLeave);
    ['mousedown', 'touchstart', 'touchmove'].forEach((t) => box.addEventListener(t, swallow, { capture: true, passive: false }));
    document.addEventListener('keydown', onKey); tool.subs.add(onArm); onArm(tool.armed);
    const offSub = on(sync);
    box._alOff = () => {
      box.removeEventListener('pointerdown', onDown, true); box.removeEventListener('pointermove', onMove, true);
      box.removeEventListener('pointerup', onUp, true); box.removeEventListener('pointercancel', onUp, true); box.removeEventListener('pointerleave', onLeave);
      ['mousedown', 'touchstart', 'touchmove'].forEach((t) => box.removeEventListener(t, swallow, { capture: true }));
      document.removeEventListener('keydown', onKey); tool.subs.delete(onArm); offSub(); cancelAnimationFrame(raf); ro.disconnect(); box.removeEventListener('wheel', follow); tb.remove();
      box.classList.remove('al-drawing', 'al-onl'); box._alOff = null;
    };
    box._alDbg = { y: (id) => candle.priceToCoordinate((get(code).find((x) => x.id === id) || {}).p), sel: () => sel, lines: () => pls.size };   // 瀏覽器測試用：線的位置與目前選取
    load().then(sync); sync();
  }
  function feedBarsQuiet(code, bars) { S.bars[code] = bars; S.memo.clear(); }

  /* ---------- 一條提醒的清單列（提醒頁與圖下方共用） ---------- */
  function rowHTML(r, o) {
    o = o || {};
    const st = statusOf(r), h = hitOf(r), l = lastOf(r.code), dp = dpOf(r.code), dist = distOf(r);
    const tg = fmt(r.p, dp) + (r.mode === 'pct' && r.base ? ` <small>（${sgn(r.pct, Math.abs(r.pct) % 1 ? 1 : 0)}，基準 ${fmt(r.base.c, dp)}，${mdd(r.base.t)}）</small>` : '');
    const tag = st === 'off' ? '已關閉' : dirWord(r) + (r.dirAuto ? '' : '（手動）');
    const nm = o.compact ? `<span class="nm">${esc(r.name)}</span>` : `<span class="nm"><a href="${esc(C.watch)}?s=${esc(r.code)}" title="在圖上看">${esc(r.name)}</a></span>`;
    const hitLine = h ? `<div class="sub">到價 ${dstr(h.t)}，當天${h.side === 'h' ? '最高' : '最低'} <b>${fmt(h.px, dp)}</b></div>` : '';
    const px = l ? `最新收盤 <b>${fmt(l.c, dp)}</b> <small>${mdd(l.t)}</small><br><span class="gap" style="color:${st === 'hit' ? 'var(--al-red)' : 'inherit'}">${st === 'hit' ? '距目標 ' : '還差 '}${sgn(dist, 2)}</span> <small>（價差 ${fmt(Math.abs(r.p - l.c), dp)}）</small>` : '<small>最新收盤：讀不到（K 棒檔不存在或還沒解鎖）</small>';
    const view = `<a class="al-b" href="${esc(C.watch)}?s=${esc(r.code)}">在圖上看</a>`;
    const act = st === 'hit' ? `<button type="button" class="al-b pri" data-a="toggle" data-id="${esc(r.id)}">關閉提醒</button>${o.compact ? '' : view}<button type="button" class="al-b del" data-a="del" data-id="${esc(r.id)}">刪除</button>`
      : st === 'on' ? `${o.compact ? '' : `<button type="button" class="al-b" data-a="edit" data-id="${esc(r.id)}">編輯</button>`}<button type="button" class="al-b" data-a="toggle" data-id="${esc(r.id)}">關閉</button><button type="button" class="al-b del" data-a="del" data-id="${esc(r.id)}">刪除</button>${o.compact ? '' : view}`
        : `<button type="button" class="al-b pri" data-a="toggle" data-id="${esc(r.id)}">重新開啟</button><button type="button" class="al-b del" data-a="del" data-id="${esc(r.id)}">刪除</button>`;
    const ed = S.edit && S.edit.id === r.id && !o.compact ? editHTML(r) : '';
    return `<div class="al-r ${st}" data-id="${esc(r.id)}"><div class="main">${nm}<span class="al-tag">${tag}</span><div class="sub">目標 <b>${tg}</b></div>${hitLine}${r.n ? `<div class="sub">備註：${esc(r.n)}</div>` : ''}</div><div class="px">${px}</div><div class="act">${act}</div>${ed}</div>`;
  }
  function editHTML(r) {
    const e = S.edit;
    return `<div class="al-ed"><div class="al-f"><span>方式</span><span class="seg" role="group" aria-label="方式"><button type="button" data-em="price" aria-pressed="${e.mode === 'price'}">價格</button><button type="button" data-em="pct" aria-pressed="${e.mode === 'pct'}">％</button></span></div>
      <label class="al-f"><span>${e.mode === 'pct' ? '距最新收盤 %' : '目標價'}</span><input data-ev="v" type="number" inputmode="decimal" step="any" value="${esc(e.v)}"></label>
      <div class="al-f"><span>方向</span><span class="seg" role="group" aria-label="方向">${[['auto', '自動'], ['up', '漲破'], ['down', '跌破']].map(([v, l]) => `<button type="button" data-ed="${v}" aria-pressed="${e.dir === v}">${l}</button>`).join('')}</span></div>
      <label class="al-f"><span>備註</span><input data-ev="n" type="text" maxlength="40" value="${esc(e.n)}"></label>
      <div class="al-f"><span>&nbsp;</span><span style="display:flex;gap:6px"><button type="button" class="al-b pri" data-a="save" data-id="${esc(r.id)}" style="min-height:42px;flex:1">儲存</button><button type="button" class="al-b" data-a="cancel" style="min-height:42px;flex:1">取消</button></span></div></div>`;
  }
  /* 清單列上的按鈕（事件委派）；last：這一檔最新 K 棒（圖下方的清單知道；提醒頁用 lastOf） */
  function rowClick(e, lastArg, rerender) {
    const b = e.target.closest('button[data-a]'); if (!b) return;
    const r = S.rules.find((x) => x.id === b.dataset.id), a = b.dataset.a; if (!r && a !== 'cancel') return;
    const last = lastArg || (r && lastOf(r.code));
    if (a === 'toggle') put(setOn(r, !r.on, last));
    else if (a === 'del') del(r.id);
    else if (a === 'edit') { S.edit = { id: r.id, mode: r.mode, v: r.mode === 'pct' ? r.pct : r.p, dir: r.dirAuto ? 'auto' : r.dir, n: r.n || '' }; rerender && rerender(); }
    else if (a === 'cancel') { S.edit = null; rerender && rerender(); }
    else if (a === 'save') {
      const ed = S.edit, v = parseFloat(ed.v);
      if (!fin(v) || (ed.mode === 'price' ? v <= 0 : !(v > -100 && v <= 1000))) { toast(ed.mode === 'price' ? '目標價要大於 0' : '百分比要介於 −99.99 到 1000'); return; }
      const snapP = (x) => Math.round(x * 100) / 100;
      let x = Object.assign({}, r, { mode: ed.mode, dirAuto: ed.dir === 'auto', n: ed.n.trim().slice(0, 40) });
      if (ed.mode === 'pct') { x.base = (r.mode === 'pct' && r.base) ? r.base : (last ? { t: last.t, c: last.c } : r.base); x.pct = v; x.p = snapP(pctPrice(x.base.c, v)); } else { x.p = v; delete x.pct; }
      x.dir = ed.dir === 'auto' ? (last ? dirFor(x.p, last.c) : x.dir) : ed.dir;
      if (last) x.since = last.t;
      S.edit = null; put(x); rerender && rerender();
    }
  }

  /* ---------- 紅色提醒條（首頁、看盤頁、提醒頁） ---------- */
  const hitRules = () => S.rules.filter((r) => r.on && hitOf(r));
  let bannerEl = null;
  function banner() {
    if (bannerEl) return; css();
    bannerEl = document.createElement('div'); bannerEl.className = 'al-banner'; bannerEl.hidden = true; bannerEl.setAttribute('role', 'alert');
    const host = document.querySelector('main') || document.body; host.insertBefore(bannerEl, host.firstChild);
    const upd = () => {
      const hs = hitRules();
      const codes = [...new Set(hs.map((r) => r.code))], sig = codes.slice().sort().join(',');
      if (S.locked || !hs.length || ss.get(DISMISS_SS) === sig) { bannerEl.hidden = true; return; }
      const names = [...new Set(hs.map((r) => r.name))];
      bannerEl.innerHTML = `<span aria-hidden="true">🔔</span><span class="t">${codes.length} 檔已到價：${esc(names.slice(0, 6).join('、'))}${names.length > 6 ? `…等 ${names.length} 檔` : ''}</span><a href="${esc(C.link)}#hit">查看並關閉 →</a><button type="button" aria-label="暫時收起">✕</button>`;
      bannerEl.querySelector('button').onclick = () => { ss.set(DISMISS_SS, sig); bannerEl.hidden = true; };
      bannerEl.hidden = false;
    };
    on(upd); load().then(() => { upd(); ensureLive(); });
  }
  /* 個股頁 K 棒區塊標題列：這檔有到價中提醒 → 紅點＋「已到價」 */
  function mark(code, el) {
    if (!el || !hasKey()) return; css();
    const upd = () => {
      const has = !S.locked && get(code).some((r) => statusOf(r) === 'hit'), d = el.querySelector('.al-dot');
      if (has && !d) el.insertAdjacentHTML('beforeend', '<span class="al-dot" title="這檔有提醒已到價">已到價</span>');
      else if (!has && d) d.remove();
    };
    on(upd); load().then(() => { upd(); loadBars(code).then(upd); });
  }

  /* ---------- 「到價提醒」頁 ---------- */
  function page(root, o) {
    css(); o = o || {};
    setItems(o.items || []);
    const $ = (s) => root.querySelector(s);
    const st = { type: 'price', dir: 'auto', item: null, last: null, seq: 0 };
    S.open = S.open || { hit: true, on: true, off: false };
    S.edit = null;
    function statusBar() {
      const b = $('#alStatus'); if (!b) return;
      const w = S.worker ? (S.locked ? '<span>解鎖後才會連線</span>' : S.fromWorker ? '<span class="ok">✓ 已連線</span>' : S.loaded ? '<span class="bad">讀不到小幫手，改讀網站上的檔案（可能慢幾分鐘）</span>' : '<span>連線中…</span>')
        : `<span class="bad">還沒設定</span>（<a href="${SOP}" target="_blank" rel="noopener">設定步驟</a>；設好之前不能新增或修改）`;
      const sent = S.state && S.state.sent && S.state.sent[S.state.sent.length - 1];
      b.innerHTML = `<span>到價小幫手：<b>${w}</b></span>` +
        `<span>通知管道：<b>${sent ? esc(sent.ch.join('、')) : '尚無紀錄'}</b>${sent ? '' : '（每天台北 08:00 會發到你設定好的管道）'}</span>` +
        `<span>最近一次通知：<b>${sent ? dstr(sent.d) : '—'}</b></span>` +
        (S.state && S.state.asOf ? `<span>到價判斷更新：<b>${esc(S.state.asOf.replace('T', ' ').slice(0, 16))} UTC</b></span>` : '') +
        (S.err ? `<span class="bad">${esc(S.err)}</span>` : '');
    }
    const grp = (key, title, arr, extra) => `<details class="al-grp ${key}"${key === 'hit' ? ' id="hit"' : ''} data-k="${key}"${S.open[key] ? ' open' : ''}><summary>${title}<span class="n">${arr.length} 條</span></summary>${extra || ''}` +
      (arr.length ? arr.map((r) => rowHTML(r)).join('') : `<div class="al-empty">${key === 'hit' ? '目前沒有已到價的提醒。' : key === 'on' ? '還沒有監控中的提醒。用上面的表單新增，或在看盤頁的圖上按「🔔 提醒」再點價位。' : '沒有已關閉的提醒。'}</div>`) + '</details>';
    function lists() {
      const box = $('#alLists'); if (!box) return;
      const rs = S.rules, h = rs.filter((r) => statusOf(r) === 'hit').sort((a, b) => hitOf(b).t.localeCompare(hitOf(a).t));
      const on_ = rs.filter((r) => statusOf(r) === 'on').sort((a, b) => Math.abs(distOf(a) ?? 1e9) - Math.abs(distOf(b) ?? 1e9));
      const off = rs.filter((r) => statusOf(r) === 'off').sort((a, b) => (b.offAt || '').localeCompare(a.offAt || ''));
      if (!S.rules.length && S.loaded && !S.err) {
        box.innerHTML = `<div class="al-grp"><div class="al-empty"><b>還沒有任何提醒。</b><br>兩種設法：① 用上面的表單選標的、填價格或百分比；② 到<a href="${esc(C.watch)}">看盤頁</a>打開一檔的 K 棒，按橘色的「🔔 提醒」再點圖上的價位（也可以拖曳調整）。<br>到價（當天最高價或最低價碰到）後，每天台北 08:00 會通知你，直到你按「關閉提醒」。</div></div>`;
        return;
      }
      box.innerHTML = grp('hit', '🔔 已到價', h) + grp('on', '監控中（離目標最近的在前）', on_) + grp('off', '已關閉', off, off.length ? '<div class="al-gh"><button type="button" class="al-b del" data-a="deloff">全部刪除已關閉（' + off.length + '）</button></div>' : '');
    }
    function render() { statusBar(); if (S.locked) { const b = $('#alLists'); if (b) b.innerHTML = ''; } else lists(); const L = $('#alLock'), B = $('#alBody'); if (L && B) { B.hidden = S.locked; L.hidden = !S.locked; } formState(); }
    /* 表單 */
    function pickList() {
      const sel = $('#alPick'), q = ($('#alFind').value || '').trim().toLowerCase();
      const groups = [['公司', (i) => i.kind === 'stock'], ['ETF', (i) => i.kind === 'etf'], ['期貨', (i) => i.kind === 'fut']];
      sel.innerHTML = '<option value="">選擇標的…</option>' + groups.map(([t, f]) => { const arr = S.items.filter((i) => f(i) && (!q || (i.name + ' ' + i.ticker + ' ' + i.code).toLowerCase().includes(q))); return arr.length ? `<optgroup label="${t}">${arr.map((i) => `<option value="${esc(i.code)}"${st.item && st.item.code === i.code ? ' selected' : ''}>${esc(i.name)}　${esc(i.ticker)}</option>`).join('')}</optgroup>` : ''; }).join('');
    }
    async function pickItem(code) {
      st.item = S.items.find((i) => i.code === code) || null; st.last = null; const my = ++st.seq;
      const info = $('#alLast');
      if (!st.item) { info.textContent = ''; formState(); return; }
      info.textContent = '讀取最新收盤…';
      await loadBars(code);
      if (my !== st.seq) return;
      st.last = lastOf(code);
      info.innerHTML = st.last ? `最新收盤 <b>${fmt(st.last.c, dpOf(code))}</b>（${dstr(st.last.t)}）` : '<span style="color:var(--bad-text)">讀不到這檔的最新收盤（K 棒檔不存在），不能新增。</span>';
      formState();
    }
    function formState() {
      const f = $('#alForm'); if (!f) return;
      f.querySelectorAll('[data-t]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.t === st.type)));
      f.querySelectorAll('[data-d]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.d === st.dir)));
      $('#alVL').textContent = st.type === 'pct' ? '距最新收盤 %（例如 −10）' : '目標價';
      const v = parseFloat($('#alVal').value), pv = $('#alPrev');
      if (st.last && fin(v)) {
        const p = st.type === 'pct' ? pctPrice(st.last.c, v) : v;
        if (st.type === 'pct' && !(v > -100 && v <= 1000)) pv.textContent = '';
        else { const dir = st.dir === 'auto' ? dirFor(p, st.last.c) : st.dir; pv.textContent = `→ ${dir === 'up' ? '漲破' : '跌破'} ${fmt(Math.round(p * 100) / 100, dpOf(st.item.code))}（距最新收盤 ${sgn((p / st.last.c - 1) * 100, 2)}）`; }
      } else pv.textContent = '';
      const can = !!(st.item && st.last && canEdit());
      $('#alAdd').disabled = !can;
      $('#alAdd').title = S.worker ? (can ? '' : '先選標的') : '還沒設定：到價小幫手還沒部署';
      $('#alHint').innerHTML = S.worker ? '' : `還沒設定小幫手，暫時不能新增（<a href="${SOP}" target="_blank" rel="noopener">設定步驟</a>）。`;
    }
    $('#alFind').addEventListener('input', pickList);
    $('#alPick').addEventListener('change', (e) => pickItem(e.target.value));
    $('#alForm').addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; if (b.dataset.t) { st.type = b.dataset.t; formState(); } else if (b.dataset.d) { st.dir = b.dataset.d; formState(); } });
    $('#alVal').addEventListener('input', formState);
    $('#alForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!st.item || !st.last) return;
      const v = parseFloat($('#alVal').value);
      if (!fin(v) || (st.type === 'price' ? v <= 0 : !(v > -100 && v <= 1000 && v !== 0))) { toast(st.type === 'price' ? '目標價要大於 0' : '百分比要介於 −99.99 到 1000（不含 0）'); return; }
      const r = makeRule(st.item, st.last, { mode: st.type, p: v, pct: v, dir: st.dir, n: $('#alNote').value.trim() });
      if (await put(r)) { toast(`已新增：${st.item.name} ${dirWord(r)} ${fmt(r.p, dpOf(r.code))}`); $('#alVal').value = ''; $('#alNote').value = ''; formState(); }
    });
    const lr = () => { lists(); };
    root.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-a]'); if (!b) return;
      if (b.dataset.a === 'deloff') { const n = S.rules.filter((r) => !r.on).length; if (n && confirm(`確定刪除全部 ${n} 條已關閉的提醒？`)) delOff(); return; }
      rowClick(e, null, lr);
    });
    root.addEventListener('click', (e) => {
      const em = e.target.closest('[data-em]'), ed = e.target.closest('[data-ed]');
      if (em && S.edit) { S.edit.mode = em.dataset.em; const r = S.rules.find((x) => x.id === S.edit.id); S.edit.v = S.edit.mode === 'pct' ? (r.mode === 'pct' ? r.pct : (lastOf(r.code) ? Math.round((r.p / lastOf(r.code).c - 1) * 1e4) / 100 : '')) : r.p; lists(); }
      if (ed && S.edit) { S.edit.dir = ed.dataset.ed; lists(); }
    });
    root.addEventListener('input', (e) => { const i = e.target.closest('[data-ev]'); if (i && S.edit) S.edit[i.dataset.ev] = i.value; });
    root.addEventListener('toggle', (e) => { const d = e.target.closest && e.target.closest('details.al-grp'); if (d) S.open[d.dataset.k] = d.open; }, true);
    on(() => { render(); });
    const go = async () => {
      statusBar();
      await load();
      if (S.locked) { if (hasFUT()) FUT.lockForm($('#alLock'), C.fut, () => { S.loading = null; S.loaded = false; load(true).then(() => { ensureLive(); }); }); }
      render(); pickList();
      const q = new URLSearchParams(location.search).get('add'); if (q && S.items.some((i) => i.code === q)) { $('#alPick').value = q; pickItem(q); }
      await ensureLive(); render();
      if (location.hash === '#hit') { const h = document.getElementById('hit'); if (h && h.scrollIntoView) h.scrollIntoView(); }
    };
    banner();
    go();
  }

  /* 其他頁用：沒有 ERD_ALERTS 設定就不自動啟動 */
  function auto() {
    const c = window.ERD_ALERTS; if (!c) return;
    init(c);
    if (c.banner && hasKey()) banner();
  }
  if (typeof document !== 'undefined' && document.readyState === 'loading') document.addEventListener('DOMContentLoaded', auto); else if (typeof document !== 'undefined') auto();

  return { init, load, loadBars, feedBars, setItems, setNames, get, all, on, put, del, delOff, makeRule, repriced, setOn, hitFor, hitValid, dirFor, pctPrice, hitOf, statusOf, lastOf,
    attach, btn, wire, banner, mark, page, toast, ensureLive, rowHTML, hasKey, _S: S };
})();
