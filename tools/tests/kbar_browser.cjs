/* 看盤頁／個股頁 K 棒的瀏覽器測試（CI 用；用合成資料，不碰 repo 的 data/）。
   用法（先 python3 tools/build.py）：
     node tools/tests/kbar_browser.cjs [--shots <資料夾>]
   需要：playwright（node 套件，NODE_PATH 或本機 node_modules 找得到）與 chromium（PW_CHROMIUM 指定執行檔；沒指定就用 playwright 自己的）。
   流程：呼叫 tools/tests/kbar_fixture.py 在臨時資料夾產生合成期貨與個股 K 棒檔（含測試用 key.json 與密碼），
   起一個本機伺服器：網站檔案取自 repo，/data/futures/ 與 /data/kbar/ 改取臨時資料夾。
   總覽牆（預設畫面）：卡片數＝商品數、未解鎖不顯示價格、延遲建圖、每張卡只有 1 張圖、分類篩選與家數、週期／KD／排序切換會重建、點卡片進單檔、?s= 直接進單檔、回總覽、讀不到的卡顯示「—」。
   單檔檢視（?s= 進入）的檢查維持原樣。個股頁的 K 棒區塊預設收合，展開才載入。
   檢查：未解鎖（無 JS 錯誤、不顯示價格）→ 解鎖 → 清單／切換商品／日週月／鍵盤 ↑↓／深連結／讀不到的列顯示「—」／歷史檔合併／
         個股頁（tsmc、pltr、nvda 三種模板）K 棒延遲載入、解鎖後預設 K 棒；390px 與 1280px 都不可整頁水平捲動；淺色、深色各跑一次。
   --shots 會另存截圖（deviceScaleFactor 2；畫面角落標「合成測試資料」）。 */
const http = require('http'), fs = require('fs'), path = require('path'), os = require('os'), cp = require('child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const shotsDir = process.argv.includes('--shots') ? process.argv[process.argv.indexOf('--shots') + 1] : null;
const IGNORE = ['Failed to load resource', 'net::ERR', 'fonts.googleapis', 'fonts.gstatic'];
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kbar-fx-'));
const out = cp.spawnSync('python3', [path.join(ROOT, 'tools', 'tests', 'kbar_fixture.py'), tmp], { encoding: 'utf8' });
if (out.status !== 0) { console.error(out.stdout, out.stderr); process.exit(2); }
const FX = JSON.parse(out.stdout.trim().split('\n').pop());

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  const base = /^\/data\/(futures|kbar)\//.test(p) ? tmp : ROOT;
  const f = path.normalize(path.join(base, p));
  if (!f.startsWith(base) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); res.end('not found'); return; }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});

let bad = 0;
const ok = (cond, msg) => { if (!cond) { bad++; console.log('  ✗', msg); } };
const say = (msg) => console.log(msg);

