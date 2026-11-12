/* 每月本益比（P/E）與預估本益比（forward P/E）的前端顯示。
   資料由 tools/pe.py 在建置時算好放在 D.valuation（前端只畫圖、不重算）：
     D.valuation = { symbol, currency, monthly:[{m,d,c,eps4,pe,why,ntm,fpe,fwhy,few}], stats:{latest,latestM,med5,med10,pct10,fpeLatest,fpeM,priceM} }
   why：loss 虧損、short 累積未滿四季、missing EPS 或公布日待確認、price 股價待確認
   不依賴 common.js（台積電頁面沒有載入），所以自己帶一套小工具。
   提供：PEV.mount(D)  公司頁「本益比（每月）」整節；PEV.brief(D) 首頁卡片／記分板用的文字；PEV.cmp(...) 首頁比較圖 */
const PEV = (() => {
  const CAP = 200;
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const x1 = (n) => n == null ? '—' : n.toFixed(1) + '×';
  const f2 = (n) => n == null ? '—' : n.toFixed(2);
  const f4 = (n) => n == null ? '—' : n.toFixed(2);
  const ym = (m) => m.replace('-', '/');
  const WHY = { loss: '虧損，不適用', short: '累積未滿四季', missing: '待確認', price: '待確認（股價）' };
  const FWHY = { loss: '預估虧損，不適用', missing: '待確認', none: '' };
  const COPY = '本益比 ＝ 月底收盤價 ÷ 「那一天為止已公布」的最近四季 EPS 加總。美股用稀釋 EPS，台積電、台達電、三星用基本 EPS；都是公認會計準則數字。';

  /* 首頁卡片、記分板用 */
  function brief(D) {
    const V = D.valuation; if (!V || !V.monthly.length) return { pe: '股價尚未收錄', fpe: '—', sub: '', pct: '—', has: false };
    const s = V.stats, last = V.monthly[V.monthly.length - 1];
    let pe, sub = '';
    if (last.pe != null) { pe = x1(last.pe); sub = ym(last.m) + ' 月底'; }
    else { pe = WHY[last.why] || '—'; sub = ym(last.m) + ' 月底'; }
    const fl = [...V.monthly].reverse().find(r => r.fpe != null);
    return { has: true, pe, sub, fpe: fl ? x1(fl.fpe) : '累積中', fpeSub: fl ? ym(fl.m) + (fl.few ? '（預估人數少）' : '') : '2026-11 起逐月累積',
      pct: s.pct10 == null ? '—' : s.pct10 + '%', med5: x1(s.med5), med10: x1(s.med10), latestPe: last.pe, priceM: s.priceM, priceD: last.d };
  }

  /* 公司頁整節 */
  function mount(D) {
    const sec = document.getElementById('pe'); if (!sec) return;
    const V = D.valuation;
    const hide = () => { sec.hidden = true; document.querySelectorAll('#secnav a[href="#pe"]').forEach(a => a.remove()); };
    if (!V || !V.monthly.length) return hide();
    const M = V.monthly, s = V.stats, last = M[M.length - 1];
    const b = brief(D);
    const fl = [...M].reverse().find(r => r.fpe != null);
    const nF = M.filter(r => r.fpe != null).length;
    const cur = V.currency || '';
    const hasPE = M.some(r => r.pe != null);
    sec.innerHTML = `
    <div class="sec-head"><span class="sec-tag">每月一筆 · ${ym(M[0].m)} – ${ym(last.m)}</span><h2>本益比（每月）</h2>
      <p class="sub">市場用幾倍的價格買這家公司的一年獲利。每個月底算一次，用「當時已經公布」的最近四季 EPS，所以是當時投資人真的看得到的數字。</p></div>
    <div class="kpis pe-kpis">
      <div class="kpi"><span class="label">最新本益比（${ym(last.m)} 月底）</span><span class="value">${last.pe != null ? x1(last.pe) : `<small>${WHY[last.why] || '—'}</small>`}</span><span class="delta">月底收盤價 ${f2(last.c)} ${cur}</span></div>
      <div class="kpi"><span class="label">近 5 年中位數</span><span class="value">${x1(s.med5)}</span><span class="delta">${s.med5 == null ? '有本益比的月份不足 12 個' : '只用有本益比的月份'}</span></div>
      <div class="kpi"><span class="label">近 10 年中位數</span><span class="value">${x1(s.med10)}</span><span class="delta">${s.med10 == null ? '有本益比的月份不足 12 個' : ''}</span></div>
      <div class="kpi"><span class="label">目前在近 10 年的位置</span><span class="value">${s.pct10 == null ? '—' : s.pct10 + '<small>百分位</small>'}</span><span class="delta">${s.pct10 == null ? '有本益比的月份少於 24 個月，不算百分位' : s.pct10 + '% 的月份比現在便宜（本益比較低）'}</span></div>
      <div class="kpi"><span class="label">預估本益比（分析師預估）</span><span class="value">${fl ? x1(fl.fpe) : '<small>累積中</small>'}</span><span class="delta">${fl ? ym(fl.m) + ' 月底快照' + (fl.few ? ' · 預估人數少' : '') : '2026-11 月底起逐月存檔，不回填'}</span></div>
    </div>
    <div class="card wide">
      <div class="tbl-bar"><h3>每月本益比走勢（倍）</h3>
        <div class="seg" id="peWin" role="group" aria-label="期間"><button type="button" data-y="3" aria-pressed="false">近 3 年</button><button type="button" data-y="5" aria-pressed="false">近 5 年</button><button type="button" data-y="10" aria-pressed="false">近 10 年</button><button type="button" data-y="0" aria-pressed="true">全部</button></div></div>
      <p class="how" id="peHow"></p>
      <div class="legend" id="peLg"></div>
      <div class="chartbox"><canvas id="cPE" aria-label="每月本益比"></canvas></div>
      <p class="how pe-note">${COPY} 虧損期間圖上留白；本益比超過 ${CAP} 倍的點貼在圖的頂端，滑鼠移上去看實際值。股價用「分割調整後、不含股利調整」的收盤價，才跟網站已換算成今天股數的 EPS 對得上。</p>
      <p class="how pe-note"><b>預估本益比</b> ＝ 月底收盤價 ÷ 未來 12 個月預估 EPS（分析師平均預估，按今年度剩餘天數在「今年度」與「下年度」之間加權）。它是<b>分析師預估</b>、不是財報數字，美股多為調整後（non-GAAP）EPS，通常比公認會計準則高，所以和歷史本益比<b>不能直接相減</b>；歷史只能從 2026-11 月底開始逐月累積，不回填。</p>
    </div>
    <details class="card wide pe-det"><summary>每月本益比數據表（${M.length} 個月）</summary>
      <div class="tbl-wrap"><table id="tPE"></table></div></details>`;
    const rows = M.slice().reverse().map(r => `<tr><td>${ym(r.m)}</td><td>${ym(r.d)}</td><td>${f2(r.c)}</td><td>${r.eps4 == null ? '—' : f4(r.eps4)}</td><td>${r.pe != null ? x1(r.pe) : `<span class="st-plan">${WHY[r.why] || '—'}</span>`}</td><td>${r.ntm == null ? '—' : f4(r.ntm)}</td><td>${r.fpe != null ? x1(r.fpe) + (r.few ? '＊' : '') : (r.fwhy && FWHY[r.fwhy] ? `<span class="st-plan">${FWHY[r.fwhy]}</span>` : '—')}</td></tr>`).join('');
    sec.querySelector('#tPE').innerHTML = `<thead><tr><th>月份</th><th>收盤日</th><th>收盤價（${cur}）</th><th>近四季 EPS</th><th>本益比</th><th>未來 12 個月 EPS</th><th>預估本益比</th></tr></thead><tbody>${rows}</tbody><tfoot><tr><td colspan="7" class="txt" style="text-align:left">＊預估人數少於 3 人。未來 12 個月 EPS 與預估本益比為分析師預估，只有存檔過的月份才有。</td></tr></tfoot>`;
    let chart = null, years = 0;
    const draw = () => {
      if (!window.Chart) return;
      if (chart) chart.destroy();
      let from = 0;
      if (years) { const y = +last.m.slice(0, 4) - years, lo = `${y}-${last.m.slice(5)}`; from = Math.max(0, M.findIndex(r => r.m > lo)); }
      const A = M.slice(from);
      const labels = A.map(r => r.m);
      const raw = A.map(r => r.pe);
      const capped = raw.map(v => v == null ? null : Math.min(v, CAP));
      const over = raw.filter(v => v != null && v > CAP).length;
      const c1 = css('--s1'), c2 = css('--s4') || css('--s2');
      const ds = [{ label: '歷史本益比', data: capped, raw, borderColor: c1, backgroundColor: c1, borderWidth: 2, pointRadius: (c) => (raw[c.dataIndex] != null && raw[c.dataIndex] > CAP) ? 4 : (c.dataIndex === raw.length - 1 || raw.filter(v => v != null).length < 3 ? 3 : 0), pointStyle: (c) => (raw[c.dataIndex] != null && raw[c.dataIndex] > CAP) ? 'triangle' : 'circle', pointHoverRadius: 4, tension: 0.15, spanGaps: false }];
      const m5 = s.med5;
      if (m5 != null) ds.push({ label: '近 5 年中位數', data: A.map(() => m5), borderColor: css('--axis'), borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 0, spanGaps: true });
      const fp = A.map(r => r.fpe), nfp = fp.filter(v => v != null).length;
      if (nfp) ds.push({ label: '預估本益比', data: fp.map(v => v == null ? null : Math.min(v, CAP)), raw: fp, borderColor: c2, backgroundColor: c2, borderWidth: 2, pointRadius: nfp < 3 ? 5 : 2, pointHoverRadius: 5, tension: 0.15, spanGaps: false });
      const lg = [{ t: '歷史本益比', c: c1, ln: 1 }]; if (m5 != null) lg.push({ t: '近 5 年中位數', c: css('--axis'), ln: 1 }); if (nfp) lg.push({ t: '預估本益比（分析師預估）', c: c2, ln: 1 });
      sec.querySelector('#peLg').innerHTML = lg.map(i => `<span><i class="ln" style="background:${i.c}"></i>${i.t}</span>`).join('');
      const nul = A.filter(r => r.pe == null).length;
      sec.querySelector('#peHow').innerHTML = `${ym(A[0].m)} – ${ym(A[A.length - 1].m)} 共 ${A.length} 個月，其中 <b>${A.length - nul}</b> 個月算得出本益比` + (nul ? `，<b>${nul}</b> 個月留白（虧損、累積未滿四季，或 EPS／公布日待確認，原因見數據表）` : '') + (over ? `；<b>${over}</b> 個月超過 ${CAP} 倍（貼在頂端，▲ 標記）` : '') + '。';
      const grid = css('--grid'), tick = css('--tick');
      chart = new Chart(sec.querySelector('#cPE'), { type: 'line', data: { labels, datasets: ds }, options: {
        responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink-2'), borderColor: css('--axis'), borderWidth: 1, padding: 10, cornerRadius: 8,
          callbacks: { title: (it) => it.length ? ym(it[0].label) + ' 月底' : '', label: (c) => { const v = c.dataset.raw ? c.dataset.raw[c.dataIndex] : c.raw; if (v == null) return null; return ` ${c.dataset.label} ${x1(v)}`; }, afterBody: (it) => { const r = A[it[0].dataIndex]; return r.pe == null && r.why ? ' 歷史本益比：' + (WHY[r.why] || '') : ''; } } } },
        scales: { y: { min: 0, max: Math.min(CAP, Math.max(10, Math.ceil(Math.max(...capped.filter(v => v != null), ...fp.filter(v => v != null), m5 || 0) * 1.1 / 5) * 5)), border: { display: false }, grid: { color: grid, drawTicks: false }, ticks: { color: tick, padding: 8, callback: (v) => v + '×', font: { family: 'IBM Plex Mono, monospace', size: 11 } } },
          x: { border: { color: css('--axis') }, grid: { display: false }, ticks: { color: tick, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: { family: 'IBM Plex Mono, monospace', size: 11 }, callback: function (v) { const l = this.getLabelForValue(v); return l ? l.slice(0, 4) + (l.slice(5) === '01' ? '' : '/' + l.slice(5)) : ''; } } } } } });
    };
    sec.querySelector('#peWin').addEventListener('click', (e) => { const bt = e.target.closest('button'); if (!bt) return; years = +bt.dataset.y; sec.querySelectorAll('#peWin button').forEach(x => x.setAttribute('aria-pressed', String(x === bt))); draw(); });
    draw();
    let t; const re = () => { clearTimeout(t); t = setTimeout(draw, 60); };
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', re);
    new MutationObserver(re).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    sec.hidden = false;
    const gl = document.getElementById('gloss');
    if (gl) gl.insertAdjacentHTML('beforeend', [
      ['本益比', 'P/E ratio', '市場用幾倍的價格買這家公司一年的獲利。倍數高代表市場願意為每 1 元獲利付更高的價格（常見於預期成長快的公司），低則相反；高低不代表貴或便宜。', '月底收盤價 ÷ 當時已公布的近四季 EPS 加總'],
      ['近四季 EPS', 'Trailing EPS', '最近連續四季的每股盈餘加總。「當時已公布」指財報公布日（rd）不晚於該月最後交易日。', '最近 4 個已公布季度的 EPS 相加'],
      ['歷史百分位', 'Percentile', '最新本益比在過去 10 年每個月的本益比中排第幾。例：第 80 百分位＝過去 10 年有 80% 的月份本益比比現在低。', '低於現值的月份數 ÷ 有本益比的月份數'],
      ['預估本益比', 'Forward P/E', '用分析師對「未來 12 個月」EPS 的平均預估來算的本益比。預估會被修正，美股多為調整後 EPS，不能和歷史本益比直接相減。', '月底收盤價 ÷ 未來 12 個月預估 EPS'],
      ['未來 12 個月 EPS', 'NTM EPS', '分析師按會計年度給今年度與下年度預估，依今年度剩餘天數加權成未來 12 個月。', 'w×今年度預估 ＋ (1−w)×下年度預估；w＝今年度剩餘天數 ÷ 365'],
    ].map(x => `<div class="item"><dt>${x[0]}<code>${x[1]}</code></dt><dd>${x[2]}</dd><dd><span class="f">${x[3]}</span></dd></div>`).join(''));
    const sl = document.getElementById('srcList');
    if (sl) sl.insertAdjacentHTML('beforeend', `<li>股價：Yahoo Finance 日線 Close（已依股票分割調整、不含股利調整；每月由 GitHub Actions 抓取，台股另與證交所收盤價交叉核對）。財報公布日（rd）與 EPS 見各公司 SOURCES.md。預估本益比使用 Yahoo Finance 的分析師 EPS 預估（非財報數字）。</li>`);
    if (!hasPE) sec.querySelector('#peHow').innerHTML += ' 目前還沒有任何一個月算得出本益比。';
  }
  return { mount, brief, WHY, CAP, x1, ym };
})();
