/* 到價提醒小幫手的核心邏輯（純函式＋注入的 fetch，node --test 可測；alerts.js 只是把它接到 Cloudflare 的入口）。
   安全模型：瀏覽器用「看盤密碼推導的 AES 金鑰」把操作加密送來；Worker 用同一把金鑰（secret ALERT_KEY）解開。
   解得開（AES-GCM 驗證通過）＝本人；再檢查時間戳（±300 秒，擋重送舊封包）與欄位白名單，才改 repo 裡的 data/alerts/rules.enc.json。
   檔案格式與 data/kbar、data/futures 相同：{"iv","ct"}（base64），明文 = zlib(JSON)。 */

export const MAX_RULES = 300;
export const TS_WINDOW_MS = 300000;
export const RULES_PATH = 'data/alerts/rules.enc.json';
export const COMMIT_MSG = '到價提醒設定更新';          // 不含價格與代號（公開 repo 的 commit 紀錄誰都看得到）

export class HttpError extends Error {
  constructor(status, msg) { super(msg); this.status = status; }
}

/* ---------- base64／加解密 ---------- */
export const b64d = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
export const b64e = (u) => { let s = ''; const a = new Uint8Array(u); for (let i = 0; i < a.length; i += 0x8000) s += String.fromCharCode(...a.subarray(i, i + 0x8000)); return btoa(s); };

export async function importKey(b64) {
  return crypto.subtle.importKey('raw', b64d(b64), 'AES-GCM', false, ['encrypt', 'decrypt']);
}
async function pipe(bytes, Stream, kind) {
  const s = new Blob([bytes]).stream().pipeThrough(new Stream(kind));
  return new Uint8Array(await new Response(s).arrayBuffer());
}
export async function decryptJson(file, key) {
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(file.iv) }, key, b64d(file.ct));
  return JSON.parse(new TextDecoder().decode(await pipe(plain, DecompressionStream, 'deflate')));
}
export async function encryptJson(obj, key) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const z = await pipe(new TextEncoder().encode(JSON.stringify(obj)), CompressionStream, 'deflate');
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, z);
  return { v: 1, iv: b64e(iv), ct: b64e(ct) };
}

/* ---------- 規則欄位檢查（白名單；多的欄位直接丟掉，型別或數值不對就拒絕） ---------- */
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const fin = (x) => typeof x === 'number' && Number.isFinite(x);
const str = (x, max) => typeof x === 'string' && [...x].length <= max;
const bad = (m) => { throw new HttpError(400, m); };

export function cleanRule(r) {
  if (!r || typeof r !== 'object' || Array.isArray(r)) bad('提醒格式不對');
  if (!(typeof r.id === 'string' && /^[A-Za-z0-9_-]{1,40}$/.test(r.id))) bad('提醒編號不對');
  if (!(typeof r.code === 'string' && /^[a-z0-9_]{1,40}$/.test(r.code))) bad('標的代號不對');
  if (!['stock', 'etf', 'fut'].includes(r.kind)) bad('標的種類不對');
  if (!(str(r.name, 60) && r.name.length)) bad('名稱不對');
  if (!(fin(r.p) && r.p > 0 && r.p < 1e9)) bad('目標價不對');
  if (!['up', 'down'].includes(r.dir)) bad('方向不對');
  if (typeof r.dirAuto !== 'boolean') bad('方向模式不對');
  if (!['price', 'pct'].includes(r.mode)) bad('價格模式不對');
  if (typeof r.on !== 'boolean') bad('開關不對');
  if (!(r.n == null || str(r.n, 40))) bad('備註太長（最多 40 字）');
  if (!(typeof r.since === 'string' && DATE.test(r.since))) bad('起算日不對');
  const out = { id: r.id, code: r.code, kind: r.kind, name: r.name, p: r.p, dir: r.dir, dirAuto: r.dirAuto, mode: r.mode, n: r.n || '', on: r.on, since: r.since };
  if (r.mode === 'pct') {
    if (!(fin(r.pct) && r.pct > -100 && r.pct <= 1000)) bad('百分比不對');
    out.pct = r.pct;
  }
  if (r.base != null) {
    if (!(r.base && typeof r.base.t === 'string' && DATE.test(r.base.t) && fin(r.base.c) && r.base.c > 0)) bad('基準價不對');
    out.base = { t: r.base.t, c: r.base.c };
  } else if (r.mode === 'pct') bad('百分比提醒需要基準價');
  for (const k of ['created', 'updated', 'offAt']) {
    if (r[k] != null) { if (!str(r[k], 40)) bad('時間欄位不對'); out[k] = r[k]; } else out[k] = null;
  }
  return out;
}

/* ---------- 套用一個操作（回傳新的文件；不改傳入的物件） ---------- */
export function applyOp(doc, op, nowIso) {
  const rules = (doc && doc.rules ? doc.rules : []).slice();
  if (op.op === 'put') {
    const r = cleanRule(op.rule);
    const i = rules.findIndex((x) => x.id === r.id);
    if (i < 0) {
      if (rules.length >= MAX_RULES) throw new HttpError(400, `提醒最多 ${MAX_RULES} 條，請先刪掉一些`);
      rules.push(r);
    } else { r.created = rules[i].created || r.created; rules[i] = r; }
  } else if (op.op === 'del') {
    if (!(typeof op.id === 'string' && op.id)) bad('提醒編號不對');
    const i = rules.findIndex((x) => x.id === op.id);
    if (i >= 0) rules.splice(i, 1);
  } else if (op.op === 'delOff') {
    for (let i = rules.length - 1; i >= 0; i--) if (!rules[i].on) rules.splice(i, 1);
  } else bad('不認得的操作');
  return { v: 1, rules, updated: nowIso };
}