async function watchErrors(page, errs) {
  page.on('pageerror', (e) => errs.push('例外：' + e));
  page.on('console', (m) => { if (m.type() === 'error' && !IGNORE.some(x => m.text().includes(x))) errs.push('console.error：' + m.text()); });
}
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const BANNER = '合成測試資料（不是真實行情）';
async function shot(page, name, el) {
  if (!shotsDir) return;
  fs.mkdirSync(shotsDir, { recursive: true });
  const file = path.join(shotsDir, name);
  await page.mouse.move(0, 0);   // 游標留在清單上會讓那一列帶著滑過的底色，看起來像兩列被選取
  if (el) {   // 區塊截圖：標示放在區塊最上面（不是固定在視窗），用整頁座標裁切，避免黏住的導覽列疊在圖上
    await page.evaluate(([sel, t]) => { const h = document.querySelector(sel); if (h.querySelector('.fx-banner')) return; const d = document.createElement('div'); d.className = 'fx-banner'; d.textContent = t; d.style.cssText = 'background:#b00020;color:#fff;font:600 12px sans-serif;padding:3px 8px;text-align:center;margin-bottom:6px'; h.prepend(d); }, [el, BANNER]);
    await page.evaluate(() => scrollTo(0, 0));
    await page.waitForTimeout(400);
    const box = await page.locator(el).evaluate((n) => { const r = n.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height }; });
    await page.screenshot({ path: file, fullPage: true, clip: box });
  } else {
    await page.evaluate(([t]) => { const app = document.getElementById('kbApp'); if (app) window.scrollTo(0, app.getBoundingClientRect().top + scrollY - 64); if (document.getElementById('fxBanner')) return; const d = document.createElement('div'); d.id = 'fxBanner'; d.textContent = t; d.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#b00020;color:#fff;font:600 12px sans-serif;padding:3px 8px;text-align:center;pointer-events:none'; document.body.appendChild(d); }, [BANNER]);
    await page.waitForTimeout(500);
    await page.screenshot({ path: file });
  }
  say('  截圖 ' + name);
}
async function unlock(page) {
  await page.waitForSelector('form.fut-lock');
  await page.fill('form.fut-lock input[type=password]', FX.password);
  await page.click('form.fut-lock button.go');
}
const pick = async (page, id) => {   // 窄螢幕要先展開清單面板
  if (await page.evaluate(() => getComputedStyle(document.getElementById('kbPanel')).display === 'none')) await page.click('#kbTog');
  await page.click(`.kb-row[data-id="${id}"]`);
};
const title = (page) => page.textContent('#futTitle');
/* 等條件成立（不丟錯，逾時回 false，讓後面的 ok() 帶著訊息失敗）；取代固定 sleep */
const until = (page, fn, arg, ms) => page.waitForFunction(fn, arg, { timeout: ms || 10000 }).then(() => true, () => false);
/* 等兩個畫格：捲動後 IntersectionObserver 的回呼、版面計算都已跑完 */
const frames = (page) => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
/* 總覽牆：接近畫面的卡都已建好圖（或顯示「—」），沒有還在讀的 */
const settled = (page) => until(page, () => [...document.querySelectorAll('.kb-card')].every(c => !c._near || c._chart || c.querySelector('.kb-empty')), null, 20000);
/* 章節導覽目前看得到的連結文字 */
const navLinks = (page) => page.evaluate(() => [...document.querySelectorAll('.secnav a[data-mode-link]')].filter(a => getComputedStyle(a).display !== 'none').map(a => a.textContent).join(','));

async function watchPage(browser, base, w, scheme) {
  const tag = `看盤頁 ${w}px ${scheme}`;
  say('— ' + tag);
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, deviceScaleFactor: 2, colorScheme: scheme });
  const page = await ctx.newPage(), errs = [];
  await watchErrors(page, errs);
  // 1. 未解鎖
  await page.goto(base + '/futures/?s=ym', { waitUntil: 'load' });   // 單檔檢視：有 ?s= 才會直接進單檔（沒有 ?s= 是總覽牆）
  await page.waitForSelector('form.fut-lock');
  await page.waitForFunction(() => document.querySelectorAll('.kb-row').length >= 20);
  await until(page, () => /資料截至/.test(document.querySelector('.kb-row .px').textContent));
  ok(await page.evaluate(() => !document.querySelector('.kb-row .ch.kup, .kb-row .ch.kdn')), '未解鎖不該顯示漲跌');
  ok(await page.evaluate(() => /資料截至/.test(document.querySelector('.kb-row .px').textContent)), '未解鎖的列要顯示「資料截至」');
  ok(await page.evaluate(() => !/\d{1,3}(,\d{3})*\.\d\d/.test(document.getElementById('kbList').textContent)), '未解鎖不該出現價格');
  ok(await page.evaluate(() => document.getElementById('futBody').hidden), '未解鎖不該顯示圖');
  ok((await overflow(page)) <= 1, `未解鎖有橫向捲動 ${await overflow(page)}px`);
  // 焦點在輸入框（密碼欄）時，↑↓ 不能被拿去換商品
  const sel0 = await page.evaluate(() => document.querySelector('.kb-row[aria-selected="true"]').dataset.id);
  await page.focus('form.fut-lock input[type=password]'); await page.keyboard.press('ArrowDown'); await page.waitForTimeout(150);
  ok((await page.evaluate(() => document.querySelector('.kb-row[aria-selected="true"]').dataset.id)) === sel0, '焦點在輸入框時 ↓ 不該換商品');
  // 2. 解鎖
  await unlock(page);
  await page.waitForSelector('#futBody:not([hidden]) canvas', { timeout: 15000 });
  await page.waitForFunction(() => document.querySelectorAll('.kb-row .ch.kup, .kb-row .ch.kdn').length >= 20, null, { timeout: 15000 });
  // 逐檔讀取（一次 4 檔）：等全部讀完再檢查讀不到的那一列（CI 機器慢時，只等 20 列有漲跌會太早）
  await page.waitForFunction(() => ![...document.querySelectorAll('.kb-row .px')].some(x => x.textContent === '讀取中'), null, { timeout: 15000 });
  ok(/上漲 \d+ · 下跌 \d+ · 平 \d+/.test(await page.textContent('#kbSum')), '漲跌家數文字');
  const missing = await page.evaluate((id) => { const r = document.querySelector(`.kb-row[data-id="${id}"]`); return r && { ch: r.querySelector('.ch').textContent, px: r.querySelector('.px').textContent, title: r.title }; }, FX.missing[0]);
  ok(missing && missing.ch === '—' && missing.px === '—' && /讀不到/.test(missing.title), '讀不到資料檔的列要顯示「—」與原因：' + JSON.stringify(missing));
  // 換過密碼、某一檔還沒用新密碼重新產生：只有那一列顯示原因，整頁不能被上鎖
  const stale = await page.evaluate((id) => { const r = document.querySelector(`.kb-row[data-id="${id}"]`); return r && { ch: r.querySelector('.ch').textContent, title: r.title }; }, FX.staleKey[0]);
  ok(stale && stale.ch === '—' && /解不開/.test(stale.title), '近期檔解不開的列要顯示「—」與原因：' + JSON.stringify(stale));
  ok(await page.evaluate(() => !document.getElementById('futBody').hidden && !!localStorage.getItem('erd-futures-key-v1')), '某一檔解不開不可把整個網站上鎖');
  const sh = await page.evaluate(async (id) => { const d = await KB.full(id); return d && { hm: d.histMissing, n: d.bars.length }; }, FX.staleHist[0]);
  ok(sh && sh.hm === true && sh.n > 0 && await page.evaluate(() => !!localStorage.getItem('erd-futures-key-v1')), '歷史檔解不開：只顯示近期、標 histMissing、不上鎖：' + JSON.stringify(sh));
  say('  第一檔：' + (await title(page)));
  // 清單順序：指數期貨 3 檔在最前
  const first3 = await page.evaluate(() => [...document.querySelectorAll('.kb-row')].slice(0, 3).map(r => r.dataset.id));
  ok(first3.join() === 'ym,nq,tx', '期貨三檔在最前：' + first3);
  // 切換個股
  await pick(page, 'nvda');
  await page.waitForFunction(() => /輝達 NVDA 日 K/.test(document.getElementById('futTitle').textContent) && /NASDAQ/.test(document.getElementById('futSub').textContent));
  ok(/看財報/.test(await page.textContent('#kbFin')) && (await page.getAttribute('#kbFin', 'href')).endsWith('nvda/'), '看財報連結');
  ok(/NASDAQ · USD · 已依分割調整、不含股利/.test(await page.textContent('#futSub')), '個股副標：' + await page.textContent('#futSub'));
  ok(/合成測試資料/.test(await page.textContent('#futSrc')), '來源區要有檔內 source／check 文字');
  // 歷史檔合併
  const hist = await page.evaluate(async () => { const d = await KB.full('nvda'); const t = d.bars.map(b => b[0]); return { n: t.length, first: t[0], sorted: t.every((x, i) => !i || x > t[i - 1]), hm: d.histMissing }; });
  ok(hist.first === '2023-01-02' && hist.sorted && hist.n > 900 && !hist.hm, '歷史檔合併：' + JSON.stringify(hist));
  // 日週月
  for (const [p, label] of [['W', '週 K'], ['M', '月 K'], ['D', '日 K']]) {
    await page.click(`.fut-ctrl [data-p="${p}"]`);
    await page.waitForFunction((l) => document.getElementById('futTitle').textContent.endsWith(l), label);
    ok(page.url().includes('p=' + p), 'URL 要記住週期 ' + p);
  }
  // 均線、成交量、畫線按鈕
  await page.click('#futMaBtns [data-ma="5"]'); await page.click('#futVol'); await page.click('#futVol');
  ok((await page.$$('#futMa canvas, #futChart canvas')).length > 0, '圖有 canvas');
  ok((await page.$$eval('#futMaTbl tbody tr', r => r.length)) === 5, '均線表 5 列');
  // 鍵盤
  const sel = () => page.evaluate(() => document.querySelector('.kb-row[aria-selected="true"]').dataset.id);
  const before = await sel();
  await page.mouse.click(5, 5); await page.keyboard.press('ArrowDown');
  await page.waitForFunction((b) => document.querySelector('.kb-row[aria-selected="true"]').dataset.id !== b, before);
  const after = await sel(); ok(after !== before, '↓ 要換商品：' + before + '→' + after);
  ok((await page.$$eval('.kb-row[aria-selected="true"]', r => r.length)) === 1, '清單只能有一列被選取');
  for (let i = 0; i < 6; i++) { await page.keyboard.press(i % 2 ? 'ArrowUp' : 'ArrowDown'); await page.waitForTimeout(120); }   // 連按（中間留一點空檔）是要製造「上一檔還在讀、又換下一檔」的競態
  await until(page, () => { const r = document.querySelector('.kb-row[aria-selected="true"] .n'); return r && document.getElementById('futTitle').textContent.startsWith(r.textContent) && document.querySelector('#futChart canvas'); });
  await frames(page);
  const leak = await page.evaluate(() => { const c = document.getElementById('futChart'); return { charts: c.querySelectorAll('.tv-lightweight-charts').length, tb: c.querySelectorAll('.fut-ltb').length }; });
  ok(leak.charts === 1 && leak.tb === 1, '切換多次後只能留一張圖（舊圖要釋放）：' + JSON.stringify(leak));
  await page.keyboard.press('ArrowUp'); await until(page, (b) => document.querySelector('.kb-row[aria-selected="true"]').dataset.id === b, before);
  ok((await sel()) === before, '↑ 要回到原商品');
  // 排序切換
  if (w < 900) await page.click('#kbTog');
  await page.click('#kbSort [data-sort="chg"]');
  ok(await page.evaluate(() => /漲跌幅高到低/.test(document.getElementById('kbList').textContent)), '漲跌幅排序');
  const chs = await page.evaluate(() => [...document.querySelectorAll('.kb-grp')][1] && [...document.querySelectorAll('.kb-row')].slice(3).map(r => parseFloat(r.querySelector('.ch').textContent.replace('−', '-'))).filter(x => !isNaN(x)));
  ok(chs && chs.every((x, i) => !i || x <= chs[i - 1] + 1e-9), '漲跌幅由高到低');
  await page.click('#kbSort [data-sort="sector"]'); if (w < 900) await page.click('#kbTog');
  // 三星：dp 0；期貨：tx、ym
  await pick(page, 'samsung');
  await page.waitForFunction(() => /三星電子/.test(document.getElementById('futTitle').textContent));
  ok(/KRW/.test(await page.textContent('#futSub')) && !/收 [\d,]+\.\d/.test(await page.textContent('#futLeg')), '三星（KRW）不顯示小數：' + await page.textContent('#futLeg'));
  for (const c of ['ym', 'nq', 'tx']) {
    await pick(page, c);
    await page.waitForFunction((c) => document.querySelector('.kb-row[aria-selected="true"]').dataset.id === c && /期貨/.test(document.getElementById('futTitle').textContent), c);
  }
  ok(/日盤/.test(await page.textContent('#futSub')) && /日盤（一般交易時段/.test(await page.textContent('#futSrc')), 'TX 來源說明沿用期貨頁的寫法');
  // 暫定、待確認
  await pick(page, 'amd');
  await page.waitForFunction(() => /超微/.test(document.getElementById('futTitle').textContent) || /超微/.test(document.querySelector('.kb-row[aria-selected="true"] .n').textContent));
  await until(page, () => /超微/.test(document.getElementById('futTitle').textContent) && /暫定/.test(document.getElementById('futSub').textContent));
  ok(/暫定/.test(await page.textContent('#futSub')) && /暫定/.test(await page.textContent('#futSrc')), '暫定標示');
  await pick(page, 'csco'); await until(page, () => /思科/.test(document.getElementById('futTitle').textContent) && /待確認/.test(document.getElementById('futSrc').textContent));
  ok(/待確認：1 天的 K 棒沒有採用/.test(await page.textContent('#futSrc')), '待確認清單');
  await pick(page, 'spcx'); await until(page, () => /SpaceX/.test(document.getElementById('futTitle').textContent) && document.querySelector('#futBody:not([hidden]) #futChart canvas'));
  ok(/SpaceX/.test(await page.textContent('#futTitle')), '上市不滿一年（沒有歷史檔）也能畫：' + await title(page));
  // 深連結
  for (const [s, p, expect] of [['ym', 'W', /小道瓊期貨 週 K/], ['nq', 'M', /小那指期貨 月 K/], ['tsmc', 'D', /台積電 \S+ 日 K/]]) {
    await page.goto(`${base}/futures/?s=${s}&p=${p}`, { waitUntil: 'load' });
    await page.waitForFunction(() => document.querySelector('#futBody:not([hidden]) canvas'), null, { timeout: 15000 });
    await page.waitForFunction((r) => new RegExp(r).test(document.getElementById('futTitle').textContent), expect.source);
  }
  // 選到的商品記住
  await page.goto(base + '/futures/', { waitUntil: 'load' });
  ok(await page.evaluate(() => !document.getElementById('kbGrid').hidden && document.getElementById('kbApp').hidden), '沒有 ?s= 的網址開總覽，不自動跳單檔');
  await page.click('#kbMode [data-mode="single"]');
  await page.waitForFunction(() => document.querySelector('.kb-row[aria-selected="true"]') && !document.getElementById('kbApp').hidden);
  ok((await sel()) === 'tsmc', '記住上次看的商品：' + await sel());
  // 窄螢幕的清單面板
  if (w < 900) {
    ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbPanel')).display === 'none'), '窄螢幕清單預設收起');
    await page.click('#kbTog'); ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbPanel')).display !== 'none'), '按鈕展開清單');
    await shot(page, `watch-${w}-${scheme}-list.png`);
    await page.click('.kb-row[data-id="nvda"]');
    ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbPanel')).display === 'none'), '選了商品後收起');
    await page.click('#kbNext');
  } else {
    ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbTog')).display === 'none' && getComputedStyle(document.getElementById('kbPanel')).display !== 'none'), '寬螢幕清單固定顯示');
    await pick(page, 'nvda');
  }
  await page.waitForFunction(() => /\S+ \S+ 日 K/.test(document.getElementById('futTitle').textContent));
  await page.waitForSelector('#futBody:not([hidden]) #futChart canvas', { timeout: 15000 }); await frames(page);
  ok((await overflow(page)) <= 1, `${tag} 整頁水平捲動 ${await overflow(page)}px`);
  await shot(page, `watch-${w}-${scheme}.png`);
  // 上鎖
  await page.click('#futLockBtn'); await page.waitForSelector('form.fut-lock');
  ok(await page.evaluate(() => !document.querySelector('.kb-row .ch.kup, .kb-row .ch.kdn')), '上鎖後不顯示漲跌');
  ok(errs.length === 0, '錯誤：' + errs.join(' | '));
  await ctx.close();
}

