/* 個股頁「今日股價與估值」：每個交易日收盤後由 GitHub Actions（prices-daily）抓收盤價，tools/daily_calc.py 用公式算好。
   資料兩個來源，取比較新的那個：
     1. 頁面打開時讀 D.dailyUrl（data/daily/<代號>.json；Actions 每天更新，不必重建網站）
     2. 建置時放進頁面的 D.daily（讀不到檔案時用，例如 Artifact 連不到 GitHub Pages）
   前端只顯示，不重算公式。放在標題（header.masthead）正下方。 */
const DAILY = (() => {
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const CUR = { USD: '美元', TWD: '元', EUR: '歐元', KRW: '韓元' };
  const nf = (n, d = 2) => n == null ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const x1 = (n) => n == null ? '—' : n.toFixed(1) + '×';
  const noisy = (n) => typeof PEV !== 'undefined' ? PEV.noisy(n) : (n != null && n > 200);   // 本益比超過 PEV.CAP 顯示「不適用」
  const sg = (n, u = '%') => n == null ? '—' : (n > 0 ? '+' : '') + n.toFixed(1) + u;
  const md = (d) => d ? d.slice(5).replace('-', '/') : '';
  const WHY = { loss: '虧損，不適用', short: '累積未滿四季', missing: '待確認', none: '還沒有預估快照', neg: '營收不是正數' };
  // 金額單位是「百萬」：≥ 100 萬百萬＝兆、≥ 100 百萬＝億
  const money = (m, cur) => m == null ? null : (m >= 1e6 ? nf(m / 1e6, 2) + ' 兆' : nf(m / 100, 0) + ' 億') + (CUR[cur] || cur || '');

  // 使用者選的指標與期間放在模組層：render() 可能跑兩次（建置內嵌版、再換成讀到的新檔），不能把選擇重設
  let k = 1, range = 5;
  const RANGES = [1, 3, 5];
  const cutoff = (d, n) => { const t = new Date(d + 'T00:00:00Z'); t.setUTCFullYear(t.getUTCFullYear() - n); return t.toISOString().slice(0, 10); };

  function render(sec, X, D) {
    const L = X.latest, cur = X.currency, W = L.why || {};
    const ch = L.chg == null ? '' : `<span class="chip ${L.chg > 0 ? 'chip-up' : L.chg < 0 ? 'chip-down' : ''}">${sg(L.chg)}</span>`;
    const caps = (L.caps || []).map(c => {
      if (c.now == null) return `<li><b>${esc(c.name)}上限 ${c.thr}${c.k === 'fcfY' ? '%' : '×'}</b>：現值算不出來（${WHY[W[c.k]] || '待確認'}）</li>`;
      const unit = c.k === 'fcfY' ? '%' : '×';
      const word = c.op === '<=' ? (c.ok ? `還有 <b>${sg(c.room)}</b> 空間` : `已超過上限 <b>${sg(-c.room)}</b>`) : (c.ok ? `高於下限 <b>${sg(c.room)}</b>` : `低於下限 <b>${sg(c.room)}</b>`);
      const px = c.px == null ? '' : `；股價 <b>${nf(c.px)}</b> 以下才在門檻內`;
      return `<li><span class="chip ${c.ok ? 'chip-up' : 'chip-down'}">${c.ok ? '在門檻內' : '超出門檻'}</span> <b>${esc(c.name)} ${c.op === '<=' ? '≤' : '≥'} ${c.thr}${unit}</b>：現在 ${c.k === 'fcfY' ? nf(c.now) + '%' : x1(c.now)}，${word}${px}</li>`;
    }).join('');
    const chk = X.check ? `<span class="${X.check.ok === false ? 'st-plan' : ''}">${esc(X.check.note)}</span>。` : '';
    sec.innerHTML = `
    <div class="sec-head"><span class="sec-tag">每日收盤 · ${L.d.replace(/-/g, '/')}</span><h2>今日股價與估值</h2>
      <p class="sub">每個交易日收盤後由 GitHub Actions 自動抓收盤價，本益比、市值等用固定公式算出來（不經過 Claude）。財報數字一律用「那天為止已公布」的季度。</p></div>
    <div class="kpis">
      <div class="kpi"><span class="label">收盤價（${md(L.d)}）</span><span class="value">${nf(L.c, cur === 'KRW' ? 0 : 2)}<small>${esc(CUR[cur] || cur)}</small></span><span class="delta">${ch} ${L.prevD ? '比 ' + md(L.prevD) : ''}</span></div>
      <div class="kpi"><span class="label">本益比（近四季）</span><span class="value"${noisy(L.pe) ? ` title="${esc(PEV.tip(L.pe))}"` : ''}>${L.pe != null ? (noisy(L.pe) ? '<small>不適用</small>' : x1(L.pe)) : `<small>${WHY[W.pe] || '—'}</small>`}</span><span class="delta">${noisy(L.pe) ? `公式值 ${x1(L.pe)}，近四季 EPS 接近零，倍數沒有參考價值<br>` : ''}${L.eps4 != null ? `EPS ${nf(L.eps4)}（到 ${esc(L.q)}）` : ''}${L.vsMed5 != null && !noisy(L.pe) ? `<br>比近 5 年中位數 ${x1(L.med5)}${noisy(L.med5) ? '（參考性低）' : ''} ${sg(L.vsMed5)}` : ''}</span></div>
      <div class="kpi"><span class="label">預估本益比（分析師預估）</span><span class="value">${L.fpe != null ? (noisy(L.fpe) ? '<small>不適用</small>' : x1(L.fpe)) : `<small>${WHY[W.fpe] || '—'}</small>`}</span><span class="delta">${L.fSnap ? `用 ${esc(L.fSnap)} 月底預估快照${L.few ? '・人數少' : ''}` : '2026-11 月底起逐月存檔'}</span></div>
      <div class="kpi"><span class="label">市值</span><span class="value" style="font-size:var(--step-2)">${L.mcap != null ? money(L.mcap, cur) : `<small>${WHY[W.mcap] || '待確認'}</small>`}</span><span class="delta">${L.mcap != null ? `收盤價 × ${esc(L.shQ)} 期末股數${L.shLatest ? '' : '（最新一季股數待確認）'}` : '期末流通股數待確認'}</span></div>
      <div class="kpi"><span class="label">股價營收比（P/S）</span><span class="value">${L.ps != null ? x1(L.ps) : '<small>—</small>'}</span><span class="delta">${L.evS != null ? 'EV/Sales ' + x1(L.evS) : ''}${L.fcfY != null ? `<br>FCF 殖利率 ${nf(L.fcfY)}%` : ''}</span></div>
    </div>
    <div class="card wide">
      ${caps ? `<h3>離論點卡的估值門檻多遠</h3><ul class="sum-list">${caps}</ul>` : ''}
      <p class="how">近 52 週最高 ${nf(L.hi52, cur === 'KRW' ? 0 : 2)}、最低 ${nf(L.lo52, cur === 'KRW' ? 0 : 2)}，目前離最高 ${sg(L.fromHi)}。</p>
      <div class="tbl-bar"><h3 id="dyT">近 5 年每日收盤價</h3>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
        <div class="seg" id="dyR" role="group" aria-label="期間">${RANGES.map(n => `<button type="button" data-r="${n}" aria-pressed="${n === range}">${n} 年</button>`).join('')}</div>
        <div class="seg" id="dyK" role="group" aria-label="指標"><button type="button" data-k="1" aria-pressed="${k === 1}">收盤價</button><button type="button" data-k="2" aria-pressed="${k === 2}">本益比</button></div></div></div>
      <div class="chartbox short"><canvas id="cDY" aria-label="每日收盤價與本益比"></canvas></div>
      <p class="how pe-note">本益比 ＝ 收盤價 ÷ 近四季 EPS；市值 ＝ 收盤價 × 期末流通股數；P/S ＝ 市值 ÷ 近四季營收；EV/Sales ＝（市值 ＋ 有息負債 − 現金與投資）÷ 近四季營收；距門檻 ＝ 門檻 ÷ 現值 − 1。
        股價：Yahoo Finance 日線收盤（分割調整、不含股利調整），還沒收盤的當天不收。${chk}
        圖為近 5 年（上市未滿 5 年從上市起）。預估本益比用分析師預估，不是財報數字。抓取時間 ${esc((X.fetched || '').replace('T', ' ').replace('Z', ' UTC'))}。</p>
    </div>`;
    const S0 = X.series || [];
    const first = S0.length ? S0[0][0] : null;
    // 資料沒有超過「下一個較短期間」的起點，這個期間就沒意義（等於跟較短的一樣）→ 藏起來
    const avail = RANGES.filter((n, i) => i === 0 || (first && first <= cutoff(L.d, RANGES[i - 1])));
    if (!avail.includes(range)) range = avail[avail.length - 1];
    sec.querySelectorAll('#dyR button').forEach(b => { b.hidden = !avail.includes(+b.dataset.r); b.setAttribute('aria-pressed', String(+b.dataset.r === range)); });
    if (avail.length < 2) sec.querySelector('#dyR').hidden = true;
    let chart = null;
    const draw = () => {
      const cut = cutoff(L.d, range);
      const S = S0.filter(r => r[0] > cut);
      if (!window.Chart || !S.length) return;
      if (chart) chart.destroy();
      const col = k === 1 ? css('--s1') : css('--s4') || css('--s2');
      const short = first > cut;      // 資料起點比期間起點晚：標出從哪個月起
      const pre = short ? `${first.slice(0, 4)}/${first.slice(5, 7)} 起每日` : `近 ${range} 年每日`;
      const tail = short ? `（未滿 ${range} 年）` : '';
      sec.querySelector('#dyT').textContent = k === 1 ? `${pre}收盤價（${CUR[cur] || cur}）${tail}` : `${pre}本益比（倍）${tail}`;
      chart = LT.lazyChart(sec.querySelector('#cDY'), { type: 'line', data: { labels: S.map(r => r[0]), datasets: [{ label: k === 1 ? '收盤' : '本益比', data: S.map(r => r[k]), borderColor: col, backgroundColor: col, borderWidth: range === 1 ? 1.8 : 1.3, pointRadius: 0, pointHoverRadius: 3, tension: 0, spanGaps: false }] },
        options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { display: false }, tooltip: { backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink-2'), borderColor: css('--axis'), borderWidth: 1, padding: 8,
            callbacks: { label: (c) => c.raw == null ? ' 算不出來' : (k === 1 ? ' 收盤 ' + nf(c.raw) : ' 本益比 ' + x1(c.raw)) } } },
          scales: { y: { border: { display: false }, grid: { color: css('--grid'), drawTicks: false }, ticks: { color: css('--tick'), padding: 6, callback: (v) => k === 1 ? nf(v, 0) : v + '×', font: { family: 'IBM Plex Mono, monospace', size: 11 } } },
            x: { border: { color: css('--axis') }, grid: { display: false }, ticks: { color: css('--tick'), maxRotation: 0, autoSkip: true, maxTicksLimit: 7, font: { family: 'IBM Plex Mono, monospace', size: 11 }, callback: function (v) { const l = this.getLabelForValue(v); return l ? l.slice(2, 7).replace('-', '/') : ''; } } } } } });
    };
    sec.querySelector('#dyK').addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; k = +b.dataset.k; sec.querySelectorAll('#dyK button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); draw(); });
    sec.querySelector('#dyR').addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; range = +b.dataset.r; sec.querySelectorAll('#dyR button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); draw(); });
    draw();
    if (!sec.__re) {
      sec.__re = true;
      let t; const re = () => { clearTimeout(t); t = setTimeout(draw, 60); };
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', re);
      new MutationObserver(re).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }
    sec.hidden = false;
    const nav = document.getElementById('secnav');
    if (nav && !nav.querySelector('a[href="#today"]')) { const o = nav.querySelector('a[href="#overview"]'); if (o) o.insertAdjacentHTML('afterend', '<a href="#today">今日股價</a>'); }
  }

  function mount(D) {
    if (document.getElementById('today')) return;
    const head = document.querySelector('header.masthead');
    if (!head) return;
    const sec = document.createElement('section'); sec.id = 'today'; sec.hidden = true;
    head.after(sec);
    const has = (X) => X && X.latest && X.latest.d;
    if (has(D.daily)) render(sec, D.daily, D);
    if (!D.dailyUrl || !window.fetch) return;
    fetch(D.dailyUrl, { cache: 'no-cache' }).then(r => r.ok ? r.json() : null).then(F => {
      const X = F && F.calc;
      if (!has(X)) return;
      const E = D.daily;
      // 檔案比較新（收盤日較晚，或同一天但計算時間較新）才換掉建置時的版本
      if (!has(E) || X.latest.d > E.latest.d || (X.latest.d === E.latest.d && (F.fetched || '') > (E.fetched || ''))) render(sec, X, D);
    }).catch(() => {});
  }
  return { mount };
})();
