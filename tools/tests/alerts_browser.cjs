/* 到價提醒的瀏覽器測試（CI 用；合成資料＋真的 Worker 核心 worker/core.js＋假的 GitHub，不碰 repo 的 data/）。
   用法（先 python3 tools/build.py）：node tools/tests/alerts_browser.cjs [--shots <資料夾>]
   流程：tools/tests/kbar_fixture.py 產生合成 K 棒，tools/tests/alerts_fixture.py 產生合成提醒並用 tools/alerts.py 真的判斷到價（state.enc.json）；
   本機伺服器：網站檔案取自 repo；/data/futures、/data/kbar、/data/alerts 取自臨時資料夾；/worker/* 交給 worker/core.js（GitHub 是記憶體裡的假檔案）。
   檢查：鈴鐺線（監控中／已到價／已關閉）、放線、方向自動、價格↔％、關閉／重新開啟、刪除與復原、拖曳、儲存失敗還原、
         提醒頁新增 ETF 提醒／編輯／全部刪除已關閉、紅色提醒條與暫時收起、個股頁紅點、小幫手沒設定時的狀態、
         手機 390px 不水平捲動且按鈕 ≥ 40px、淺色深色、沒有 JS 錯誤。 */
const http = require('http'), fs = require('fs'), path = require('path'), os = require('os'), cp = require('child_process'), { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const shotsDir = process.argv.includes('--shots') ? process.argv[process.argv.indexOf('--shots') + 1] : null;
const IGNORE = ['Failed to load resource', 'net::ERR', 'fonts.googleapis', 'fonts.gstatic'];
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'alerts-fx-'));
const py = (script) => { const o = cp.spawnSync('python3', [path.join(ROOT, 'tools', 'tests', script), tmp], { encoding: 'utf8' }); if (o.status !== 0) { console.error(o.stdout, o.stderr); process.exit(2); } return JSON.parse(o.stdout.trim().split('\n').pop()); };
const FX = py('kbar_fixture.py'), AF = py('alerts_fixture.py');

let C = null, ALERT_KEY = null;   // worker/core.js（動態 import）
const mode = { worker: true, failPut: false };
const gh = { file: null, sha: 1, puts: [] };
const fakeFetch = async (url, o = {}) => {
  const m = o.method || 'GET';
  if (m === 'GET') return gh.file ? new Response(JSON.stringify({ sha: gh.file.sha, content: C.b64e(new TextEncoder().encode(gh.file.text)) }), { status: 200 }) : new Response('{}', { status: 404 });
  const b = JSON.parse(o.body);
  if (gh.file && b.sha !== gh.file.sha) return new Response('{}', { status: 409 });
  gh.file = { sha: 's' + (++gh.sha), text: new TextDecoder().decode(C.b64d(b.content)) }; gh.puts.push(b);
  return new Response('{}', { status: 200 });
};
const ghRules = async () => (await C.decryptJson(JSON.parse(gh.file.text), await C.importKey(ALERT_KEY))).rules;
const byId = async (id) => (await ghRules()).find((r) => r.id === id);

let baseUrl = '';
const server = http.createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p.startsWith('/worker/')) {
    const chunks = []; for await (const c of req) chunks.push(c);
    const body = Buffer.concat(chunks);
    const origin = req.headers.origin ? { Origin: req.headers.origin } : {};
    if (mode.failPut && req.method === 'POST') { res.writeHead(500, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ ok: false, error: '測試用的失敗' })); return; }
    const r = await C.handleRequest(new Request('http://worker.test' + p.slice(7), { method: req.method, headers: origin, body: req.method === 'POST' ? body : undefined }),
      { REPO: 'o/r', ORIGIN: baseUrl, ALERT_KEY, GH_TOKEN: 't' }, fakeFetch);
    res.writeHead(r.status, Object.fromEntries(r.headers)); res.end(Buffer.from(await r.arrayBuffer())); return;
  }
  if (p === '/data/alerts/config.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ worker: mode.worker ? baseUrl + '/worker' : null })); return; }
  if (p === '/data/alerts/rules.enc.json') { res.writeHead(404); res.end('not found'); return; }
  if (p.endsWith('/')) p += 'index.html';
  const base = /^\/data\/(futures|kbar|alerts)\//.test(p) ? tmp : ROOT;
  const f = path.normalize(path.join(base, p));
  if (!f.startsWith(base) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); res.end('not found'); return; }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});