async function gridShot(page, name, full) {
  if (!shotsDir) return;
  fs.mkdirSync(shotsDir, { recursive: true });
  if (full) {   // 延遲建圖：整頁截圖前先把每張卡捲過一遍
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    for (let y = 0; y < h; y += 500) { await page.evaluate((y) => scrollTo(0, y), y); await page.waitForTimeout(120); }
    await page.waitForFunction(() => [...document.querySelectorAll('.kb-card')].every(c => c.querySelector('.tv-lightweight-charts') || c.querySelector('.kb-empty')), null, { timeout: 15000 });
  }
  await page.evaluate(([t, full]) => { if (!document.getElementById('fxBanner')) { const d = document.createElement('div'); d.id = 'fxBanner'; d.textContent = t; d.style.cssText = 'background:#b00020;color:#fff;font:600 13px sans-serif;padding:4px 8px;text-align:center;margin-bottom:8px'; document.querySelector('.kb-modebar').before(d); } const g = document.getElementById('fxBanner'); scrollTo({ top: full ? 0 : g.getBoundingClientRect().top + scrollY - 60, behavior: 'instant' }); }, [BANNER, !!full]);   // 頁面是 scroll-behavior: smooth：要立即捲到位，整頁截圖才不會把黏住的導覽列拍在半路
  await page.mouse.move(0, 0); await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(shotsDir, name), fullPage: !!full });
  say('  截圖 ' + name);
}

