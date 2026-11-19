/* 看盤 K 棒：個股（companies.json 裡有 price.yahoo 的公司）＋指數期貨，共用 assets/futures.js（FUT）的解密、指標、K 棒圖與水平線。
   資料：data/kbar/<代號>.enc.json（近期：前一年 1/1 起）＋ <代號>.hist.enc.json（更早的歷史，外層 hist 指到它）。
         加密、金鑰、密碼都與期貨共用（解鎖一次，期貨與個股都能看）。檔案由 GitHub Actions（prices-daily 的 tools/kbar_update.py）寫入。
   兩個用法：
     KB.watch(root, cfg)   看盤頁（futures/）：左清單＋大圖
     KB.stock(el, opts)    個股頁「今日股價與估值」的 K 棒檢視（由 assets/daily.js 延遲載入本檔後呼叫）
   資料誠實：讀不到的商品顯示「—」與原因，不顯示假數字；沒解鎖不顯示任何價格。 */
const KB = (() => {
  const MAS = FUT.MAS, fmt = FUT.fmt, dstr = FUT.dstr, esc = FUT.esc;
  const LAST_LS = 'erd-watch-last', SORT_LS = 'erd-watch-sort';
  const ls = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { } } };
  let C = { base: '../data/kbar/', futBase: '../data/futures/', companies: [], link: '../' };
  const futCodes = () => (FUT.SYMS || ['ym', 'nq']).slice();
  const isFut = (code) => futCodes().includes(code);
  const mmdd = (t) => t ? t.slice(5).replace('-', '/') : '';
  const NAMES = { ym: '小道瓊', nq: '小那指', tx: '大台指' };

  function init(o) { C = Object.assign({}, C, o || {}); }

  /* ---------- 讀檔 ---------- */
  const outers = {};
  /* 外層（沒有價格：名稱、日期、筆數、hist 指標）；解鎖前也讀得到 */
  function outer(code) {
    if (!outers[code]) outers[code] = FUT.getJSON((isFut(code) ? C.futBase : C.base) + code + '.enc.json').catch((e) => { delete outers[code]; throw e; });
    return outers[code];
  }
  const unlocked = async () => !!(await FUT.keyFromStore());
  /* 近期檔（個股）；期貨走 FUT.load。沒有金鑰或金鑰錯回傳 null（金鑰錯會清掉記住的金鑰）。
     這一檔解不開但期貨解得開（金鑰是對的；例如換密碼後這一檔還沒用新密碼重新產生）→ 丟錯誤，只讓這一檔顯示原因，不把整個網站上鎖 */
  async function recent(code) {
    if (isFut(code)) return FUT.load(C.futBase, code);
    const ck = 'kb:' + code; if (FUT.cache[ck]) return FUT.cache[ck];
    const key = await FUT.keyFromStore(); if (!key) return null;
    const o = await outer(code);
    try { FUT.cache[ck] = await FUT.decrypt(o, key); }
    catch (e) {
      if (!(await FUT.load(C.futBase, futCodes()[0]))) return null;   // 期貨也解不開：金鑰錯，FUT.load 已清掉金鑰
      throw new Error('這一檔的資料檔解不開（可能還是舊密碼加密，下一次自動更新後會恢復）');
    }
    return FUT.cache[ck];
  }
  /* 近期＋歷史合併成跟期貨 payload 同形狀的物件（bars 依日期串接、去重）。歷史檔讀不到 → 只用近期並標 histMissing */
  async function full(code) {
    if (isFut(code)) return FUT.load(C.futBase, code);
    const ck = 'kbf:' + code; if (FUT.cache[ck]) return FUT.cache[ck];
    const r = await recent(code); if (!r) return null;
    const o = await outer(code);
    let bars = r.bars, histMissing = false;
    if (o.hist && o.hist.file) {
      try {
        // 近期檔剛用同一把金鑰解開，所以歷史檔解不開是檔案本身的問題（例如還是舊密碼加密）：當成讀不到，不上鎖
        const key = await FUT.keyFromStore(), hf = await FUT.getJSON(C.base + o.hist.file);
        const h = await FUT.decrypt(hf, key);
        const seen = new Set(r.bars.map(b => b[0]));
        bars = h.bars.filter(b => !seen.has(b[0])).concat(r.bars).sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
      } catch (e) { histMissing = true; }
    }
    const d = Object.assign({}, r, { bars, histMissing, firstDate: histMissing ? r.bars[0][0] : (o.firstDate || r.firstDate) });
    FUT.cache[ck] = d;
    return d;
  }
  /* 清單列用：最新收盤與漲跌（只用近期檔，不讀歷史） */
  function quick(d) {
    const n = d.bars.length, b = d.bars[n - 1], p = d.bars[n - 2];
    return { c: b[4], date: b[0], chg: p ? (b[4] / p[4] - 1) * 100 : null, dp: FUT.dp(d) };
  }

  /* ---------- 圖與數值（看盤頁、個股頁共用） ---------- */
  const pNames = { D: '日 K', W: '週 K', M: '月 K' };
  /* els：{leg, chart, lines, title?, sub?, ma?, src?}；st：{p, mas:Set, vol}；回傳 chart */
  function render(els, d, st, item) {
    const bars = FUT.aggregate(FUT.toBars(d), st.p), S = FUT.study(bars), q = FUT.dp(d), n = bars.length;
    const done = FUT.periodDone(bars[n - 1].last || bars[n - 1].t, st.p);
    const unit = pNames[st.p].replace(' K', '');
    if (els.title) els.title.textContent = d.kind === 'stock' ? `${d.name} ${(item && item.ticker) || d.yahoo || d.code} ${pNames[st.p]}` : `${d.name}期貨 ${pNames[st.p]}`;
    if (els.sub) {
      const tail = (done ? '' : `· 最後一根${unit}尚未收完，只算到 ${dstr(d.lastDate)}`) + (d.provisional ? '· 最新一根為暫定（收盤後 Yahoo 日線還沒定案，下一班會更新）' : '') + (d.histMissing ? '· 歷史檔讀不到，只顯示近期' : '');
      els.sub.textContent = d.kind === 'stock'
        ? `${d.exchange || ''} · ${d.currency || ''} · 已依分割調整、不含股利 · 資料 ${dstr(d.firstDate)} – ${dstr(d.lastDate)}${tail}`
        : `${d.exchange} 連續近月合約（未調整${d.session ? '，' + d.session : ''}）· 資料 ${dstr(d.firstDate)} – ${dstr(d.lastDate)}${tail}`;
    }
    if (els.chart._kbChart) { els.chart._kbChart.remove(); els.chart._kbChart = null; }
    const chart = FUT.chartInto(els.chart, d, bars, S, { p: st.p, mas: st.mas, vol: st.vol, marks: true });
    els.chart._kbChart = chart;
    FUT.linesList(els.lines, d);
    const idx = Object.fromEntries(bars.map((b, i) => [b.t, i]));
    const leg = (i) => {
      const b = bars[i], p = bars[i - 1], ch = p ? (b.c / p.c - 1) * 100 : null;
      els.leg.innerHTML = `<span class="d">${dstr(b.t)}${st.p !== 'D' && b.last && b.last !== b.t ? '–' + dstr(b.last).slice(5) : ''}</span>` +
        `<span>開 <b>${fmt(b.o, q)}</b></span><span>高 <b>${fmt(b.h, q)}</b></span><span>低 <b>${fmt(b.l, q)}</b></span><span>收 <b class="${ch >= 0 ? 'kup' : 'kdn'}">${fmt(b.c, q)}</b> ${ch == null ? '' : sp(ch, 2)}</span>` +
        MAS.filter(m => st.mas.has(m)).map(m => `<span><i style="background:${T(FUT.MA_COLOR(m))}"></i>MA${m} ${fmt(S.ma[m][i], q)}</span>`).join('') +
        `<span><i style="background:${T('--s1')}"></i>K ${fmt(S.K[i], 1)}</span><span><i style="background:${T('--s2')}"></i>D ${fmt(S.D[i], 1)}</span>`;
    };
    leg(n - 1);
    chart.subscribeCrosshairMove(p => { const i = p && p.time != null ? idx[typeof p.time === 'string' ? p.time : `${p.time.year}-${String(p.time.month).padStart(2, '0')}-${String(p.time.day).padStart(2, '0')}`] : null; leg(i == null ? n - 1 : i); });
    if (els.ma) {
      const last = bars[n - 1];
      els.ma.innerHTML = `<thead><tr><th>均線</th><th>目前</th><th>扣抵值</th><th>扣抵那一根</th><th>最新收盤 − 扣抵值</th><th class="txt">若下一根收盤跟最新收盤一樣</th></tr></thead><tbody>` +
        MAS.map(m => { const x = S.ded[m], v = S.ma[m][n - 1]; if (!x || v == null) return `<tr><td><i class="dot" style="background:${T(FUT.MA_COLOR(m))}"></i>MA${m}</td><td colspan="5" class="txt">資料不足 ${m} 根</td></tr>`;
          const diff = last.c - x.c, nx = v + diff / m;
          return `<tr><td><i class="dot" style="background:${T(FUT.MA_COLOR(m))}"></i>MA${m}</td><td>${fmt(v, q)}</td><td>${fmt(x.c, q)}</td><td>${dstr(x.t)}</td><td class="${diff >= 0 ? 'kup' : 'kdn'}">${diff >= 0 ? '+' : '−'}${fmt(Math.abs(diff), q)}</td><td class="txt">${diff > 0 ? '均線上揚' : diff < 0 ? '均線下彎' : '均線持平'}，變成 ${fmt(nx, q)}</td></tr>`; }).join('') + '</tbody>';
    }
    if (els.src) els.src.innerHTML = d.kind === 'stock' ? srcStock(d) : FUT.srcFut(d);
    return chart;
  }
  function srcStock(d) {
    const ck = d.check;
    const pend = d.pending && d.pending.length ? `<li><details><summary class="pend">待確認：${d.pending.length} 天的 K 棒沒有採用（點開看日期與原因）</summary><ul>${d.pending.map(p => `<li>${p.date ? dstr(p.date) + '：' : ''}${esc(p.reason)}</li>`).join('')}</ul></details></li>` : '';
    return `<li>價格：<a href="${esc(d.source.url)}" target="_blank" rel="noopener">${esc(d.source.n)}</a>，每個交易日收盤後由 GitHub Actions 自動抓（這次抓取：${esc((d.fetchedAt || '').replace('T', ' ').slice(0, 16))} UTC）。延遲資料，只供研究，不能拿來下單。</li>` +
      `<li>核對：` + (ck ? esc(ck.note) : '<span class="pend">待確認：這一檔沒有核對資訊。</span>') + `</li>` +
      (d.provisional ? `<li><span class="pend">暫定：</span>最新一根在收盤後 Yahoo 日線還沒定案時先放上，下一班自動更新會用正式值覆蓋。</li>` : '') +
      `<li>成交量顯示空白的日子是來源沒有提供成交量。價格口徑與「今日股價與估值」的收盤價相同：依股票分割調整、不含股利調整。</li>` +
      `<li>週 K、月 K 由日 K 合成；MA 為收盤價簡單平均，KD 為 (9,3,3) 台灣算法，扣抵值為下一根會被扣掉的那根收盤價。</li>` + pend;
  }
  const maBtns = () => MAS.map(n => `<button type="button" data-ma="${n}" aria-pressed="true"><i style="background:${T(FUT.MA_COLOR(n))}"></i>${n}</button>`).join('');
  const sync = (root, st) => {
    root.querySelectorAll('[data-p]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.p === st.p)));
    root.querySelectorAll('[data-ma]').forEach(b => b.setAttribute('aria-pressed', String(st.mas.has(+b.dataset.ma))));
    const v = root.querySelector('[data-vol]'); if (v) v.setAttribute('aria-pressed', String(st.vol));
  };
  const onTheme = (f) => {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', f);
    new MutationObserver(f).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  };

  /* ====================== 個股頁的 K 棒檢視 ====================== */
  /* el：放 K 棒的容器；o：{code, name, ticker, link（看盤頁網址，不含 ?s=）} */
  function stock(el, o) {
    const st = { p: 'D', mas: new Set(MAS), vol: true };
    el.classList.add('kb-embed');
    el.innerHTML = `<div class="kb-lockbox" hidden></div><div class="kb-ebody" hidden>
      <div class="fut-ctrl">
        <div class="seg" role="group" aria-label="週期"><button type="button" data-p="D">日K</button><button type="button" data-p="W">週K</button><button type="button" data-p="M">月K</button></div>
        <div class="seg fut-ma" role="group" aria-label="均線">${maBtns()}</div>
        <div class="seg" role="group" aria-label="成交量"><button type="button" data-vol="1">成交量</button></div>
        ${FUT.toolBtn()}</div>
      <div class="fut-leg"></div><div class="fut-chart"></div><div class="fut-lines"></div>
      <p class="how kb-foot"><a class="go" href="${esc(o.link)}?s=${encodeURIComponent(o.code)}">在看盤頁開啟 →</a> <span class="kb-asof"></span>圖下方小三角「扣N」＝ MA N 下一根會扣掉的那根 K 棒；水平線與看盤頁共用（記在這台裝置）。</p></div>`;
    const $ = (s) => el.querySelector(s), body = $('.kb-ebody'), lockbox = $('.kb-lockbox');
    const els = { leg: $('.fut-leg'), chart: $('.fut-chart'), lines: $('.fut-lines') };
    let d = null, seq = 0;
    const item = { ticker: o.ticker };
    async function go() {
      const my = ++seq;
      if (!(await unlocked())) { body.hidden = true; lockbox.hidden = false; FUT.lockForm(lockbox, C.futBase, go); return; }
      let x;
      try { x = await full(o.code); } catch (e) { if (my !== seq) return; body.hidden = true; lockbox.hidden = false; lockbox.innerHTML = `<p class="fut-note">讀不到 ${esc(o.name)} 的 K 棒資料（${esc(e.message || e)}）。第一次資料可能還在產生，請稍後再試。</p>`; return; }
      if (my !== seq) return;
      if (!x) { body.hidden = true; lockbox.hidden = false; FUT.lockForm(lockbox, C.futBase, go); return; }
      d = x; lockbox.hidden = true; body.hidden = false;
      draw();
    }
    function draw() { if (!d || body.hidden) return; sync(el, st); render(els, d, st, item); $('.kb-asof').textContent = `資料截至 ${dstr(d.lastDate)}。` + (d.histMissing ? `歷史檔讀不到，只顯示 ${dstr(d.firstDate)} 起的近期資料（週 K、月 K、長天期均線與 KD 不完整）。` : ''); }
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b || !b.closest('.fut-ctrl')) return;
      if (b.dataset.p) st.p = b.dataset.p; else if (b.dataset.ma) { const n = +b.dataset.ma; st.mas.has(n) ? st.mas.delete(n) : st.mas.add(n); } else if (b.dataset.vol) st.vol = !st.vol; else return;
      draw();
    });
    FUT.wireTool(el);
    FUT.Lines.on((c) => { if (d && !body.hidden && (c == null || c === d.code)) FUT.linesList(els.lines, d); });
    onTheme(() => draw());
    go();
    return { redraw: draw, reload: go };
  }

  /* ====================== 看盤頁 ====================== */
  function watch(root, cfg) {
    cfg = cfg || {};
    const $ = (s) => root.querySelector(s);
    const gmap = {};
    const items = [];
    futCodes().forEach(c => items.push({ id: c, code: c, name: NAMES[c] || c.toUpperCase(), ticker: c.toUpperCase(), kind: 'fut', sector: '指數期貨', href: null }));
    (C.companies || []).forEach(c => items.push({ id: c.code, code: c.code, name: c.name, ticker: c.ticker || c.code.toUpperCase(), kind: 'stock', sector: c.sector || '其他', href: c.href }));
    items.forEach(it => { gmap[it.id] = it; });
    const sectors = []; items.forEach(it => { if (!sectors.includes(it.sector)) sectors.push(it.sector); });
    const q = new URLSearchParams(location.search);
    const st = { p: { D: 'D', W: 'W', M: 'M' }[q.get('p')] || 'D', mas: new Set(MAS), vol: true, sort: ls.get(SORT_LS) === 'chg' ? 'chg' : 'sector' };
    let cur = gmap[q.get('s')] || gmap[ls.get(LAST_LS)] || items[0];
    let d = null, seq = 0, locked = true, loaded = 0, order = [];
    const els = { leg: $('#futLeg'), chart: $('#futChart'), lines: $('#futLines'), title: $('#futTitle'), sub: $('#futSub'), ma: $('#futMaTbl'), src: $('#futSrc') };

    /* ----- 清單 ----- */
    const arrow = (c) => c > 0 ? 'kup' : c < 0 ? 'kdn' : '';
    function rowHTML(it) {
      const x = it.q, sel = it === cur;
      let a, b, title = '';
      if (locked) { a = '<span class="ch">🔒</span>'; b = it.lastDate ? `資料截至 ${mmdd(it.lastDate)}` : '—'; if (it.err) title = it.err; }
      else if (x) { a = `<span class="ch ${arrow(x.chg)}">${x.chg == null ? '—' : sp(x.chg, 2)}</span>`; b = `${fmt(x.c, x.dp)} · ${mmdd(x.date)}`; }
      else if (it.err) { a = '<span class="ch">—</span>'; b = '—'; title = it.err; }
      else { a = '<span class="ch">…</span>'; b = '讀取中'; }
      return `<button type="button" class="kb-row" role="option" data-id="${esc(it.id)}" aria-selected="${sel}"${title ? ` title="${esc(title)}"` : ''}><span class="n">${esc(it.name)}</span>${a}<span class="c">${esc(it.ticker)}</span><span class="px">${b}</span></button>`;
    }
    function renderList() {
      const stocks = items.filter(i => i.kind === 'stock'), futs = items.filter(i => i.kind === 'fut');
      let html = '';
      order = [];
      const grp = (title, arr) => { if (!arr.length) return; html += `<div class="kb-grp">${esc(title)}<span>${arr.length}</span></div>`; arr.forEach(i => { order.push(i); html += rowHTML(i); }); };
      grp('指數期貨', futs);
      if (st.sort === 'sector') sectors.filter(s => s !== '指數期貨').forEach(s => grp(s, stocks.filter(i => i.sector === s)));
      else grp('個股（漲跌幅高到低）', stocks.slice().sort((a, b) => (b.q && b.q.chg != null ? b.q.chg : -1e9) - (a.q && a.q.chg != null ? a.q.chg : -1e9)));
      $('#kbList').innerHTML = html;
      $('#kbSort').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.sort === st.sort)));
      const sum = $('#kbSum');
      if (locked) sum.textContent = '解鎖後顯示各檔漲跌與上漲／下跌家數';
      else {
        const got = stocks.filter(i => i.q && i.q.chg != null), up = got.filter(i => i.q.chg > 0).length, dn = got.filter(i => i.q.chg < 0).length;
        sum.innerHTML = `上漲 <b class="kup">${up}</b> · 下跌 <b class="kdn">${dn}</b> · 平 <b>${got.length - up - dn}</b><small>（個股，各商品最新一個交易日${loaded < items.length ? `；讀取中 ${loaded}/${items.length}` : ''}）</small>`;
      }
      $('#kbTogName').textContent = `${cur.name} ${cur.ticker}`;
    }
    let raf = 0; const soon = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; renderList(); }); };
    /* 逐檔延遲讀取：一次 4 檔，讀好一檔就更新那一列，不等全部 */
    async function loadAll() {
      loaded = 0; items.forEach(it => { it.q = null; it.err = ''; });
      const todo = items.slice(); const worker = async () => {
        while (todo.length) {
          const it = todo.shift();
          try { const r = await recent(it.code); if (r) it.q = quick(r); else if (!(await unlocked())) { locked = true; } }
          catch (e) { it.err = errWhy(e); }
          loaded++; soon();
        }
      };
      await Promise.all([worker(), worker(), worker(), worker()]);
      loaded = items.length; soon();
    }
    const errWhy = (e) => /404/.test(e && e.message || '') ? '讀不到資料檔（第一次資料還在產生，或還沒有這一檔）' : '讀不到資料（' + ((e && e.message) || e) + '）';
    async function loadOuters() {
      const todo = items.slice();
      const worker = async () => { while (todo.length) { const it = todo.shift(); try { const o = await outer(it.code); it.lastDate = o.lastDate; if (o.name && it.kind === 'fut') it.name = o.name; it.err = ''; } catch (e) { it.err = errWhy(e); } soon(); } };
      await Promise.all([worker(), worker(), worker(), worker()]);
    }

    /* ----- 選商品 ----- */
    function setCur(it, push) {
      if (!it) return;
      cur = it;
      $('#kbApp').classList.remove('kb-open');
      renderList(); go();
      const r = $(`.kb-row[data-id="${CSS.escape(it.id)}"]`); if (r && r.scrollIntoView) r.scrollIntoView({ block: 'nearest' });
    }
    const step = (k) => { const i = order.indexOf(cur); if (i < 0) return; setCur(order[Math.max(0, Math.min(order.length - 1, i + k))]); };

    async function go() {
      const my = ++seq, it = cur;
      ls.set(LAST_LS, it.id);
      history.replaceState(null, '', `?s=${it.id}&p=${st.p}`);
      const fin = $('#kbFin'); if (it.href) { fin.href = it.href; fin.hidden = false; } else fin.hidden = true;
      $('#futTitle').textContent = `${it.name} ${it.ticker} ${pNames[st.p]}`;
      if (!(await unlocked())) { showLock(my); return; }
      let x;
      try { x = await full(it.id); }
      catch (e) { if (my !== seq) return; d = null; $('#futBody').hidden = true; const L = $('#futLock'); L.hidden = false; L.innerHTML = `<p class="fut-note">${esc(it.name)}：${esc(errWhy(e))}。</p>`; $('#futSub').textContent = ''; return; }
      if (my !== seq) return;
      if (!x) { showLock(my); return; }
      if (locked) { locked = false; loadAll(); }
      d = x; $('#futLock').hidden = true; $('#futBody').hidden = false;
      draw();
    }
    function showLock(my) {
      if (my !== seq) return;
      d = null; $('#futBody').hidden = true; const L = $('#futLock'); L.hidden = false;
      $('#futSub').textContent = it_asof(cur);
      FUT.lockForm(L, C.futBase, () => { locked = false; loadAll(); go(); });
      if (!locked) { locked = true; renderList(); }
    }
    const it_asof = (it) => it.lastDate ? `資料截至 ${dstr(it.lastDate)}（解鎖後顯示價格）` : '';
    function draw() {
      if (!d) return;
      sync(root, st);
      render(els, d, st, cur);
    }

    /* ----- 事件 ----- */
    $('#kbList').addEventListener('click', (e) => { const b = e.target.closest('.kb-row'); if (b) setCur(gmap[b.dataset.id]); });
    $('#kbSort').addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; st.sort = b.dataset.sort; ls.set(SORT_LS, st.sort); renderList(); });
    $('#kbTog').addEventListener('click', () => $('#kbApp').classList.toggle('kb-open'));
    $('#kbPrev').addEventListener('click', () => step(-1));
    $('#kbNext').addEventListener('click', () => step(1));
    root.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b || !b.closest('.fut-ctrl')) return;
      if (b.dataset.p) st.p = b.dataset.p; else if (b.dataset.ma) { const n = +b.dataset.ma; st.mas.has(n) ? st.mas.delete(n) : st.mas.add(n); }
      else if (b.id === 'futVol') st.vol = !st.vol;
      else if (b.id === 'futLockBtn') { FUT.lock(); locked = true; items.forEach(i => { i.q = null; }); renderList(); go(); return; }
      else return;
      if (b.dataset.p) { history.replaceState(null, '', `?s=${cur.id}&p=${st.p}`); $('#futTitle').textContent = `${cur.name} ${cur.ticker} ${pNames[st.p]}`; }
      draw();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      const t = e.target; if (t && (/INPUT|TEXTAREA|SELECT/.test(t.tagName || '') || t.isContentEditable)) return;
      e.preventDefault(); step(e.key === 'ArrowDown' ? 1 : -1);
    });
    FUT.wireTool(root);
    FUT.Lines.on((c) => { if (d && (c == null || c === d.code)) FUT.linesList(els.lines, d); });
    $('#futMaBtns').innerHTML = maBtns();
    onTheme(() => draw());

    /* ----- 開始 ----- */
    renderList();
    (async () => {
      locked = !(await unlocked());
      loadOuters().then(() => soon());
      if (!locked) loadAll();
      renderList(); go();
    })();
    return { select: (id) => setCur(gmap[id]), items };
  }

  return { init, watch, stock, recent, full, outer, isFut };
})();
