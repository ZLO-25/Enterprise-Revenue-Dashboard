/* 看盤頁／個股頁 K 棒的瀏覽器測試（CI 用；用合成資料，不碰 repo 的 data/）。
   用法（先 python3 tools/build.py）：
     node tools/tests/kbar_browser.cjs [--shots <資料夾>]
   需要：playwright（node 套件，NODE_PATH 或本機 node_modules 找得到）與 chromium（PW_CHROMIUM 指定執行檔；沒指定就用 playwright 自己的）。
   流程：呼叫 tools/tests/kbar_fixture.py 在臨時資料夾產生合成期貨與個股 K 棒檔（含測試用 key.json 與密碼），
   起一個本機伺服器：網站檔案取自 repo，/data/futures/ 與 /data/kbar/ 改取臨時資料夾。
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

async function watchPage(browser, base, w, scheme) {
  const tag = `看盤頁 ${w}px ${scheme}`;
  say('— ' + tag);
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, deviceScaleFactor: 2, colorScheme: scheme });
  const page = await ctx.newPage(), errs = [];
  await watchErrors(page, errs);
  // 1. 未解鎖
  await page.goto(base + '/futures/', { waitUntil: 'load' });
  await page.waitForSelector('form.fut-lock');
  await page.waitForFunction(() => document.querySelectorAll('.kb-row').length >= 20);
  await page.waitForTimeout(500);
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
  ok(/上漲 \d+ · 下跌 \d+ · 平 \d+/.test(await page.textContent('#kbSum')), '漲跌家數文字');
  const missing = await page.evaluate((id) => { const r = document.querySelector(`.kb-row[data-id="${id}"]`); return r && { ch: r.querySelector('.ch').textContent, px: r.querySelector('.px').textContent, title: r.title }; }, FX.missing[0]);
  ok(missing && missing.ch === '—' && missing.px === '—' && /讀不到/.test(missing.title), '讀不到資料檔的列要顯示「—」與原因：' + JSON.stringify(missing));
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
  for (let i = 0; i < 6; i++) { await page.keyboard.press(i % 2 ? 'ArrowUp' : 'ArrowDown'); await page.waitForTimeout(120); }
  await page.waitForTimeout(400);
  const leak = await page.evaluate(() => { const c = document.getElementById('futChart'); return { charts: c.querySelectorAll('.tv-lightweight-charts').length, tb: c.querySelectorAll('.fut-ltb').length }; });
  ok(leak.charts === 1 && leak.tb === 1, '切換多次後只能留一張圖（舊圖要釋放）：' + JSON.stringify(leak));
  await page.keyboard.press('ArrowUp'); await page.waitForTimeout(200);
  ok((await sel()) === before, '↑ 要回到原商品');
  // 排序切換
  if (w < 900) await page.click('#kbTog');
  await page.click('#kbSort [data-sort="chg"]'); await page.waitForTimeout(150);
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
    await page.waitForTimeout(150);
  }
  ok(/日盤/.test(await page.textContent('#futSub')) && /日盤（一般交易時段/.test(await page.textContent('#futSrc')), 'TX 來源說明沿用期貨頁的寫法');
  // 暫定、待確認
  await pick(page, 'amd');
  await page.waitForFunction(() => /超微/.test(document.getElementById('futTitle').textContent) || /超微/.test(document.querySelector('.kb-row[aria-selected="true"] .n').textContent));
  await page.waitForTimeout(300);
  ok(/暫定/.test(await page.textContent('#futSub')) && /暫定/.test(await page.textContent('#futSrc')), '暫定標示');
  await pick(page, 'csco'); await page.waitForTimeout(500);
  ok(/待確認：1 天的 K 棒沒有採用/.test(await page.textContent('#futSrc')), '待確認清單');
  await pick(page, 'spcx'); await page.waitForTimeout(500);
  ok(/SpaceX/.test(await page.textContent('#futTitle')), '上市不滿一年（沒有歷史檔）也能畫：' + await title(page));
  // 深連結
  for (const [s, p, expect] of [['ym', 'W', /小道瓊期貨 週 K/], ['nq', 'M', /小那指期貨 月 K/], ['tsmc', 'D', /台積電 \S+ 日 K/]]) {
    await page.goto(`${base}/futures/?s=${s}&p=${p}`, { waitUntil: 'load' });
    await page.waitForFunction(() => document.querySelector('#futBody:not([hidden]) canvas'), null, { timeout: 15000 });
    await page.waitForFunction((r) => new RegExp(r).test(document.getElementById('futTitle').textContent), expect.source);
  }
  // 選到的商品記住
  await page.goto(base + '/futures/', { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelector('.kb-row[aria-selected="true"]'));
  ok((await sel()) === 'tsmc', '記住上次看的商品：' + await sel());
  // 窄螢幕的清單面板
  if (w < 900) {
    ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbPanel')).display === 'none'), '窄螢幕清單預設收起');
    await page.click('#kbTog'); ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbPanel')).display !== 'none'), '按鈕展開清單');
    await shot(page, `watch-${w}-${scheme}-list.png`);
    await page.click('.kb-row[data-id="nvda"]'); await page.waitForTimeout(400);
    ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbPanel')).display === 'none'), '選了商品後收起');
    await page.click('#kbNext'); await page.waitForTimeout(300);
  } else {
    ok(await page.evaluate(() => getComputedStyle(document.getElementById('kbTog')).display === 'none' && getComputedStyle(document.getElementById('kbPanel')).display !== 'none'), '寬螢幕清單固定顯示');
    await pick(page, 'nvda');
  }
  await page.waitForFunction(() => /\S+ \S+ 日 K/.test(document.getElementById('futTitle').textContent));
  await page.waitForTimeout(600);
  ok((await overflow(page)) <= 1, `${tag} 整頁水平捲動 ${await overflow(page)}px`);
  await shot(page, `watch-${w}-${scheme}.png`);
  // 上鎖
  await page.click('#futLockBtn'); await page.waitForSelector('form.fut-lock');
  ok(await page.evaluate(() => !document.querySelector('.kb-row .ch.kup, .kb-row .ch.kdn')), '上鎖後不顯示漲跌');
  ok(errs.length === 0, '錯誤：' + errs.join(' | '));
  await ctx.close();
}

async function companyPages(browser, base, w, scheme) {
  say(`— 個股頁 ${w}px ${scheme}`);
  for (const code of ['nvda', 'tsmc', 'pltr']) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, deviceScaleFactor: 2, colorScheme: scheme });   // 每家一個全新環境（沒解鎖）
    const page = await ctx.newPage(), errs = [];
    await watchErrors(page, errs);
    await page.goto(`${base}/${code}/`, { waitUntil: 'load' });
    await page.waitForSelector('#today:not([hidden])');
    // 沒解鎖：預設收盤折線；K 棒相關 script 不能被載入（延遲載入）
    ok(await page.evaluate(() => document.querySelector('#dyK [data-k="1"]').getAttribute('aria-pressed') === 'true'), code + ' 未解鎖預設收盤折線');
    ok(await page.evaluate(() => !document.querySelector('script[src*="kbar.js"], script[src*="futures.js"], script[src*="lightweight-charts"]') && typeof KB === 'undefined'), code + ' 沒點 K 棒前不載入 K 棒程式');
    ok(await page.evaluate(() => !document.documentElement.innerHTML.includes('const KB = (()')), code + ' kbar.js 沒有內嵌在公司頁');
    await page.click('#dyK [data-k="3"]');
    await page.waitForSelector('#dyKB form.fut-lock', { timeout: 15000 }).catch(async (e) => { console.log('  state:', errs.join('|'), await page.evaluate(() => document.getElementById('dyKB').outerHTML.slice(0, 200) + ' k=' + document.querySelector('#dyK [aria-pressed=true]').textContent + ' scripts=' + [...document.scripts].map(x => x.src).filter(Boolean).join(',') + ' rect=' + JSON.stringify(document.getElementById('dyKB').getBoundingClientRect()))); throw e; });
    ok(await page.evaluate(() => !!document.querySelector('script[src*="kbar.js"]') && typeof KB !== 'undefined'), code + ' 點 K 棒後才載入');
    if (code === 'nvda') await shot(page, `stock-${w}-${scheme}-locked.png`, '#today');
    await unlock(page);
    await page.waitForSelector('#dyKB .kb-ebody:not([hidden]) canvas', { timeout: 15000 });
    ok(/看盤頁開啟/.test(await page.textContent('#dyKB')) && (await page.getAttribute('#dyKB a.go', 'href')).includes('futures/?s=' + code), code + ' 在看盤頁開啟連結');
    await page.click('#dyKB [data-p="W"]'); await page.waitForTimeout(200);
    ok(await page.evaluate(() => document.querySelector('#dyKB [data-p="W"]').getAttribute('aria-pressed') === 'true'), code + ' 切週 K');
    await page.click('#dyKB [data-p="D"]');
    ok(await page.evaluate(() => document.getElementById('dyR').hidden && document.querySelector('.chartbox.short').hidden), code + ' K 棒檢視要藏起 1/3/5 年與折線');
    ok((await overflow(page)) <= 1, `${code} 整頁水平捲動 ${await overflow(page)}px`);
    if (code === 'nvda') await shot(page, `stock-${w}-${scheme}.png`, '#today');
    // 切回折線
    await page.click('#dyK [data-k="1"]'); await page.waitForTimeout(300);
    ok(await page.evaluate(() => document.getElementById('dyKB').hidden && !document.querySelector('.chartbox.short').hidden), code + ' 切回收盤折線');
    // 已解鎖的新頁面：預設 K 棒
    const p2 = await ctx.newPage(); await watchErrors(p2, errs);
    await p2.goto(`${base}/${code}/`, { waitUntil: 'load' });
    await p2.waitForSelector('#dyKB', { state: 'attached' });
    await p2.evaluate(() => document.getElementById('dyKB').scrollIntoView());   // 預設 K 棒是等區塊接近畫面才載入
    await p2.waitForSelector('#dyKB .kb-ebody:not([hidden]) canvas', { timeout: 15000 });
    ok(await p2.evaluate(() => document.querySelector('#dyK [data-k="3"]').getAttribute('aria-pressed') === 'true'), code + ' 已解鎖預設 K 棒');
    ok((await overflow(p2)) <= 1, `${code} 預設 K 棒時整頁水平捲動`);
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