/* 驗證並解開瀏覽器送來的操作。解不開＝金鑰不對（401）；時間戳超過 ±300 秒＝401（可能是重送的舊封包或手機時間差太多） */
export async function parseOp(bodyText, key, nowMs) {
  let file;
  try { file = JSON.parse(bodyText); if (!file || typeof file.iv !== 'string' || typeof file.ct !== 'string') throw 0; } catch (e) { throw new HttpError(400, '封包格式不對'); }
  let op;
  try { op = await decryptJson(file, key); } catch (e) { throw new HttpError(401, '金鑰不對（可能換過看盤密碼，請重新解鎖）'); }
  if (!op || !fin(op.ts) || Math.abs(nowMs - op.ts) > TS_WINDOW_MS) throw new HttpError(401, '時間不對（手機或電腦時鐘差超過 5 分鐘），請校正時間後再試');
  return op;
}

/* ---------- GitHub Contents API ---------- */
const GH = 'https://api.github.com';
const ghHeaders = (env) => ({ Authorization: `Bearer ${env.GH_TOKEN}`, Accept: 'application/vnd.github+json', 'User-Agent': 'erd-alerts-worker', 'X-GitHub-Api-Version': '2022-11-28' });

export async function ghReadRules(env, f) {
  const r = await f(`${GH}/repos/${env.REPO}/contents/${RULES_PATH}?ref=main`, { headers: ghHeaders(env) });
  if (r.status === 404) return null;
  if (!r.ok) throw new HttpError(502, `讀取設定失敗（GitHub ${r.status}）`);
  const j = await r.json();
  return { sha: j.sha, text: new TextDecoder().decode(b64d(String(j.content).replace(/\n/g, ''))) };
}
export async function ghWriteRules(env, f, file, sha) {
  const body = { message: COMMIT_MSG, content: b64e(new TextEncoder().encode(JSON.stringify(file))), branch: 'main' };
  if (sha) body.sha = sha;
  const r = await f(`${GH}/repos/${env.REPO}/contents/${RULES_PATH}`, { method: 'PUT', headers: { ...ghHeaders(env), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (r.status === 409 || r.status === 422) return 'conflict';          // sha 對不上＝剛好有人同時寫
  if (!r.ok) throw new HttpError(502, `寫入設定失敗（GitHub ${r.status}）`);
  return 'ok';
}

/* 讀 → 套用 → 加密 → 寫；sha 衝突重試最多 3 次 */
export async function commitOp(env, f, key, op, nowMs) {
  for (let i = 0; i < 3; i++) {
    const cur = await ghReadRules(env, f);
    let doc = { v: 1, rules: [] };
    if (cur) { try { doc = await decryptJson(JSON.parse(cur.text), key); } catch (e) { throw new HttpError(500, '現有的提醒檔解不開（密碼換過？請重新部署小幫手）'); } }
    const next = applyOp(doc, op, new Date(nowMs).toISOString());
    const res = await ghWriteRules(env, f, await encryptJson(next, key), cur && cur.sha);
    if (res === 'ok') return next.rules.length;
  }
  throw new HttpError(409, '同時有別的變更，請再試一次');
}

/* ---------- CORS ---------- */
export function corsHeaders(origin, env) {
  const okLocal = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin || '');
  const allow = origin && (origin === env.ORIGIN || okLocal) ? origin : null;
  const h = { Vary: 'Origin' };
  if (allow) Object.assign(h, { 'Access-Control-Allow-Origin': allow, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '600' });
  return h;
}

/* ---------- 入口 ---------- */
const json = (obj, status, extra) => new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra } });

export async function handleRequest(request, env, f = fetch, nowMs = Date.now()) {
  const url = new URL(request.url), cors = corsHeaders(request.headers.get('Origin'), env);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
  try {
    if (url.pathname === '/rules' && request.method === 'GET') {
      // 直接讀 GitHub（不經過 Pages 部署延遲）；檔案本身是密文，任何人拿到也解不開，所以不需要驗證
      const cur = await ghReadRules(env, f);
      return cur ? new Response(cur.text, { status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...cors } }) : json({ empty: true }, 404, cors);
    }
    if (url.pathname === '/op' && request.method === 'POST') {
      const text = await request.text();
      if (text.length > 20000) throw new HttpError(413, '封包太大');
      const key = await importKey(env.ALERT_KEY);
      const op = await parseOp(text, key, nowMs);
      const n = await commitOp(env, f, key, op, nowMs);
      return json({ ok: true, n }, 200, cors);
    }
    return json({ ok: false, error: '找不到' }, 404, cors);
  } catch (e) {
    if (e instanceof HttpError) return json({ ok: false, error: e.message }, e.status, cors);
    console.log('未預期的錯誤', e && e.name);                 // 不印內容（可能含密文以外的東西）
    return json({ ok: false, error: '小幫手內部錯誤' }, 500, cors);
  }
}

/* 每天台北 08:00：叫醒 alerts-daily（workflow_dispatch 幾乎立刻執行）。失敗只留 log，GitHub 備援排程會補 */
export async function dispatchDaily(env, f = fetch) {
  const r = await f(`${GH}/repos/${env.REPO}/actions/workflows/alerts-daily.yml/dispatches`, {
    method: 'POST', headers: { ...ghHeaders(env), 'Content-Type': 'application/json' }, body: JSON.stringify({ ref: 'main' }),
  });
  if (!(r.status === 204 || r.ok)) console.log(`叫醒 alerts-daily 失敗（GitHub ${r.status}）`);
  return r.status;
}