async function gridPage(browser, base, w, scheme) {
  const tag = `總覽牆 ${w}px ${scheme}`;
  say('— ' + tag);
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, deviceScaleFactor: 2, colorScheme: scheme });
  const page = await ctx.newPage(), errs = [];
  await watchErrors(page, errs);
  const nCards = () => page.evaluate(() => document.querySelectorAll('.kb-card').length);
  const bad1 = () => page.evaluate(() => [...document.querySelectorAll('.kb-card')].filter(c => c.querySelectorAll('.tv-lightweight-charts').length > 1).map(c => c.dataset.id));
  const built = () => page.evaluate(() => [...document.querySelectorAll('.kb-card')].filter(c => c.querySelector('.tv-lightweight-charts')).length);
  // 1. 預設總覽、未解鎖
  await page.goto(base + '/futures/', { waitUntil: 'load' });
  await page.waitForSelector('form.fut-lock');
  await page.waitForFunction(() => document.querySelectorAll('.kb-row').length >= 20);
  await until(page, () => [...document.querySelectorAll('.kb-cm')].filter(c => /資料截至 \d/.test(c.textContent)).length >= document.querySelectorAll('.kb-card').length - 1);
  const rows = await page.evaluate(() => document.querySelectorAll('.kb-row').length);
  ok(await page.evaluate(() => !document.getElementById('kbGrid').hidden && document.getElementById('kbApp').hidden && document.getElementById('kbMode').querySelector('[data-mode="grid"]').getAttribute('aria-pressed') === 'true'), '預設是總覽');
  ok((await nCards()) === rows && rows >= 20, `卡片數＝商品數：${await nCards()} / ${rows}`);
  ok(await page.evaluate(() => !document.querySelector('.kb-card canvas') && !document.querySelector('.kb-cpx .ch.kup, .kb-cpx .ch.kdn')), '未解鎖不畫圖、不顯示漲跌');
  ok(await page.evaluate(() => !/\d{1,3}(,\d{3})*\.\d\d/.test(document.getElementById('kbCards').textContent) && /資料截至/.test(document.querySelector('.kb-cm').textContent)), '未解鎖不出現價格，顯示「資料截至」');
  ok((await overflow(page)) <= 1, `${tag} 未解鎖水平捲動 ${await overflow(page)}px`);
  ok((await navLinks(page)) === '總覽', '總覽模式的章節導覽只留「總覽」（K 棒／均線／資料來源只在單檔）：' + await navLinks(page));
  ok(await page.evaluate(() => { const g = document.getElementById('kbGSum').getBoundingClientRect().top - document.getElementById('kbMode').getBoundingClientRect().bottom; return g >= 0 && g <= 24; }), '「總覽｜單檔」與家數列之間不留大片空白');
  if (w > 600 && scheme === 'light') await gridShot(page, 'grid-1280-light-locked.png', false);
  // 2. 解鎖
  await unlock(page);
  await page.waitForSelector('.kb-card canvas', { timeout: 15000 });
  await page.waitForFunction(() => ![...document.querySelectorAll('.kb-cpx b')].some(b => b.textContent === '…') && !/讀取中/.test(document.getElementById('kbGSum').textContent), null, { timeout: 20000 });
  if (w > 600) ok(await page.evaluate(() => document.querySelector('.kb-card').getBoundingClientRect().bottom <= innerHeight), '1280×900：第一排卡片完整出現在第一屏');
  const miss = await page.evaluate((id) => { const c = document.querySelector(`.kb-card[data-id="${id}"]`); return c && { px: c.querySelector('.kb-cpx').textContent, cm: c.querySelector('.kb-cm').textContent, chart: !!c.querySelector('canvas') }; }, FX.missing[0]);
  ok(miss && miss.px === '—' && /讀不到/.test(miss.cm) && !miss.chart, '讀不到資料檔的卡顯示「—」與原因、不畫圖：' + JSON.stringify(miss));
  const stale = await page.evaluate((id) => { const c = document.querySelector(`.kb-card[data-id="${id}"]`); return c && { px: c.querySelector('.kb-cpx').textContent, cm: c.querySelector('.kb-cm').textContent, chart: !!c.querySelector('canvas') }; }, FX.staleKey[0]);
  ok(stale && stale.px === '—' && /解不開/.test(stale.cm) && !stale.chart, '近期檔解不開的卡顯示「—」與原因：' + JSON.stringify(stale));
  ok(await page.evaluate(() => !!localStorage.getItem('erd-futures-key-v1') && document.getElementById('kbGLockBox').hidden), '某一檔解不開不可把整個網站上鎖');
  ok(/上漲 \d+ · 下跌 \d+ · 平 \d+/.test(await page.textContent('#kbGSum')), '漲跌家數文字');
  ok(await page.evaluate(() => document.querySelector('.kb-card[data-id="ym"] .kb-cpx .ch').className.includes('ku') || document.querySelector('.kb-card[data-id="ym"] .kb-cpx .ch').className.includes('kd')), '漲跌用 kup／kdn');
  ok(await page.evaluate(() => [...document.querySelectorAll('.kb-gh')].length >= 4 && document.querySelector('.kb-gh').textContent.startsWith('指數期貨')), '產業排序有分段小標題，期貨在最前');
  ok(await page.evaluate(() => { const c = document.querySelector('.kb-card[data-id="amd"]'); return /暫定/.test(c.querySelector('.kb-cm').textContent); }), '暫定標示保留');
  ok(await page.evaluate(() => /待確認 1 天/.test(document.querySelector('.kb-card[data-id="csco"] .kb-cm').textContent)), '待確認標示保留');
  // 3. 延遲建立：最下面的卡捲到之前沒有圖；大小與重疊
  const total = await nCards(), b0 = await built();
  const lastId = await page.evaluate(() => [...document.querySelectorAll('.kb-card')].pop().dataset.id);
  ok(b0 > 0 && b0 < total, `延遲建立：目前只建 ${b0} / ${total} 張`);
  ok(await page.evaluate((id) => !document.querySelector(`.kb-card[data-id="${id}"] canvas`), lastId), '最下面的卡在捲到之前沒有 canvas');
  await page.evaluate((id) => document.querySelector(`.kb-card[data-id="${id}"]`).scrollIntoView(), lastId);
  await page.waitForFunction((id) => document.querySelector(`.kb-card[data-id="${id}"] canvas`), lastId, { timeout: 15000 });
  ok((await bad1()).length === 0, '每張卡最多 1 張圖');
  ok(await page.evaluate(() => { const c = document.querySelector('.kb-card canvas'); const b = c.closest('.kb-cbox'); return b.getBoundingClientRect().height >= 200 && b.getBoundingClientRect().height <= 240; }), '日 K 小圖高約 220px');
  ok(await page.evaluate(() => !document.querySelector('.kb-card .fut-ltb') && !document.querySelector('.kb-card .fut-tool')), '總覽沒有畫線工具列');
  if (w > 600) ok(await page.evaluate(() => { const x = getComputedStyle(document.getElementById('kbCards')).gridTemplateColumns.split(' ').length; return x === 3; }), '1280 寬 3 欄：' + await page.evaluate(() => getComputedStyle(document.getElementById('kbCards')).gridTemplateColumns));
  else ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbCards')).gridTemplateColumns.split(' ').length === 1), '手機 1 欄');
  await page.evaluate(() => scrollTo(0, 0));
  ok((await overflow(page)) <= 1, `${tag} 整頁水平捲動 ${await overflow(page)}px`);
  // 4. 分類篩選
  const chip = await page.evaluate(() => { const c = [...document.querySelectorAll('.kb-chip')].find(x => x.textContent.startsWith('半導體')); return c && { n: +c.querySelector('span').textContent }; });
  ok(chip && chip.n > 0, '有「半導體」分類');
  await page.evaluate(() => [...document.querySelectorAll('.kb-chip')].find(x => x.textContent.startsWith('半導體')).click());
  await page.waitForFunction((n) => document.querySelectorAll('.kb-card').length === n, chip.n);
  ok(page.url().includes('g=') && decodeURIComponent(page.url()).includes('g=半導體'), '網址反映分類：' + page.url());
  ok(await page.evaluate(() => localStorage.getItem('erd-watch-filter') === '半導體'), '分類記在 erd-watch-filter');
  await page.waitForFunction(() => [...document.querySelectorAll('.kb-card')].some(c => c.querySelector('canvas')), null, { timeout: 15000 });
  await settled(page);
  const cnt = await page.evaluate(() => { const m = /上漲 (\d+) · 下跌 (\d+) · 平 (\d+)/.exec(document.getElementById('kbGSum').textContent); const cs = [...document.querySelectorAll('.kb-card')].filter(c => !['ym', 'nq', 'tx'].includes(c.dataset.id)); return { sum: m && m.slice(1).map(Number), up: cs.filter(c => c.querySelector('.ch.kup')).length, dn: cs.filter(c => c.querySelector('.ch.kdn')).length, n: cs.length, gh: document.querySelectorAll('.kb-gh').length }; });
  ok(cnt.sum && cnt.sum[0] === cnt.up && cnt.sum[1] === cnt.dn && cnt.sum[0] + cnt.sum[1] + cnt.sum[2] <= cnt.n, '篩選後家數跟著變：' + JSON.stringify(cnt));
  ok((await bad1()).length === 0 && cnt.gh === 0, '篩選後每張卡最多 1 張圖、單一分類不分段');
  if (w > 600 && scheme === 'light') await gridShot(page, 'grid-1280-light-semi.png', false);
  // 網址 ?g=指數期貨
  await page.goto(base + '/futures/?g=' + encodeURIComponent('指數期貨'), { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelectorAll('.kb-card').length === 3);
  await page.waitForFunction(() => /沒有個股/.test(document.getElementById('kbGSum').textContent), null, { timeout: 15000 });
  await page.waitForFunction(() => document.querySelectorAll('.kb-card canvas').length >= 3, null, { timeout: 15000 }).catch(async (e) => { console.log(await page.evaluate(() => document.getElementById('kbCards').innerText.slice(0, 400) + ' | ' + document.querySelectorAll('canvas').length + ' ' + localStorage.getItem('erd-futures-key-v1'))); throw e; });
  // 沒有 g：用記住的分類；選回全部
  await page.goto(base + '/futures/', { waitUntil: 'load' });   // 網址的 g 不改記住的分類；沒有 g 就用上次點選的「半導體」
  await page.waitForFunction((n) => document.querySelectorAll('.kb-card').length === n, chip.n);
  await page.evaluate(() => document.querySelector('.kb-chip[data-f="all"]').click());
  await page.waitForFunction((n) => document.querySelectorAll('.kb-card').length === n, rows);
  await page.waitForFunction(() => document.querySelectorAll('.kb-card canvas').length > 3, null, { timeout: 15000 });
  // 水平線的監聽：每張圖一個，建了又釋放不可累積（包 FUT.Lines.on 計數；從這裡起算，下面切週期時這之前建的圖都會被換掉）
  await page.evaluate(() => { const on = FUT.Lines.on; window.__lsn = 0; FUT.Lines.on = (f) => { window.__lsn++; const off = on(f); return () => { window.__lsn--; off(); }; }; });
  // 5. 週期、KD、排序：舊圖要換掉、每張卡只有 1 張圖
  await page.evaluate(() => scrollTo(0, 0)); await frames(page); await settled(page);
  await page.evaluate(() => { document.querySelectorAll('.kb-card .tv-lightweight-charts').forEach(e => { e.dataset.old = '1'; }); });
  const b1 = await built();
  await page.click('#kbGP [data-gp="W"]');
  await page.waitForFunction((n) => { const l = [...document.querySelectorAll('.kb-card .tv-lightweight-charts')]; return l.length >= n && l.every(e => !e.dataset.old); }, Math.min(b1, 3), { timeout: 20000 });
  await settled(page);
  ok(page.url().includes('p=W'), '網址記住週期');
  ok((await bad1()).length === 0 && !(await page.evaluate(() => document.querySelector('.kb-card .tv-lightweight-charts[data-old]'))), '週 K：舊圖已移除、每張卡只有 1 張圖');
  ok(await page.evaluate(() => document.querySelector('#kbGP [data-gp="W"]').getAttribute('aria-pressed') === 'true'), '週期按鈕狀態');
  await page.click('#kbGKD'); await settled(page);
  ok(await page.evaluate(() => { const b = document.querySelector('.kb-card .kb-cbox'); return b.getBoundingClientRect().height >= 300; }), 'KD 開啟後卡片變高（約 320px）');
  ok((await bad1()).length === 0 && (await built()) > 0, 'KD 切換後每張卡最多 1 張圖');
  await page.click('#kbGKD'); await page.click('#kbGP [data-gp="M"]'); await settled(page);
  await page.click('#kbGP [data-gp="D"]'); await settled(page);
  ok((await bad1()).length === 0 && (await built()) > 0 && page.url().includes('p=D'), '切回日 K');
  const leak = await page.evaluate(() => document.querySelectorAll('.tv-lightweight-charts').length - document.querySelectorAll('.kb-card .tv-lightweight-charts').length);
  ok(leak === 0, '頁面上沒有卡片以外殘留的圖：' + leak);
  await page.click('#kbGSort [data-gsort="chg"]'); await settled(page);
  const chs = await page.evaluate(() => ({ gh: document.querySelectorAll('.kb-gh').length, v: [...document.querySelectorAll('.kb-card')].map(c => c.querySelector('.kb-cpx .ch') ? parseFloat(c.querySelector('.kb-cpx .ch').textContent.replace('−', '-')) : NaN).filter(x => !isNaN(x)) }));
  ok(chs.gh === 0 && chs.v.length > 20 && chs.v.every((x, i) => !i || x <= chs.v[i - 1] + 1e-9), '漲跌幅排序：不分段、由高到低');
  // 排序後是一批新卡：IntersectionObserver 要觀察到新卡（捲到最下面那張也會建圖）
  const lastChg = await page.evaluate(() => { const c = [...document.querySelectorAll('.kb-card')].filter(x => !x.querySelector('.kb-empty')).pop(); c.scrollIntoView(); return c.dataset.id; });
  ok(await until(page, (id) => document.querySelector(`.kb-card[data-id="${id}"] canvas`), lastChg, 15000), '排序後捲到最下面的卡也會建圖：' + lastChg);
  await page.click('#kbGSort [data-gsort="sector"]'); await settled(page);
  // 6. 點卡片進單檔、回總覽
  await page.evaluate(() => scrollTo(0, 0)); await frames(page); await settled(page);
  ok(await page.evaluate(() => window.__lsn) === (await page.evaluate(() => document.querySelectorAll('.tv-lightweight-charts').length)) && (await built()) > 0, '切換週期／KD／排序後水平線監聽數＝圖數（不累積）：' + await page.evaluate(() => window.__lsn + ' / ' + document.querySelectorAll('.tv-lightweight-charts').length));
  const hl0 = await page.evaluate(() => history.length);
  await page.click('.kb-card[data-id="nvda"] .kb-ct');
  await page.waitForFunction(() => !document.getElementById('kbApp').hidden && /輝達 NVDA 日 K/.test(document.getElementById('futTitle').textContent));
  await page.waitForSelector('#futBody:not([hidden]) canvas', { timeout: 15000 });
  ok(page.url().includes('s=nvda') && page.url().includes('p=D') && await page.evaluate(() => document.getElementById('kbGrid').hidden), '點卡片進單檔，網址有 ?s=');
  ok(await page.evaluate(() => document.querySelectorAll('.kb-card canvas').length === 0), '進單檔後總覽的圖已釋放');
  ok((await overflow(page)) <= 1, `${tag} 單檔水平捲動`);
  ok((await navLinks(page)) === 'K 棒,均線與扣抵,資料來源', '單檔模式的章節導覽：' + await navLinks(page));
  ok((await page.evaluate(() => history.length)) === hl0 + 1, '從總覽點卡片進單檔要新增一筆歷史（pushState）');
  // 瀏覽器「上一頁」回總覽、「下一頁」再進單檔；單檔內換週期不新增歷史
  await page.click('.fut-ctrl [data-p="W"]'); await page.waitForFunction(() => /週 K/.test(document.getElementById('futTitle').textContent));
  ok((await page.evaluate(() => history.length)) === hl0 + 1 && page.url().includes('p=W'), '單檔內換週期用 replaceState');
  await page.goBack();
  ok(await until(page, () => !document.getElementById('kbGrid').hidden && document.getElementById('kbApp').hidden && document.querySelectorAll('.kb-card').length > 0), '上一頁回到總覽');
  ok(!page.url().includes('s=') && (await page.evaluate(() => document.querySelectorAll('#futChart .tv-lightweight-charts').length)) === 0, '上一頁回總覽：網址沒有 ?s=、單檔的圖已釋放');
  await page.waitForFunction(() => document.querySelectorAll('.kb-card canvas').length > 0, null, { timeout: 15000 });
  await page.goForward();
  ok(await until(page, () => !document.getElementById('kbApp').hidden && /輝達 NVDA 週 K/.test(document.getElementById('futTitle').textContent) && document.querySelector('#futBody:not([hidden]) #futChart canvas'), null, 15000), '下一頁再進單檔（輝達、週 K）');
  ok(await page.evaluate(() => document.querySelectorAll('.kb-card canvas').length === 0), '下一頁進單檔：總覽的圖已釋放');
  await page.click('.fut-ctrl [data-p="D"]'); await page.waitForFunction(() => /日 K/.test(document.getElementById('futTitle').textContent));
  await page.click('#kbBack');
  await page.waitForFunction(() => !document.getElementById('kbGrid').hidden && document.getElementById('kbApp').hidden);
  ok(!page.url().includes('s=') && (await page.evaluate(() => history.length)) === hl0 + 1, '回總覽後網址沒有 ?s=（退回原本那一筆，不新增歷史）');
  ok(await page.evaluate(() => document.querySelectorAll('#futChart .tv-lightweight-charts').length === 0), '回總覽時單檔的圖已釋放');
  await page.waitForFunction(() => document.querySelectorAll('.kb-card canvas').length > 0, null, { timeout: 15000 });
  await page.click('.kb-card[data-id="tsmc"] .kb-more').catch(async () => { await page.evaluate(() => document.querySelector('.kb-card[data-id="tsmc"] .kb-more').click()); });
  await page.waitForFunction(() => /台積電/.test(document.getElementById('futTitle').textContent) && !document.getElementById('kbApp').hidden);
  await page.click('#kbMode [data-mode="grid"]');
  await page.waitForFunction(() => !document.getElementById('kbGrid').hidden);
  // ?s=nvda 直接進單檔
  await page.goto(base + '/futures/?s=nvda&p=W', { waitUntil: 'load' });
  await page.waitForSelector('#futBody:not([hidden]) canvas', { timeout: 15000 });
  ok(await page.evaluate(() => document.getElementById('kbGrid').hidden && !document.getElementById('kbApp').hidden && /輝達 NVDA 週 K/.test(document.getElementById('futTitle').textContent)), '?s=nvda 直接進單檔');
  // 直接打開 ?s= 的網址按「回總覽」：新增一筆總覽，上一頁回到單檔
  await page.click('#kbBack'); await page.waitForFunction(() => !document.getElementById('kbGrid').hidden);
  await page.goBack();
  ok(await until(page, () => !document.getElementById('kbApp').hidden && /輝達 NVDA 週 K/.test(document.getElementById('futTitle').textContent) && document.querySelector('#futBody:not([hidden]) #futChart canvas'), null, 15000), '直接開 ?s= → 回總覽 → 上一頁回到單檔');
  await page.goto(base + '/futures/', { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelectorAll('.kb-card canvas').length > 0, null, { timeout: 15000 });
  // 7. 截圖
  if (shotsDir && scheme === 'light' && w > 600) { await page.evaluate(() => document.querySelector('.kb-chip[data-f="all"]').click()); await page.waitForFunction((n) => document.querySelectorAll('.kb-card').length === n, rows); await gridShot(page, 'grid-1280-light.png', true); }
  if (shotsDir && scheme === 'dark' && w < 600) await gridShot(page, 'grid-390-dark.png', false);
  ok((await overflow(page)) <= 1, `${tag} 整頁水平捲動 ${await overflow(page)}px`);
  // 8. 上鎖
  await page.click('#kbGLock'); await page.waitForSelector('#kbGLockBox form.fut-lock');
  ok(await page.evaluate(() => !document.querySelector('.kb-cpx .ch.kup, .kb-cpx .ch.kdn') && !document.querySelector('.kb-card canvas')), '上鎖後不顯示漲跌、不留圖');
  ok(errs.length === 0, '錯誤：' + errs.join(' | '));
  await ctx.close();
}

async function companyPages(browser, base, w, scheme) {
  say(`— 個股頁 ${w}px ${scheme}`);
  for (const code of ['nvda', 'tsmc', 'pltr']) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, deviceScaleFactor: 2, colorScheme: scheme });   // 每家一個全新環境（沒解鎖）
    const page = await ctx.newPage(), errs = [], kbReq = [];
    await watchErrors(page, errs);
    page.on('request', (r) => { if (/kbar\.js|futures\.js|lightweight-charts|\/data\/(kbar|futures)\//.test(r.url())) kbReq.push(r.url()); });
    // 每日收盤檔：模擬「讀到比建置版新的檔」→ render() 跑第二次；先扣住，等 K 棒展開、畫好圖再放行
    let relDaily; const held = new Promise(r => { relDaily = r; });
    await page.route(`**/data/daily/${code}.json*`, async (route) => { const r = await route.fetch(); const j = await r.json(); j.fetched = '9999-12-31T00:00:00Z'; await held; await route.fulfill({ response: r, body: JSON.stringify(j) }); });
    await page.goto(`${base}/${code}/`, { waitUntil: 'load' });
    await page.waitForSelector('#today:not([hidden])');
    // K 棒區塊預設收合：沒解鎖、沒展開 → K 棒相關 script 不能被載入，也沒有 canvas
    const kbScripts = () => page.evaluate(() => !!document.querySelector('script[src*="kbar.js"], script[src*="futures.js"], script[src*="lightweight-charts"]') || typeof KB !== 'undefined');
    const nCharts = (pg) => pg.evaluate(() => document.querySelectorAll('#dyKB .tv-lightweight-charts').length);
    ok(await page.evaluate(() => [...document.querySelectorAll('#dyK button')].map(b => b.dataset.k).join() === '1,2' && document.querySelector('#dyK [data-k="1"]').getAttribute('aria-pressed') === 'true'), code + ' 走勢圖切換只剩 收盤／本益比');
    ok(await page.evaluate(() => { const t = document.getElementById('dyKToggle'); return t && t.getAttribute('aria-expanded') === 'false' && /展開/.test(t.textContent) && document.getElementById('dyKB').hidden; }), code + ' K 棒預設收合');
    ok(!(await kbScripts()) && (await page.evaluate(() => !document.querySelector('#dyKB canvas'))), code + ' 收合時不載入 K 棒程式、沒有 canvas');
    ok(kbReq.length === 0, code + ' 收合時沒有任何 K 棒程式或資料的網路請求：' + kbReq.join(' '));
    ok(await page.evaluate(() => !document.documentElement.innerHTML.includes('const KB = (()')), code + ' kbar.js 沒有內嵌在公司頁');
    ok(await page.evaluate(() => !localStorage.getItem('erd-stock-kbar-open')), code + ' 沒有記住值＝收合');
    ok((await overflow(page)) <= 1, `${code} 收合時整頁水平捲動`);
    if (code === 'nvda') await shot(page, `stock-collapsed-${w}-${scheme}.png`, '#today');
    await page.click('#dyKToggle');
    await page.waitForSelector('#dyKB form.fut-lock', { timeout: 15000 });
    ok(await page.evaluate(() => !!document.querySelector('script[src*="kbar.js"]') && typeof KB !== 'undefined' && document.getElementById('dyKToggle').getAttribute('aria-expanded') === 'true' && /收合/.test(document.getElementById('dyKToggle').textContent)), code + ' 展開後才載入、按鈕變「收合」；未解鎖顯示解鎖表單');
    ok(await page.evaluate(() => localStorage.getItem('erd-stock-kbar-open') === '1'), code + ' 展開狀態記在 erd-stock-kbar-open');
    if (code === 'nvda') await shot(page, `stock-${w}-${scheme}-locked.png`, '#today');
    await unlock(page);
    await page.waitForSelector('#dyKB .kb-ebody:not([hidden]) canvas', { timeout: 15000 });
    ok((await nCharts(page)) === 1, code + ' 展開後 1 張圖：' + await nCharts(page));
    // render() 第二次（讀到新的每日檔）：展開的 K 棒區塊要留著、不重複
    await page.evaluate(() => { document.querySelector('#today .kpis').dataset.old = '1'; });
    relDaily();
    ok(await until(page, () => !document.querySelector('#today .kpis[data-old]')), code + ' 每日檔第二次 render');
    await until(page, () => document.querySelector('#dyKB .kb-ebody:not([hidden]) canvas'), null, 15000); await frames(page);
    ok(await page.evaluate(() => document.querySelectorAll('#dyKB').length === 1 && !document.getElementById('dyKB').hidden && document.getElementById('dyKToggle').getAttribute('aria-expanded') === 'true' && document.querySelectorAll('#dyKB .tv-lightweight-charts').length === 1), code + ' 第二次 render 後 K 棒仍展開、只有 1 個區塊 1 張圖');
    ok(/看盤頁開啟/.test(await page.textContent('#dyKB')) && (await page.getAttribute('#dyKB a.go', 'href')).includes('futures/?s=' + code), code + ' 在看盤頁開啟連結');
    await page.click('#dyKB [data-p="W"]'); await until(page, () => document.querySelector('#dyKB [data-p="W"]').getAttribute('aria-pressed') === 'true' && document.querySelector('#dyKB canvas'));
    ok(await page.evaluate(() => document.querySelector('#dyKB [data-p="W"]').getAttribute('aria-pressed') === 'true'), code + ' 切週 K');
    await page.click('#dyKB [data-p="D"]'); await until(page, () => document.querySelector('#dyKB [data-p="D"]').getAttribute('aria-pressed') === 'true' && document.querySelector('#dyKB canvas')); await frames(page);
    ok((await nCharts(page)) === 1, code + ' 切週期後仍只有 1 張圖');
    ok((await overflow(page)) <= 1, `${code} 整頁水平捲動 ${await overflow(page)}px`);
    if (code === 'nvda') await shot(page, `stock-${w}-${scheme}.png`, '#today');
    // 收合 → 圖被釋放；再展開 → 仍只有 1 張
    await page.click('#dyKToggle');
    ok(await page.evaluate(() => document.getElementById('dyKB').hidden && document.querySelectorAll('#dyKB canvas').length === 0 && document.getElementById('dyKToggle').getAttribute('aria-expanded') === 'false'), code + ' 收合要釋放圖');
    ok(await page.evaluate(() => localStorage.getItem('erd-stock-kbar-open') === '0'), code + ' 收合記為 0');
    for (let i = 0; i < 2; i++) {
      await page.click('#dyKToggle'); await page.waitForSelector('#dyKB canvas', { timeout: 15000 }); await frames(page);
      ok((await nCharts(page)) === 1, code + ' 再展開只能 1 張圖：' + await nCharts(page));
      await page.click('#dyKToggle');
    }
    await page.click('#dyKToggle'); await page.waitForSelector('#dyKB canvas', { timeout: 15000 });
    // 重新整理：記得展開，區塊接近畫面才載入
    await page.reload({ waitUntil: 'load' });
    await page.waitForSelector('#dyKToggle');
    ok(await page.evaluate(() => document.getElementById('dyKToggle').getAttribute('aria-expanded') === 'true'), code + ' 重新整理後記得展開');
    await page.evaluate(() => document.getElementById('dyKB').scrollIntoView());
    await page.waitForSelector('#dyKB .kb-ebody:not([hidden]) canvas', { timeout: 15000 });
    ok((await nCharts(page)) === 1, code + ' 重新整理後 1 張圖');
    ok((await overflow(page)) <= 1, `${code} 展開（重新整理後）整頁水平捲動`);
    // 走勢圖切換與 1/3/5 年仍可用
    await page.click('#dyK [data-k="2"]');
    ok(await page.evaluate(() => document.getElementById('dyK').querySelector('[data-k="2"]').getAttribute('aria-pressed') === 'true' && !document.querySelector('.chartbox.short').hidden), code + ' 本益比切換');
    await page.click('#dyK [data-k="1"]');
    // 收合後新開的頁面（同一個已解鎖的環境）：預設收合
    await page.click('#dyKToggle');
    const p2 = await ctx.newPage(); await watchErrors(p2, errs);
    await p2.goto(`${base}/${code}/`, { waitUntil: 'load' });
    await p2.waitForSelector('#dyKToggle');
    ok(await p2.evaluate(() => document.getElementById('dyKToggle').getAttribute('aria-expanded') === 'false' && !document.querySelector('script[src*="kbar.js"]') && !document.querySelector('#dyKB canvas')), code + ' 已解鎖也預設收合、不載入 K 棒程式');
    if (code === 'nvda') {   // 歷史檔解不開的那一家：個股頁展開後也要標示只顯示近期
      await p2.goto(`${base}/${FX.staleHist[0]}/`, { waitUntil: 'load' });
      await p2.waitForSelector('#dyKToggle'); await p2.click('#dyKToggle');
      await p2.waitForSelector('#dyKB .kb-ebody:not([hidden]) canvas', { timeout: 15000 });
      const asof = await p2.textContent('#dyKB .kb-asof');
      ok(/歷史檔讀不到，只顯示 \d{4}\/\d{2}\/\d{2} 起的近期資料/.test(asof), '個股頁歷史檔讀不到要標示：' + asof);
      await p2.click('#dyKToggle');
    }
    await p2.close();
    ok(errs.length === 0, code + ' 錯誤：' + errs.join(' | '));
    await ctx.close();
  }
}

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  try {
    for (const scheme of ['light', 'dark']) {
      for (const w of [1280, 390]) {
        await gridPage(browser, base, w, scheme);
        await watchPage(browser, base, w, scheme);
        await companyPages(browser, base, w, scheme);
      }
    }
    // 合併版 Artifact：K 棒按鈕改成連到網站；不載入站內 script
    const all = fs.readFileSync(path.join(ROOT, 'dist', 'artifacts', 'all.html'), 'utf8');
    ok(all.includes('\\"kbar\\":null,\\"kbarLink\\":\\"https://') && all.includes('/futures/?s=nvda'), '合併版 Artifact 的 D.kbar 為 null 且有 kbarLink');
    ok(!all.includes('kbar.js?v='), '合併版 Artifact 不載入站內 kbar.js');
  } catch (e) { bad++; console.log('  ✗ 測試中斷：', e && e.stack || e); }
  await browser.close(); server.close(); fs.rmSync(tmp, { recursive: true, force: true });
  console.log(bad ? `\n✗ ${bad} 項失敗` : '\n✓ 全部通過');
  process.exit(bad ? 1 : 0);
})();