let bad = 0;
const ok = (cond, msg) => { if (!cond) { bad++; console.log('  ✗', msg); } };
const say = (m) => console.log(m);
const until = (page, fn, arg, ms) => page.waitForFunction(fn, arg, { timeout: ms || 10000 }).then(() => true, () => false);
const poll = async (fn, ms) => { const t = Date.now(); while (Date.now() - t < (ms || 8000)) { try { if (await fn()) return true; } catch (e) { /* 還沒好 */ } await new Promise((r) => setTimeout(r, 60)); } return false; };
const frames = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
function watchErrors(page, errs) {
  page.on('pageerror', (e) => errs.push('例外：' + e));
  page.on('console', (m) => { if (m.type() === 'error' && !IGNORE.some((x) => m.text().includes(x))) errs.push('console.error：' + m.text()); });
}
const BANNER = '合成測試資料（不是真實行情，也不是真實提醒）';
async function shot(page, name, o) {
  if (!shotsDir) return;
  fs.mkdirSync(shotsDir, { recursive: true });
  await page.mouse.move(0, 0);
  await page.evaluate((t) => { if (document.getElementById('fxBanner')) return; const d = document.createElement('div'); d.id = 'fxBanner'; d.textContent = t; d.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#b00020;color:#fff;font:600 12px sans-serif;padding:3px 8px;text-align:center;pointer-events:none'; document.body.appendChild(d); }, BANNER);
  await page.waitForTimeout(400);
  await page.screenshot(Object.assign({ path: path.join(shotsDir, name) }, o || {}));
  say('  截圖 ' + name);
}
async function unlock(page, sel) {
  await page.waitForSelector((sel || '') + ' form.fut-lock');
  await page.fill((sel || '') + ' form.fut-lock input[type=password]', FX.password);
  await page.click((sel || '') + ' form.fut-lock button.go');
}
const newCtx = (browser, w, scheme) => browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, deviceScaleFactor: 1, colorScheme: scheme || 'light', hasTouch: w <= 600 });
const chartBox = async (page) => { await page.evaluate(() => document.getElementById('futChart').scrollIntoView({ block: 'start', behavior: 'instant' })); await frames(page); return chartBox0(page); };
const chartBox0 = (page) => page.evaluate(() => { document.getElementById('futChart').scrollIntoView({ block: 'start', behavior: 'instant' }); const r = document.getElementById('futChart').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
async function openWatch(page, code) {
  await page.goto(baseUrl + `/futures/?s=${code}&p=D`, { waitUntil: 'load' });
  await page.waitForSelector('#futBody:not([hidden]) #futChart canvas, #futLock form.fut-lock', { timeout: 20000 });
}
const bigBtn = (page, sel) => page.evaluate((s) => [...document.querySelectorAll(s)].filter((e) => e.offsetParent).map((e) => Math.round(e.getBoundingClientRect().height)), sel);

/* ---------- 1. 沒解鎖、小幫手還沒設定 ---------- */
async function lockedAndUnset(browser) {
  say('— 沒解鎖／小幫手沒設定');
  const errs = [], ctx = await newCtx(browser, 1280); const page = await ctx.newPage(); watchErrors(page, errs);
  await page.goto(baseUrl + '/', { waitUntil: 'load' }); await page.waitForTimeout(600);
  ok(!(await page.$('.al-banner:not([hidden])')), '沒解鎖：首頁沒有提醒條');
  await page.goto(baseUrl + '/alerts/', { waitUntil: 'load' });
  await page.waitForSelector('#alLock form.fut-lock');
  ok(!(await page.$('.al-r')) && (await page.isHidden('#alBody')), '沒解鎖：提醒頁只有解鎖表單，不顯示任何提醒');
  ok(await page.evaluate(() => document.getElementById('alLists').innerText.trim() === '' ), '沒解鎖：清單是空的');
  mode.worker = false;
  await unlock(page, '#alLock');
  await page.waitForSelector('#alBody:not([hidden])');
  await until(page, () => document.getElementById('alStatus').textContent.includes('還沒設定'));
  ok((await page.textContent('#alStatus')).includes('還沒設定'), '小幫手沒設定：狀態列寫「還沒設定」');
  ok(await page.evaluate(() => document.getElementById('alAdd').disabled), '小幫手沒設定：新增按鈕停用');
  ok((await page.textContent('#alHint')).includes('還沒設定'), '小幫手沒設定：表單下方有說明');
  await openWatch(page, 'nvda');
  await frames(page);
  await page.click('.al-tool');
  ok(await until(page, () => document.querySelector('.al-toast') && document.querySelector('.al-toast').textContent.includes('還沒設定')), '小幫手沒設定：按鈴鐺跳「還沒設定」提示');
  ok(await page.evaluate(() => !document.querySelector('.al-tool[aria-pressed="true"]')), '小幫手沒設定：不會進入放線狀態');
  mode.worker = true;
  ok(errs.length === 0, '第 1 段錯誤：' + errs.join(' | '));
  await ctx.close();
}

/* ---------- 2. 看盤頁：鈴鐺線 ---------- */
async function watchFlow(browser) {
  say('— 看盤頁：鈴鐺線');
  const errs = [], ctx = await newCtx(browser, 1280); const page = await ctx.newPage(); watchErrors(page, errs);
  await page.goto(baseUrl + '/futures/?s=nvda&p=D', { waitUntil: 'load' });
  await unlock(page, '#futLock');
  await page.waitForSelector('#futBody:not([hidden]) #futChart canvas', { timeout: 20000 });
  ok(await until(page, () => document.querySelector('.al-banner:not([hidden])') != null), '解鎖後看盤頁最上方出現紅色提醒條');
  const bt = await page.textContent('.al-banner');
  ok(/1 檔已到價：輝達/.test(bt) && bt.includes('查看並關閉'), '提醒條文字：' + bt.trim());
  ok(await until(page, () => document.getElementById('futChart')._alDbg && document.getElementById('futChart')._alDbg.lines() === 3), '圖上有 3 條鈴鐺線（已到價、監控中、已關閉）');
  const st = await page.evaluate(() => ['hit1', 'on1', 'off1'].map((id) => ALERTS.statusOf(ALERTS.get('nvda').find((r) => r.id === id))));
  ok(st.join() === 'hit,on,off', '三種狀態：' + st);
  ok(await page.evaluate(() => !!document.querySelector('.fut-tool') && !!document.querySelector('.al-tool') && document.querySelector('.al-tool').parentElement === document.querySelector('.fut-tool').parentElement), '「🔔 提醒」按鈕和「水平線」同一組並排');
  ok(await page.evaluate(() => { const b = document.querySelector('.al-tool'), r = b.getBoundingClientRect(); return b.textContent.includes('提醒') && r.width > 60 && getComputedStyle(b).color !== getComputedStyle(document.querySelector('.fut-tool')).color; }), '提醒按鈕有文字且顏色與水平線不同（醒目）');
  ok(await page.evaluate(() => document.querySelector('.al-codelist') && document.querySelector('.al-codelist').textContent.includes('全部提醒')), '圖下方有「這檔的提醒」清單與「全部提醒 →」');
  await page.evaluate(() => { const c = document.getElementById('futChart'); window.scrollTo({ top: c.getBoundingClientRect().top + scrollY - 150, behavior: 'instant' }); }); await frames(page);
  await shot(page, 'watch-lines-light.png');
  // 放一條新線
  await page.click('.al-tool');
  ok(await page.evaluate(() => document.querySelector('.al-tool').getAttribute('aria-pressed') === 'true'), '按鈴鐺進入放線狀態');
  let cb = await chartBox(page);
  const n0 = (await ghRules()).length;
  await page.mouse.click(cb.x + cb.w * 0.35, cb.y + cb.h * 0.22);
  ok(await until(page, () => ALERTS.get('nvda').length === 4), '點圖放了一條提醒');
  ok(await until(page, () => !!document.querySelector('.al-tb:not([hidden])')), '放線後立刻浮出小工具列');
  let nr = await page.evaluate(() => { const r = ALERTS.get('nvda').find((x) => !['hit1', 'on1', 'off1'].includes(x.id)); return r; });
  const last = AF.lastNvda;
  ok(nr.dir === (nr.p >= last.c ? 'up' : 'down') && nr.dirAuto === true && nr.since === last.t && nr.mode === 'price', '方向自動、起算日＝最新 K 棒：' + JSON.stringify(nr));
  ok(await poll(async () => (await ghRules()).length === n0 + 1), '已送到小幫手並寫進（假）GitHub');
  ok(gh.puts[gh.puts.length - 1].message === '到價提醒設定更新', 'commit 訊息不含價格與代號');
  ok(await page.evaluate(() => document.querySelector('.al-tool').getAttribute('aria-pressed') === 'false'), '放完線自動離開放線狀態');
  const id = nr.id;
  // 方向：手動改跌破／漲破
  await page.click('.al-tb [data-dir="up"]'); ok(await until(page, (i) => { const r = ALERTS.get('nvda').find((x) => x.id === i); return r.dir === 'up' && r.dirAuto === false; }, id), '手動改成漲破（dirAuto=false）');
  await page.click('.al-tb [data-dir="auto"]'); ok(await until(page, (i) => ALERTS.get('nvda').find((x) => x.id === i).dirAuto === true, id), '改回自動');
  // 價格 → ％
  await page.click('.al-tb [data-mode="pct"]');
  ok(await until(page, (i) => ALERTS.get('nvda').find((x) => x.id === i).mode === 'pct', id) && await page.$('.al-tb .al-pct input'), '切到 ％ 模式並出現百分比輸入框');
  await page.fill('.al-tb .al-pct input', '-4'); await page.keyboard.press('Enter');
  ok(await until(page, (i) => { const r = ALERTS.get('nvda').find((x) => x.id === i); return r.pct === -4 && r.dir === 'down'; }, id), '改成 −4%：線移動且方向自動變跌破');
  nr = await page.evaluate((i) => ALERTS.get('nvda').find((x) => x.id === i), id);
  ok(Math.abs(nr.p - nr.base.c * 0.96) < 0.011, '目標價＝基準 × 0.96：' + nr.p + ' vs ' + nr.base.c * 0.96);
  ok(await poll(async () => Math.abs((await byId(id)).p - nr.p) < 1e-9 && (await byId(id)).mode === 'pct'), '％ 設定寫進小幫手');
  // 備註
  await page.fill('.al-tb .al-note', '測試備註'); await page.keyboard.press('Enter');
  ok(await until(page, (i) => ALERTS.get('nvda').find((x) => x.id === i).n === '測試備註', id), '備註');
  // 關閉 → 變灰保留 → 重新開啟
  await page.click('.al-tb [data-act="toggle"]');
  ok(await until(page, (i) => ALERTS.statusOf(ALERTS.get('nvda').find((x) => x.id === i)) === 'off', id), '關閉後狀態＝已關閉（線保留）');
  ok(await page.evaluate(() => document.getElementById('futChart')._alDbg.lines() === 4), '關閉後線還在圖上（變灰）');
  await page.click('.al-tb [data-act="toggle"]');
  ok(await until(page, (a) => { const r = ALERTS.get('nvda').find((x) => x.id === a[0]); return r.on && r.since === a[1]; }, [id, last.t]), '重新開啟：起算日重設成最新 K 棒');
  // 拖曳
  cb = await chartBox(page);
  const y1 = await page.evaluate((i) => document.getElementById('futChart')._alDbg.y(i), id);
  const p0 = (await byId(id)).p;
  await page.mouse.move(cb.x + cb.w * 0.6, cb.y + y1); await page.mouse.down(); await page.mouse.move(cb.x + cb.w * 0.6, cb.y + y1 - 40, { steps: 6 });
  const lbl = await page.evaluate(() => document.querySelector('.al-tb .al-tt') ? document.querySelector('.al-tb .al-tt').textContent : '');
  ok(/%/.test(lbl), '拖曳中即時顯示距最新收盤 %：' + lbl);
  await page.mouse.up();
  ok(await until(page, (a) => { const r = ALERTS.get('nvda').find((x) => x.id === a[0]); return r.p > a[1]; }, [id, p0]), '拖曳改變價位（往上）');
  await poll(async () => (await byId(id)).p > p0);
  const dr = await byId(id);
  ok(dr.p > p0 && dr.since === last.t && Math.abs(dr.p * 100 - Math.round(dr.p * 100)) < 1e-6, '拖曳後送到小幫手、價位吸附 0.01、起算日重設：' + p0 + ' → ' + dr.p);
  ok(dr.mode === 'pct' && Math.abs(dr.pct - (dr.p / dr.base.c - 1) * 100) < 0.01, '％ 模式拖曳後 % 跟著更新：' + dr.pct);
  // 儲存失敗 → 還原＋提示
  cb = await chartBox(page);
  mode.failPut = true;
  const y2 = await page.evaluate((i) => document.getElementById('futChart')._alDbg.y(i), id);
  await page.mouse.move(cb.x + cb.w * 0.6, cb.y + y2); await page.mouse.down(); await page.mouse.move(cb.x + cb.w * 0.6, cb.y + y2 + 50, { steps: 6 }); await page.mouse.up();
  ok(await until(page, () => [...document.querySelectorAll('.al-toast')].some((t) => t.textContent.includes('沒存到') && t.textContent.includes('已還原'))), '儲存失敗：跳「沒存到…已還原」');
  ok(await until(page, (a) => ALERTS.get('nvda').find((x) => x.id === a[0]).p === a[1], [id, dr.p]), '儲存失敗：價位還原成原本的');
  mode.failPut = false;
  // 刪除與復原
  await page.click('.al-tb [data-act="del"]');
  ok(await until(page, (i) => !ALERTS.get('nvda').some((x) => x.id === i), id) && await poll(async () => !(await byId(id))), '刪除（不用確認）');
  ok(await until(page, () => [...document.querySelectorAll('.al-toast')].some((t) => t.textContent.includes('復原'))), '刪除後 toast 有「復原」');
  await page.click('.al-toast button');
  ok(await until(page, (i) => ALERTS.get('nvda').some((x) => x.id === i), id) && await poll(async () => !!(await byId(id))), '按復原：提醒回來');
  // Delete 鍵刪除（先選取再按）
  cb = await chartBox(page);
  const y3 = await page.evaluate((i) => document.getElementById('futChart')._alDbg.y(i), id);
  await page.mouse.click(cb.x + cb.w * 0.55, cb.y + y3);
  ok(await until(page, (i) => document.getElementById('futChart')._alDbg.sel() === i, id), '點線選取');
  await page.keyboard.press('Delete');
  ok(await until(page, (i) => !ALERTS.get('nvda').some((x) => x.id === i), id), 'Delete 鍵刪除');
  // Alt+A
  cb = await chartBox(page);
  await page.mouse.move(cb.x + cb.w * 0.3, cb.y + cb.h * 0.4); await page.mouse.move(cb.x + cb.w * 0.3 + 2, cb.y + cb.h * 0.4 + 1);
  await page.keyboard.press('Alt+a');
  ok(await until(page, () => ALERTS.get('nvda').length === 4), 'Alt+A 在游標位置放提醒');
  // 水平線工具仍可用且與提醒互斥
  await page.click('.fut-tool'); await page.click('.al-tool');
  ok(await page.evaluate(() => document.querySelector('.al-tool').getAttribute('aria-pressed') === 'true' && document.querySelector('.fut-tool').getAttribute('aria-pressed') === 'false'), '水平線與提醒工具互斥');
  await page.keyboard.press('Escape');
  ok(await page.evaluate(() => document.querySelector('.al-tool').getAttribute('aria-pressed') === 'false'), 'Esc 離開放線狀態');
  await page.click('.fut-tool'); await page.click('.fut-tool');
  // 紅色提醒條可收起
  await page.click('.al-banner button');
  ok(await page.isHidden('.al-banner'), '提醒條 ✕ 暫時收起');
  await page.reload({ waitUntil: 'load' }); await page.waitForSelector('#futBody:not([hidden]) #futChart canvas'); await page.waitForTimeout(800);
  ok(await page.isHidden('.al-banner'), '同一個分頁重新整理仍收起（sessionStorage）');
  // 深色
  await page.emulateMedia({ colorScheme: 'dark' }); await page.waitForTimeout(500); await frames(page);
  ok(await until(page, () => document.getElementById('futChart')._alDbg && document.getElementById('futChart')._alDbg.lines() >= 3), '深色模式重畫後鈴鐺線還在');
  await page.evaluate(() => { const c = document.getElementById('futChart'); window.scrollTo({ top: c.getBoundingClientRect().top + scrollY - 150, behavior: 'instant' }); }); await frames(page);
  await shot(page, 'watch-lines-dark.png');
  await page.emulateMedia({ colorScheme: 'light' });
  ok(errs.length === 0, '第 2 段錯誤：' + errs.join(' | '));
  await ctx.close();
}

/* ---------- 3. 總覽牆、首頁、個股頁 ---------- */
async function otherPages(browser) {
  say('— 總覽牆、首頁、個股頁');
  const errs = [], ctx = await newCtx(browser, 1280); const page = await ctx.newPage(); watchErrors(page, errs);
  await page.goto(baseUrl + '/futures/', { waitUntil: 'load' });
  await unlock(page, '#kbGLockBox');
  await page.waitForSelector('.kb-card[data-id="nvda"]', { timeout: 20000 });
  await page.evaluate(() => document.querySelector('.kb-card[data-id="nvda"]').scrollIntoView({ block: 'center' }));
  await page.waitForSelector('.kb-card[data-id="nvda"] canvas', { timeout: 20000 });
  ok(await until(page, () => document.querySelector('.al-banner:not([hidden])') != null), '總覽牆：紅色提醒條');
  await page.evaluate(() => document.querySelector('.kb-card[data-id="nvda"]').scrollIntoView({ block: 'center' })); await frames(page);
  ok(await until(page, () => document.querySelector('.kb-card[data-id="nvda"] .al-badge') != null), '總覽牆：有到價的卡片角落有紅色 🔔 徽章');
  ok(await page.evaluate(() => document.querySelectorAll('.kb-card[data-id="amd"] .al-badge').length === 0), '沒到價的卡片沒有徽章');
  ok(await page.evaluate(() => document.querySelector('.kb-card[data-id="nvda"] .kb-cbox')._alDbg.lines() === 3 && !document.querySelector('.kb-card[data-id="nvda"] .al-tb')), '總覽牆小圖：畫線但不放工具列（唯讀）');
  await shot(page, 'banner-grid-light.png', { clip: { x: 0, y: 0, width: 1280, height: 520 } }).catch(() => { });
  // 首頁
  await page.goto(baseUrl + '/', { waitUntil: 'load' });
  ok(await until(page, () => document.querySelector('.al-banner:not([hidden])') != null, null, 15000), '首頁：已解鎖的裝置看到紅色提醒條');
  ok((await overflow(page)) <= 1, '首頁加了提醒條沒有水平捲動');
  await page.evaluate(() => scrollTo(0, 0)); await page.waitForTimeout(300);
  await shot(page, 'banner-home-light.png', { clip: { x: 0, y: 0, width: 1280, height: 420 } });
  // 個股頁
  await page.goto(baseUrl + '/nvda/', { waitUntil: 'load' });
  ok(await until(page, () => document.querySelector('#dyKToggle .al-dot') != null, null, 15000), '個股頁：K 棒區塊標題列有「已到價」紅點');
  ok(await page.evaluate(() => !document.getElementById('dyKB').querySelector('canvas')), '個股頁：K 棒仍預設收合（沒有因此載入圖）');
  await page.goto(baseUrl + '/amd/', { waitUntil: 'load' }); await page.waitForTimeout(1200);
  ok(await page.evaluate(() => !document.querySelector('#dyKToggle .al-dot')), '沒到價的公司沒有紅點');
  // 展開個股頁 K 棒：有鈴鐺線與提醒按鈕
  await page.goto(baseUrl + '/nvda/', { waitUntil: 'load' });
  await page.waitForSelector('#dyKToggle'); await page.click('#dyKToggle');
  ok(await until(page, () => document.querySelector('#dyKB .al-tool') != null && document.querySelector('#dyKB .fut-chart')._alDbg && document.querySelector('#dyKB .fut-chart')._alDbg.lines() === 3, null, 20000), '個股頁 K 棒：有「🔔 提醒」按鈕與 3 條鈴鐺線');
  ok(await page.evaluate(() => document.querySelector('#dyKB .al-codelist') != null), '個股頁 K 棒：有「這檔的提醒」清單');
  ok(errs.length === 0, '第 3 段錯誤：' + errs.join(' | '));
  await ctx.close();
  // 沒解鎖的新環境：個股頁完全不載入 alerts.js
  const c2 = await newCtx(browser, 1280); const p2 = await c2.newPage(); const reqs = [];
  p2.on('request', (r) => reqs.push(r.url()));
  await p2.goto(baseUrl + '/nvda/', { waitUntil: 'load' }); await p2.waitForTimeout(800);
  ok(!reqs.some((u) => u.includes('alerts.js') || u.includes('/data/alerts/')), '沒解鎖：個股頁不載入 alerts.js、也不讀 data/alerts');
  await c2.close();
}

/* ---------- 4. 提醒頁 ---------- */
async function alertsPage(browser, w, scheme) {
  say(`— 提醒頁 ${w}px ${scheme}`);
  const errs = [], ctx = await newCtx(browser, w, scheme); const page = await ctx.newPage(); watchErrors(page, errs);
  page.on('dialog', (d) => d.accept());
  await page.goto(baseUrl + '/alerts/', { waitUntil: 'load' });
  await unlock(page, '#alLock');
  await page.waitForSelector('#alBody:not([hidden]) .al-grp');
  await until(page, () => document.querySelectorAll('.al-r').length >= 3);
  const g = await page.evaluate(() => [...document.querySelectorAll('.al-grp')].map((d) => ({ k: d.dataset.k, n: d.querySelector('summary .n').textContent, rows: d.querySelectorAll('.al-r').length, open: d.open })));
  ok(g.map((x) => x.k).join() === 'hit,on,off', '三組順序：已到價（置頂）→ 監控中 → 已關閉：' + JSON.stringify(g));
  ok(g[0].rows === 1 && g[1].rows === 2 && g[2].n.includes('2'), '各組數量：' + JSON.stringify(g));
  ok((await page.textContent('#alStatus')).includes('已連線'), '狀態列：小幫手已連線');
  ok(await page.evaluate(() => document.querySelector('.al-banner:not([hidden])') != null), '提醒頁最上方也有紅色提醒條');
  ok(await page.evaluate(() => document.querySelector('.al-grp.hit .al-r .px').textContent.includes('最新收盤') && document.querySelector('.al-grp.hit .al-r').textContent.includes('當天最低')), '已到價列：到價日＋當天最低價、最新收盤與距離');
  const ons = await page.evaluate(() => [...document.querySelectorAll('.al-grp.on .al-r .gap')].map((e) => Math.abs(parseFloat(e.textContent.replace('−', '-').replace(/[^\d.\-+]/g, '')))));
  ok(ons.length === 2 && ons[0] <= ons[1], '監控中依「還差多少 %」由近到遠：' + ons);
  ok(await page.evaluate(() => document.querySelector('.al-grp.on .al-r:nth-of-type(1) .main, .al-grp.on .al-r .main').textContent.includes('基準') || [...document.querySelectorAll('.al-grp.on .al-r')].some((r) => r.textContent.includes('基準') && r.textContent.includes('−10%'))), '％ 模式的列顯示 −10%＝價格與基準');
  await shot(page, `alerts-${w}-${scheme}.png`, { fullPage: true });
  // 新增 ETF 提醒（不必開圖）
  await page.fill('#alFind', 'voo');
  ok(await page.evaluate(() => [...document.querySelectorAll('#alPick option')].filter((o) => o.value).length >= 1 && document.querySelector('#alPick optgroup[label="ETF"]') != null), '搜尋「voo」：選單只留符合的，且有 ETF 群組');
  await page.selectOption('#alPick', 'etf_voo');
  ok(await until(page, () => document.getElementById('alLast').textContent.includes('最新收盤')), '選標的後顯示最新收盤');
  const lc = await page.evaluate(() => ALERTS.lastOf('etf_voo').c);
  await page.fill('#alVal', String(Math.round(lc * 1.1 * 100) / 100));
  ok(await until(page, () => document.getElementById('alPrev').textContent.includes('漲破')), '預覽：自動判斷漲破：' + await page.textContent('#alPrev'));
  const n0 = (await ghRules()).length;
  await page.click('#alAdd');
  ok(await until(page, () => ALERTS.get('etf_voo').filter((r) => r.on).length === 1), '新增 ETF 提醒（價格）');
  await poll(async () => (await ghRules()).length === n0 + 1);
  const vr = (await ghRules()).find((r) => r.code === 'etf_voo' && r.on);
  ok(vr && vr.kind === 'etf' && vr.dir === 'up' && vr.mode === 'price' && (await ghRules()).length === n0 + 1, '寫進小幫手：' + JSON.stringify(vr));
  // 百分比新增（期貨）
  await page.fill('#alFind', ''); await page.selectOption('#alPick', 'nq'); await until(page, () => document.getElementById('alLast').textContent.includes('最新收盤'));
  await page.click('#alForm [data-t="pct"]'); await page.fill('#alVal', '-10'); await page.fill('#alNote', '期貨％');
  ok(await until(page, () => document.getElementById('alPrev').textContent.includes('跌破')), '％ 預覽：−10% 自動跌破：' + await page.textContent('#alPrev'));
  await page.click('#alAdd');
  ok(await until(page, () => ALERTS.get('nq').length === 1), '新增期貨提醒（％）');
  await poll(async () => (await ghRules()).some((r) => r.code === 'nq'));
  const nq = (await ghRules()).find((r) => r.code === 'nq');
  ok(nq && nq.mode === 'pct' && nq.pct === -10 && nq.dir === 'down' && nq.kind === 'fut' && nq.n === '期貨％', '％ 提醒內容：' + JSON.stringify(nq));
  // 編輯
  await page.click('.al-grp.on .al-r[data-id="' + nq.id + '"] [data-a="edit"]');
  await page.fill('.al-ed [data-ev="n"]', '改過的備註'); await page.click('.al-ed [data-a="save"]');
  ok(await until(page, () => ALERTS.get('nq')[0].n === '改過的備註'), '編輯備註後儲存');
  // 關閉 → 已關閉組 → 重新開啟
  await page.click('.al-grp.on .al-r[data-id="' + nq.id + '"] [data-a="toggle"]');
  ok(await until(page, () => ALERTS.get('nq')[0].on === false) && await poll(async () => (await byId(nq.id)).on === false && !!(await byId(nq.id)).offAt), '關閉：移到已關閉並記 offAt');
  await page.evaluate(() => { document.querySelector('.al-grp.off').open = true; });
  await page.click('.al-grp.off .al-r[data-id="' + nq.id + '"] [data-a="toggle"]');
  ok(await until(page, () => ALERTS.get('nq')[0].on === true), '重新開啟');
  // 全部刪除已關閉
  await page.evaluate(() => { document.querySelector('.al-grp.off').open = true; });
  await poll(async () => (await ghRules()).some((r) => !r.on));
  const offN = (await ghRules()).filter((r) => !r.on).length;
  ok(offN >= 2, '有 ' + offN + ' 條已關閉可刪');
  await page.click('[data-a="deloff"]');
  ok(await until(page, () => ALERTS.all().every((r) => r.on)), '全部刪除已關閉（有 confirm）');
  ok(await poll(async () => (await ghRules()).every((r) => r.on)), '小幫手那邊也刪了');
  // 刪除單條＋復原
  await page.click('.al-grp.on .al-r[data-id="' + nq.id + '"] [data-a="del"]');
  ok(await until(page, () => ALERTS.get('nq').length === 0), '刪除單條');
  await page.click('.al-toast button');
  ok(await until(page, () => ALERTS.get('nq').length === 1), '復原');
  // 版面
  ok((await overflow(page)) <= 1, `提醒頁 ${w}px 沒有水平捲動`);
  if (w <= 600) {
    const hs = await bigBtn(page, '.al-r .al-b, #alAdd, .al-form .seg button');
    ok(hs.length > 5 && hs.every((h) => h >= 40), '手機：提醒頁按鈕高度都 ≥ 40px：' + [...new Set(hs)]);
    const cardOk = await page.evaluate(() => { const r = document.querySelector('.al-grp.on .al-r'); return getComputedStyle(r).gridTemplateColumns.split(' ').length === 1; });
    ok(cardOk, '手機：清單改成卡片式（單欄）');
  }
  ok(errs.length === 0, '第 4 段錯誤：' + errs.join(' | '));
  if (w > 600 && scheme === 'light') { await page.evaluate(() => scrollTo(0, 0)); await shot(page, 'alerts-top-1280-light.png', { clip: { x: 0, y: 0, width: 1280, height: 900 } }); }
  await ctx.close();
}

/* ---------- 5. 手機看盤頁 ---------- */
async function phoneWatch(browser) {
  say('— 手機看盤頁 390px');
  const errs = [], ctx = await newCtx(browser, 390); const page = await ctx.newPage(); watchErrors(page, errs);
  await page.goto(baseUrl + '/futures/?s=nvda&p=D', { waitUntil: 'load' });
  await unlock(page, '#futLock');
  await page.waitForSelector('#futBody:not([hidden]) #futChart canvas', { timeout: 20000 });
  await until(page, () => document.getElementById('futChart')._alDbg && document.getElementById('futChart')._alDbg.lines() === 3);
  ok((await overflow(page)) <= 1, '手機看盤頁沒有水平捲動');
  const hs = await bigBtn(page, '.al-tool');
  ok(hs.length === 1 && hs[0] >= 40, '手機：「🔔 提醒」按鈕 ≥ 40px 高：' + hs);
  await page.click('.al-tool');
  const cb = await chartBox(page);
  await page.mouse.click(cb.x + cb.w * 0.4, cb.y + cb.h * 0.3);
  ok(await until(page, () => ALERTS.get('nvda').length === 4 && document.querySelector('.al-tb:not([hidden])') != null), '手機：點圖放提醒並浮出工具列');
  const tb = await page.evaluate(() => { const r = document.querySelector('.al-tb').getBoundingClientRect(), c = document.getElementById('futChart').getBoundingClientRect(); return { l: r.left >= c.left - 1, r: r.right <= c.right + 1, hs: [...document.querySelectorAll('.al-tb button, .al-tb input')].map((e) => Math.round(e.getBoundingClientRect().height)) }; });
  ok(tb.l && tb.r && tb.hs.every((h) => h >= 40), '手機：工具列在圖內、按鈕輸入框 ≥ 40px：' + JSON.stringify(tb));
  ok((await overflow(page)) <= 1, '手機放線後沒有水平捲動');
  await shot(page, 'watch-phone-390-light.png');
  const id = await page.evaluate(() => document.getElementById('futChart')._alDbg.sel());
  await page.click('.al-tb [data-act="del"]');
  ok(await until(page, () => ALERTS.get('nvda').length === 3), '手機：刪除');
  ok(errs.length === 0, '第 5 段錯誤：' + errs.join(' | '));
  await ctx.close();
}

/* ---------- 6. 每日行情報告（Gmail HTML）渲染 ---------- */
async function report(browser) {
  say('— 每日行情報告');
  const errs = [], ctx = await newCtx(browser, 420); const page = await ctx.newPage(); watchErrors(page, errs);
  await page.setContent(AF.reportHtml, { waitUntil: 'load' });
  ok((await overflow(page)) <= 1, '信件在手機寬度沒有水平捲動');
  ok(await page.evaluate(() => { const t = document.body.innerText; return t.indexOf('已到價') < t.indexOf('監控中') && t.indexOf('監控中') < t.indexOf('追蹤標的總表'); }), '信件順序：已到價 → 監控中 → 總表');
  await shot(page, 'report-phone-light.png', { fullPage: true });
  await page.emulateMedia({ colorScheme: 'dark' }); await shot(page, 'report-phone-dark.png', { fullPage: true });
  await page.setViewportSize({ width: 800, height: 900 }); await page.emulateMedia({ colorScheme: 'light' });
  await shot(page, 'report-desktop-light.png', { fullPage: false });
  ok(errs.length === 0, '報告錯誤：' + errs.join(' | '));
  await ctx.close();
}

(async () => {
  C = await import(pathToFileURL(path.join(ROOT, 'worker', 'core.js')).href);
  ALERT_KEY = AF.alertKey;
  const resetGh = () => { gh.file = { sha: 's1', text: JSON.stringify(AF.rules) }; gh.puts.length = 0; };
  resetGh();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  baseUrl = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  try {
    await lockedAndUnset(browser); resetGh();
    await watchFlow(browser); resetGh();
    await otherPages(browser); resetGh();
    for (const [w, s] of [[1280, 'light'], [1280, 'dark'], [390, 'light'], [390, 'dark']]) { await alertsPage(browser, w, s); resetGh(); }
    await phoneWatch(browser); resetGh();
    await report(browser);
  } catch (e) { bad++; console.log('  ✗ 測試中斷：', e && e.stack || e); }
  await browser.close(); server.close(); fs.rmSync(tmp, { recursive: true, force: true });
  console.log(bad ? `\n✗ ${bad} 項失敗` : '\n✓ 全部通過');
  process.exit(bad ? 1 : 0);
})();
