/* 小道瓊、小那指期貨 K 棒：解密、合成週 K／月 K、指標計算、首頁小卡、K 棒圖。
   資料：data/futures/<代號>.enc.json（AES-256-GCM 加密；金鑰 = PBKDF2-SHA256(密碼, data/futures/key.json 的 salt)）
   解鎖後把推導出的金鑰存在這台裝置的 localStorage，之後不用再輸入密碼；換密碼後解不開會自動要求重新輸入。
   指標口徑（與台灣看盤軟體一致）：
     MA N  = 最近 N 根收盤價的簡單平均（週 K 的 MA5 = 5 週）
     扣抵值 = 下一根 K 棒產生時，MA N 會丟掉的那一根的收盤價 = 倒數第 N 根的收盤價
     KD(9,3,3)：RSV = (收 − 9 根最低) ÷ (9 根最高 − 9 根最低) × 100；K = 前K×2/3 + RSV×1/3；D = 前D×2/3 + K×1/3；起始 K = D = 50 */
const FUT = (() => {
  const KEY_LS = 'erd-futures-key-v1';
  const MAS = [5, 10, 20, 50, 100];
  const MA_COLOR = (n) => ({ 5: '--s4', 10: '--s5', 20: '--s1', 50: '--s7', 100: '--s2' })[n];
  const b64 = (s) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const ub64 = (u) => btoa(String.fromCharCode(...new Uint8Array(u)));
  const ls = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
               set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 私密視窗：只在這次有效 */ } },
               del(k) { try { localStorage.removeItem(k); } catch (e) { } } };
  let memKey = null;
  const cache = {};

  async function getJSON(url) { const r = await fetch(url, { cache: 'no-cache' }); if (!r.ok) throw new Error(url + ' ' + r.status); return r.json(); }
  async function keyFromStore() {
    if (memKey) return memKey;
    const raw = ls.get(KEY_LS); if (!raw) return null;
    memKey = await crypto.subtle.importKey('raw', b64(raw), 'AES-GCM', false, ['decrypt']);
    return memKey;
  }
  async function unlock(base, password) {
    const kp = await getJSON(base + 'key.json');
    const pk = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits']);
    const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: b64(kp.salt), iterations: kp.iter }, pk, 256);
    const key = await crypto.subtle.importKey('raw', bits, 'AES-GCM', false, ['decrypt']);
    const meta = await getJSON(base + 'ym.enc.json');
    await decrypt(meta, key);                         // 密碼錯會在這裡丟出錯誤
    memKey = key; ls.set(KEY_LS, ub64(bits));
    return true;
  }
  function lock() { memKey = null; ls.del(KEY_LS); Object.keys(cache).forEach(k => delete cache[k]); }
  async function decrypt(file, key) {
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(file.iv) }, key, b64(file.ct));
    const ds = new Blob([plain]).stream().pipeThrough(new DecompressionStream('deflate'));
    return JSON.parse(await new Response(ds).text());
  }
  async function meta(base, code) { return getJSON(base + code + '.enc.json'); }
  /* 讀取並解密；沒有金鑰回傳 null；金鑰錯（例如換了密碼）會清掉記住的金鑰並回傳 null */
  async function load(base, code) {
    if (cache[code]) return cache[code];
    const key = await keyFromStore(); if (!key) return null;
    const file = await meta(base, code);
    try { cache[code] = await decrypt(file, key); } catch (e) { lock(); return null; }
    return cache[code];
  }

  /* ---------- 資料整理 ---------- */
  const toBars = (d) => d.bars.map(([t, o, h, l, c, v]) => ({ t, o, h, l, c, v }));  // v = null：來源沒有成交量
  const monday = (t) => { const d = new Date(t + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return d.toISOString().slice(0, 10); };
  function aggregate(bars, p) {
    if (p === 'D') return bars;
    const key = p === 'W' ? (b) => monday(b.t) : (b) => b.t.slice(0, 7);
    const out = []; let cur = null, k0 = null;
    for (const b of bars) {
      const k = key(b);
      if (k !== k0) { cur = { t: b.t, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v, last: b.t }; out.push(cur); k0 = k; }
      else { cur.h = Math.max(cur.h, b.h); cur.l = Math.min(cur.l, b.l); cur.c = b.c; cur.v = cur.v == null || b.v == null ? null : cur.v + b.v; cur.last = b.t; }
    }
    return out;
  }
  /* 最後一根週 K／月 K 是否已經收完（最後一天是星期五／當月最後一個平日）；假日造成的例外會標「可能」 */
  function periodDone(last, p) {
    if (p === 'D') return true;
    const d = new Date(last + 'T00:00:00Z');
    if (p === 'W') return d.getUTCDay() === 5;
    const n = new Date(d); do { n.setUTCDate(n.getUTCDate() + 1); } while (n.getUTCDay() === 0 || n.getUTCDay() === 6);
    return n.getUTCMonth() !== d.getUTCMonth();
  }
  function sma(cl, n) { const out = Array(cl.length).fill(null); let s = 0; for (let i = 0; i < cl.length; i++) { s += cl[i]; if (i >= n) s -= cl[i - n]; if (i >= n - 1) out[i] = s / n; } return out; }
  function kd(bars, n = 9) {
    const K = [], D = []; let k = 50, d = 50;
    for (let i = 0; i < bars.length; i++) {
      if (i < n - 1) { K.push(null); D.push(null); continue; }
      let hi = -Infinity, lo = Infinity; for (let j = i - n + 1; j <= i; j++) { hi = Math.max(hi, bars[j].h); lo = Math.min(lo, bars[j].l); }
      const rsv = hi === lo ? 50 : (bars[i].c - lo) / (hi - lo) * 100;
      k = k * 2 / 3 + rsv / 3; d = d * 2 / 3 + k / 3; K.push(k); D.push(d);
    }
    return { K, D };
  }
  /* 扣抵：MA N 下一根會丟掉的那一根 = bars[len − N] */
  function deduct(bars, n) { const i = bars.length - n; return i >= 0 ? { i, t: bars[i].t, c: bars[i].c } : null; }
  function study(bars) {
    const cl = bars.map(b => b.c), ma = {}, ded = {};
    MAS.forEach(n => { ma[n] = sma(cl, n); ded[n] = deduct(bars, n); });
    return { ma, ded, ...kd(bars) };
  }
  function summary(d) {
    const bars = toBars(d), st = study(bars), i = bars.length - 1, b = bars[i], p = bars[i - 1];
    return { d, bars, b, chg: p ? (b.c / p.c - 1) * 100 : null, ma20: st.ma[20][i], K: st.K[i], D: st.D[i], spark: bars.slice(-60).map(x => x.c) };
  }

  /* ---------- 顯示小工具 ---------- */
  const fmt = (n, dp = 2) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  const dp = (code) => code === 'ym' ? 0 : 2;
  const dstr = (t) => t.replace(/-/g, '/');
  function fresh(lastDate) {
    // 台北早上看到的應該是美國「前一個交易日」；超過 4 天沒新 K 棒（連假除外）就提醒
    const days = Math.round((Date.now() - new Date(lastDate + 'T21:00:00Z')) / 864e5);
    return days <= 4 ? { status: 'fresh', label: '最新', text: '資料到前一個交易日' } : { status: 'aging', label: `${days} 天未更新`, text: '每日更新可能失敗，請看 GitHub Actions' };
  }
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const badge = (F) => `<span class="fresh fresh-${F.status}" title="${F.text}">${F.label}</span>`;
  function spark(vals, color) {
    const w = 240, h = 44, lo = Math.min(...vals), hi = Math.max(...vals), sx = w / (vals.length - 1), sy = (v) => h - 3 - (v - lo) / ((hi - lo) || 1) * (h - 6);
    return `<svg class="fut-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke" points="${vals.map((v, i) => (i * sx).toFixed(1) + ',' + sy(v).toFixed(1)).join(' ')}"/></svg>`;
  }

  /* ---------- 解鎖表單（首頁與 K 棒頁共用） ---------- */
  function lockForm(el, base, onOk) {
    el.innerHTML = `<form class="fut-lock" autocomplete="on">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>
      <span class="t">這一區只給本人看，請輸入密碼。這台裝置之後會自動解鎖。</span>
      <input type="text" name="username" value="futures" autocomplete="username" hidden>
      <input type="password" name="password" autocomplete="current-password" placeholder="密碼" aria-label="期貨區密碼" required>
      <button type="submit" class="go">解鎖</button>
      <span class="err" role="alert"></span></form>`;
    const f = el.querySelector('form');
    f.addEventListener('submit', async (e) => {
      e.preventDefault(); const btn = f.querySelector('button'), err = f.querySelector('.err');
      btn.disabled = true; err.textContent = '解鎖中…';
      try { await unlock(base, f.password.value); err.textContent = ''; onOk(); }
      catch (x) { err.textContent = x && x.name === 'OperationError' ? '密碼不對，請再試一次。' : '讀不到資料（' + (x.message || x) + '）'; }
      finally { btn.disabled = false; }
    });
  }

  /* ---------- 畫一張 K 棒圖（首頁與 K 棒頁共用）：K 棒＋均線，選用成交量，最下方 KD ---------- */
  function chartInto(box, d, bars, S, o) {
    const LW = window.LightweightCharts, q = dp(d.code);
      const ink = T('--ink-2'), grid = T('--grid'), up = T('--kup'), dn = T('--kdn');
      const chart = LW.createChart(box, {
        autoSize: true,
        layout: { background: { color: 'transparent' }, textColor: T('--tick'), fontFamily: 'IBM Plex Mono, Noto Sans TC, monospace', fontSize: 12, attributionLogo: true, panes: { separatorColor: T('--line'), enableResize: false } },
        grid: { vertLines: { color: grid }, horzLines: { color: grid } },
        rightPriceScale: { borderColor: T('--axis') }, timeScale: { borderColor: T('--axis'), rightOffset: 4, minBarSpacing: 0.5 },
        crosshair: { mode: 0 }, localization: { locale: 'zh-TW' },
      });
      const toT = (b) => b.t;
      const candle = chart.addSeries(LW.CandlestickSeries, { upColor: up, downColor: dn, borderUpColor: up, borderDownColor: dn, wickUpColor: up, wickDownColor: dn, priceLineVisible: false, priceFormat: { type: 'custom', formatter: (v) => fmt(v, q), minMove: q ? 0.25 : 1 } }, 0);
      candle.priceScale().applyOptions({ mode: o.p === 'M' ? 1 : 0 });   // 月 K 用對數刻度，20 年漲幅才看得清楚
      candle.setData(bars.map(b => ({ time: toT(b), open: b.o, high: b.h, low: b.l, close: b.c })));
      const maSeries = {};
      MAS.forEach(n => { if (!o.mas.has(n)) return; const s = chart.addSeries(LW.LineSeries, { color: T(MA_COLOR(n)), lineWidth: 2, priceFormat: { type: 'custom', formatter: (v) => fmt(v, q) }, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }, 0);
        s.setData(bars.map((b, i) => S.ma[n][i] == null ? { time: toT(b) } : { time: toT(b), value: S.ma[n][i] })); maSeries[n] = s; });
      /* 扣抵三角（K 棒下方，顏色 = 均線顏色）＋ 推算換月日（只在日 K） */
      const mk = [];
      if (o.marks) MAS.forEach(n => { const x = S.ded[n]; if (x && o.mas.has(n)) mk.push({ time: x.t, position: 'belowBar', shape: 'arrowUp', color: T(MA_COLOR(n)), text: '扣' + n }); });
      const have = new Set(bars.map(b => b.t));
      if (o.marks && o.p === 'D') (d.rolls || []).forEach(r => { if (have.has(r.date)) mk.push({ time: r.date, position: 'aboveBar', shape: 'circle', color: T('--muted'), text: '換月', size: 0.6 }); });
      mk.sort((a, b) => a.time < b.time ? -1 : a.time > b.time ? 1 : 0);
      LW.createSeriesMarkers(candle, mk);
      let pane = 1;
      if (o.vol) {
        const vs = chart.addSeries(LW.HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, pane++);
        vs.setData(bars.map(b => b.v == null ? { time: toT(b) } : { time: toT(b), value: b.v, color: tint(b.c >= b.o ? up : dn, 0.55) }));
      }
      const kdPane = pane;
      const kS = chart.addSeries(LW.LineSeries, { color: T('--s1'), lineWidth: 2, priceLineVisible: false, lastValueVisible: true, priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }, kdPane);
      const dS = chart.addSeries(LW.LineSeries, { color: T('--s2'), lineWidth: 2, priceLineVisible: false, lastValueVisible: true, priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }, kdPane);
      kS.setData(bars.map((b, i) => S.K[i] == null ? { time: toT(b) } : { time: toT(b), value: S.K[i] }));
      dS.setData(bars.map((b, i) => S.D[i] == null ? { time: toT(b) } : { time: toT(b), value: S.D[i] }));
      [20, 80].forEach(v => kS.createPriceLine({ price: v, color: T('--axis'), lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
      const panes = chart.panes();
      panes[0].setStretchFactor(o.vol ? 0.64 : 0.74); if (o.vol) panes[1].setStretchFactor(0.11); panes[kdPane].setStretchFactor(0.25);
      const n = bars.length, show = o.show || { D: 160, W: 150, M: 160 }[o.p];
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - show), to: n + 3 });
      /* 首頁小圖：滑鼠滾輪／雙指縮放、按住拖曳平移；手機上下滑動仍是捲動頁面 */
      if (o.compact) chart.applyOptions({ handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: false, vertTouchDrag: false }, handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: false, axisDoubleClickReset: true }, crosshair: { mode: 2 } });
      return chart;
  }

  /* ---------- 首頁：指數期貨區（可收合）：兩張 K 棒圖（K 棒、均線、KD），數值與扣抵在 K 棒頁 ---------- */
  const OPEN_LS = 'erd-futures-open';
  async function home(sec, base, link) {
    const el = sec.querySelector('#futHome'), tg = sec.querySelector('#futToggle');
    let st = { p: 'D' }, charts = [], ready = false;
    const isOpen = () => ls.get(OPEN_LS) !== '0';
    const setOpen = (v) => { ls.set(OPEN_LS, v ? '1' : '0'); tg.setAttribute('aria-expanded', String(v)); tg.innerHTML = v ? '收合 <span aria-hidden="true">▴</span>' : '展開 <span aria-hidden="true">▾</span>'; el.hidden = !v; if (v && !ready) render(); };
    tg.addEventListener('click', () => setOpen(!isOpen()));
    async function render() {
      ready = true;
      let metas;
      try { metas = await Promise.all(['ym', 'nq'].map(c => meta(base, c))); }
      catch (e) { el.innerHTML = `<p class="fut-note">目前讀不到期貨資料（第一次資料還在產生，或這裡不是網站版）。請到 <a href="${link}" target="_blank" rel="noopener">網站的 K 棒頁</a> 查看。</p>`; return; }
      const datas = await Promise.all(['ym', 'nq'].map(c => load(base, c)));
      if (datas.some(d => !d)) {
        el.innerHTML = `<div class="fut-lockbox"></div><p class="fut-note">${metas.map(m => `${m.name}期貨資料截至 ${dstr(m.lastDate)}`).join('；')}，解鎖後顯示。</p>`;
        lockForm(el.querySelector('.fut-lockbox'), base, () => { ready = false; render(); });
        return;
      }
      const legend = MAS.map(n => `<span><i style="background:${T(MA_COLOR(n))}"></i>MA${n}</span>`).join('') + `<span><i style="background:${T('--s1')}"></i>K</span><span><i style="background:${T('--s2')}"></i>D</span>`;
      el.innerHTML = `<div class="fut-ctrl"><div class="seg" role="group" aria-label="週期">${['D', 'W', 'M'].map(p => `<button type="button" data-p="${p}" aria-pressed="${p === st.p}">${{ D: '日K', W: '週K', M: '月K' }[p]}</button>`).join('')}</div><div class="fut-leg">${legend}</div><span class="fut-hint">滑鼠滾輪縮放、按住拖曳左右移動</span></div>
        <div class="fut-cards">${datas.map(d => `<article class="co fut-co" data-code="${d.code}">
          <div class="co-top"><h2>${d.name}期貨<span class="code">${d.exchange} · 連續近月</span></h2>${badge(fresh(d.lastDate))}</div>
          <div class="fut-px"></div>
          <div class="fut-mini"></div>
          <div class="foot"><span>資料截至 ${dstr(d.lastDate)}</span><a class="go" href="${link}?s=${d.code}">看數值與扣抵 →</a></div>
        </article>`).join('')}</div>`;
      el.querySelector('.fut-ctrl').addEventListener('click', (e) => { const b = e.target.closest('button[data-p]'); if (!b) return; st.p = b.dataset.p; el.querySelectorAll('[data-p]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.p === st.p))); draw(datas); });
      draw(datas);
    }
    function draw(datas) {
      charts.forEach(c => c.remove()); charts = [];
      datas.forEach(d => {
        const card = el.querySelector(`[data-code="${d.code}"]`), bars = aggregate(toBars(d), st.p), S = study(bars), b = bars[bars.length - 1], pv = bars[bars.length - 2];
        const ch = pv ? (b.c / pv.c - 1) * 100 : null, up = ch >= 0, unit = { D: '日', W: '週', M: '月' }[st.p];
        card.querySelector('.fut-px').innerHTML = `<b>${fmt(b.c, dp(d.code))}</b><span class="${up ? 'kup' : 'kdn'}">${ch == null ? '' : (up ? '▲' : '▼') + ' ' + sp(ch, 2)}</span><small>較上一${unit}</small>`;
        charts.push(chartInto(card.querySelector('.fut-mini'), d, bars, S, { p: st.p, mas: new Set(MAS), vol: false, marks: false, show: { D: 120, W: 104, M: 120 }[st.p], compact: true }));
      });
    }
    const redraw = () => { if (ready && charts.length) draw(['ym', 'nq'].map(c => cache[c])); };
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redraw);
    new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    setOpen(isOpen());
  }

  /* ---------- K 棒頁 ---------- */
  function page(root, base) {
    const q = new URLSearchParams(location.search);
    const st = { code: q.get('s') === 'nq' ? 'nq' : 'ym', p: { D: 'D', W: 'W', M: 'M' }[q.get('p')] || 'D', mas: new Set(MAS), vol: true };
    const $r = (s) => root.querySelector(s);
    let chart = null;
    async function go() {
      const d = await load(base, st.code);
      if (!d) { $r('#futBody').hidden = true; $r('#futLock').hidden = false; lockForm($r('#futLock'), base, go); return; }
      $r('#futLock').hidden = true; $r('#futBody').hidden = false;
      history.replaceState(null, '', `?s=${st.code}&p=${st.p}`);
      draw(d);
    }
    function sync() {
      root.querySelectorAll('[data-code]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.code === st.code)));
      root.querySelectorAll('[data-p]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.p === st.p)));
      root.querySelectorAll('[data-ma]').forEach(b => b.setAttribute('aria-pressed', String(st.mas.has(+b.dataset.ma))));
      $r('#futVol').setAttribute('aria-pressed', String(st.vol));
    }
    function draw(d) {
      sync();
      const LW = window.LightweightCharts, bars = aggregate(toBars(d), st.p), S = study(bars), q = dp(d.code);
      const done = periodDone(bars[bars.length - 1].last || bars[bars.length - 1].t, st.p);
      const pName = { D: '日 K', W: '週 K', M: '月 K' }[st.p];
      $r('#futTitle').textContent = `${d.name}期貨 ${pName}`;
      $r('#futSub').textContent = `${d.exchange} 連續近月合約（未調整）· 資料 ${dstr(d.firstDate)} – ${dstr(d.lastDate)}` + (done ? '' : `· 最後一根${pName.replace(' K', '')}尚未收完，只算到 ${dstr(d.lastDate)}`);
      if (chart) { chart.remove(); chart = null; }
      chart = chartInto($r('#futChart'), d, bars, S, { p: st.p, mas: st.mas, vol: st.vol, marks: true });
      const n = bars.length;
      /* 十字游標所在那一根的數值 */
      const idx = Object.fromEntries(bars.map((b, i) => [b.t, i]));
      const leg = (i) => {
        const b = bars[i], p = bars[i - 1], ch = p ? (b.c / p.c - 1) * 100 : null;
        $r('#futLeg').innerHTML = `<span class="d">${dstr(b.t)}${st.p !== 'D' && b.last && b.last !== b.t ? '–' + dstr(b.last).slice(5) : ''}</span>` +
          `<span>開 <b>${fmt(b.o, q)}</b></span><span>高 <b>${fmt(b.h, q)}</b></span><span>低 <b>${fmt(b.l, q)}</b></span><span>收 <b class="${ch >= 0 ? 'kup' : 'kdn'}">${fmt(b.c, q)}</b> ${ch == null ? '' : sp(ch, 2)}</span>` +
          MAS.filter(n => st.mas.has(n)).map(n => `<span><i style="background:${T(MA_COLOR(n))}"></i>MA${n} ${fmt(S.ma[n][i], q)}</span>`).join('') +
          `<span><i style="background:${T('--s1')}"></i>K ${fmt(S.K[i], 1)}</span><span><i style="background:${T('--s2')}"></i>D ${fmt(S.D[i], 1)}</span>`;
      };
      leg(n - 1);
      chart.subscribeCrosshairMove(p => { const i = p && p.time != null ? idx[typeof p.time === 'string' ? p.time : `${p.time.year}-${String(p.time.month).padStart(2, '0')}-${String(p.time.day).padStart(2, '0')}`] : null; leg(i == null ? n - 1 : i); });
      /* 均線與扣抵表 */
      const last = bars[n - 1];
      $r('#futMaTbl').innerHTML = `<thead><tr><th>均線</th><th>目前</th><th>扣抵值</th><th>扣抵那一根</th><th>最新收盤 − 扣抵值</th><th class="txt">若下一根收盤跟最新收盤一樣</th></tr></thead><tbody>` +
        MAS.map(n => { const x = S.ded[n], m = S.ma[n][bars.length - 1]; if (!x || m == null) return `<tr><td><i class="dot" style="background:${T(MA_COLOR(n))}"></i>MA${n}</td><td colspan="5" class="txt">資料不足 ${n} 根</td></tr>`;
          const diff = last.c - x.c, nx = m + diff / n;
          return `<tr><td><i class="dot" style="background:${T(MA_COLOR(n))}"></i>MA${n}</td><td>${fmt(m, q)}</td><td>${fmt(x.c, q)}</td><td>${dstr(x.t)}</td><td class="${diff >= 0 ? 'kup' : 'kdn'}">${diff >= 0 ? '+' : '−'}${fmt(Math.abs(diff), q)}</td><td class="txt">${diff > 0 ? '均線上揚' : diff < 0 ? '均線下彎' : '均線持平'}，變成 ${fmt(nx, q)}</td></tr>`; }).join('') + '</tbody>';
      /* 來源與待確認 */
      const cr = d.cross || {}, cme = (d.cme || []).filter(x => x.ok != null);
      const checked = cr.ok || cme.length;
      $r('#futSrc').innerHTML = `<li>價格：<a href="${d.source.url}" target="_blank" rel="noopener">${esc(d.source.n)}</a>，每天台北 08:30 自動抓前一個交易日（這次抓取：${esc(d.fetchedAt.replace('T', ' ').slice(0, 16))} UTC）。延遲資料，只供研究，不能拿來下單。</li>` +
        `<li>交叉核對：` + (cr.ok ? `<a href="${d.check.url}" target="_blank" rel="noopener">${esc(d.check.n)}</a> 收盤價比對 ${cr.compared} 天，差超過 0.1% 的有 ${cr.mismatch} 天（其中 ${cr.mismatchInRollWindow} 天在換月期間），最大差 ${cr.maxDiffPct}%。` : '') +
        (cme.length ? `CME 官方結算價比對最近 ${cme.length} 天，${cme.filter(x => x.ok).length} 天一致（差 ≤ 0.1%）。` : '') +
        (checked ? '' : `<span class="pend">待確認：這次兩個核對來源（Stooq、CME 官網）都擋住自動抓取，價格只有 Yahoo 單一來源。</span>`) + `</li>` +
        `<li>收盤價：用 Yahoo 的日收盤價。它是否等於 CME 官方結算價：待確認。成交量顯示空白的日子是來源沒有提供成交量。</li>` +
        `<li>換月：圖上「換月」圓點是依 CME 慣例（到期日前 8 天）推算的日期，不是來源公布的日期。連續合約沒有做價格調整，換月時會有小跳空。</li>` +
        `<li>週 K、月 K 由日 K 合成；MA 為收盤價簡單平均，KD 為 (9,3,3) 台灣算法，扣抵值為下一根會被扣掉的那根收盤價。</li>` +
        (d.pending && d.pending.length ? `<li><details><summary class="pend">待確認：${d.pending.length} 天的 K 棒沒有採用（點開看日期與原因）</summary><ul>${d.pending.map(p => `<li>${dstr(p.date)}：${esc(p.reason)}</li>`).join('')}</ul></details></li>` : '');
    }
    root.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b || !b.closest('.fut-ctrl')) return;
      if (b.dataset.code) st.code = b.dataset.code; else if (b.dataset.p) st.p = b.dataset.p;
      else if (b.dataset.ma) { const n = +b.dataset.ma; st.mas.has(n) ? st.mas.delete(n) : st.mas.add(n); }
      else if (b.id === 'futVol') st.vol = !st.vol;
      else if (b.id === 'futLockBtn') { lock(); }
      go();
    });
    root.querySelector('#futMaBtns').innerHTML = MAS.map(n => `<button type="button" data-ma="${n}" aria-pressed="true"><i style="background:${T(MA_COLOR(n))}"></i>${n}</button>`).join('');
    const redraw = () => { if (cache[st.code]) draw(cache[st.code]); };
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redraw);
    new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    go();
  }

  return { unlock, lock, load, meta, aggregate, study, sma, kd, deduct, summary, periodDone, home, page, MAS };
})();
