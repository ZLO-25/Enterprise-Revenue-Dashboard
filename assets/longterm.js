/* 長期指標（long-term view）：給「長期投資人」看的指標，全部由 assets/adapters.js 的標準序列 N 算出來。
   不依賴頁面其他變數（台積電頁面沒有載入 common.js），所以自己帶一套小工具。
   提供：
     LT.metrics(N)            → 近四季（TTM）、年化成長（CAGR）、利潤率變化、連續年增季數、自由現金流率…
     LT.freshness(D, today?)  → 資料新鮮度：fresh／aging／overdue
     LT.render(el, N, M)      → 公司頁的「長期觀察」卡片（六格 + 怎麼看）
     LT.badge(F)              → 新鮮度徽章 HTML
     LT.DISCLAIMER            → 各頁共用的完整免責聲明 */
const LT = (() => {
  const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
  const nf2 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const f0 = (n) => n == null || !isFinite(n) ? '—' : nf0.format(n);
  const f2 = (n) => n == null || !isFinite(n) ? '—' : nf2.format(n);
  const pc = (n, d = 1) => n == null || !isFinite(n) ? '—' : n.toFixed(d) + '%';
  const sp = (n, d = 1) => n == null || !isFinite(n) ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(d) + '%';
  const pp = (n, d = 1) => n == null || !isFinite(n) ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(d) + ' 個百分點';
  const cls = (n) => n == null || !isFinite(n) ? '' : (n >= 0 ? 'up' : 'down');
  const sum = (arr) => arr.some(v => v == null) ? null : arr.reduce((a, b) => a + b, 0);
  const win = (Q, i, key, n = 4) => i - n + 1 < 0 ? null : sum(Q.slice(i - n + 1, i + 1).map(q => q[key]));

  /* ---------- 指標 ---------- */
  function metrics(N) {
    const Q = N.Q, n = Q.length, i = n - 1, L = Q[i];
    const ttm = Q.map((_, k) => win(Q, k, 'rev'));
    const ttmNi = Q.map((_, k) => win(Q, k, 'ni'));
    const ttmEps = Q.map((_, k) => win(Q, k, 'eps'));
    const ttmOcf = Q.map((_, k) => win(Q, k, 'ocf'));
    const ttmCapex = Q.map((_, k) => win(Q, k, 'capex'));
    const ttmFcf = ttmOcf.map((v, k) => v == null || ttmCapex[k] == null ? null : v - ttmCapex[k]);
    const ttmGm = Q.map((_, k) => { if (k < 3) return null; const s = Q.slice(k - 3, k + 1); const r = sum(s.map(q => q.rev)); return r ? s.reduce((a, q) => a + q.gm * q.rev, 0) / r : null; });
    const ttmOm = Q.map((_, k) => { if (k < 3) return null; const s = Q.slice(k - 3, k + 1); if (s.some(q => q.om == null)) return null; const r = sum(s.map(q => q.rev)); return r ? s.reduce((a, q) => a + q.om * q.rev, 0) / r : null; });
    const g = (a, b) => a != null && b != null && b > 0 && a > 0 ? (a / b - 1) * 100 : null;
    const cagr = (years) => { const k = i - years * 4; return k >= 3 && ttm[k] > 0 && ttm[i] > 0 ? (Math.pow(ttm[i] / ttm[k], 1 / years) - 1) * 100 : null; };
    const firstTtm = ttm.findIndex(v => v != null);
    const allYears = firstTtm >= 0 ? (i - firstTtm) / 4 : 0;
    const cagrAll = allYears >= 1 && ttm[firstTtm] > 0 ? (Math.pow(ttm[i] / ttm[firstTtm], 1 / allYears) - 1) * 100 : null;
    let streak = 0; for (let k = i; k >= 0 && Q[k].yoy != null && Q[k].yoy > 0; k--) streak++;
    const last20 = Q.slice(Math.max(0, n - 20)).filter(q => q.yoy != null);
    const posShare = last20.length ? last20.filter(q => q.yoy > 0).length / last20.length * 100 : null;
    const recordTtm = ttm[i] != null && ttm.every(v => v == null || v <= ttm[i]);
    const back = (arr, k) => i - k >= 0 ? arr[i - k] : null;
    return {
      L, ttm, ttmNi, ttmEps, ttmFcf, ttmGm, ttmOm,
      ttmRev: ttm[i], ttmRevYoy: g(ttm[i], back(ttm, 4)), recordTtm,
      ttmEpsNow: ttmEps[i], ttmEpsYoy: g(ttmEps[i], back(ttmEps, 4)),
      ttmNm: ttm[i] && ttmNi[i] != null ? ttmNi[i] / ttm[i] * 100 : null,
      ttmFcfNow: ttmFcf[i], ttmFcfM: ttm[i] && ttmFcf[i] != null ? ttmFcf[i] / ttm[i] * 100 : null,
      ttmFcfM3y: back(ttm, 12) && back(ttmFcf, 12) != null ? back(ttmFcf, 12) / back(ttm, 12) * 100 : null,
      cagr3: cagr(3), cagr5: cagr(5), cagrAll, allYears: Math.round(allYears * 10) / 10,
      gmNow: ttmGm[i], gm3y: back(ttmGm, 12), gmDelta: ttmGm[i] != null && back(ttmGm, 12) != null ? ttmGm[i] - back(ttmGm, 12) : null,
      omNow: ttmOm[i], om3y: back(ttmOm, 12), omDelta: ttmOm[i] != null && back(ttmOm, 12) != null ? ttmOm[i] - back(ttmOm, 12) : null,
      streak, posShare, posN: last20.length, yoy: L.yoy, qoq: L.qoq,
      years: Math.round((n / 4) * 10) / 10,
    };
  }

  /* ---------- 新鮮度 ---------- */
  function freshness(D, today) {
    const t = today || new Date();
    const iso = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
    const days = Math.round((Date.parse(iso) - Date.parse(D.asOf)) / 86400000);
    const overdue = (D.events || []).filter(e => e.date < iso && e.date > D.asOf && !e.est);
    if (overdue.length) return { status: 'overdue', days, text: `${overdue[0].date.slice(5).replace('-', '/')} 有公布日已過，資料尚未更新`, label: '待更新' };
    if (days > 21) return { status: 'aging', days, text: `資料已 ${days} 天未更新`, label: `${days} 天前` };
    return { status: 'fresh', days, text: days <= 0 ? '今天更新' : `${days} 天前更新`, label: days <= 0 ? '今天' : `${days} 天前` };
  }
  const badge = (F) => `<span class="fresh fresh-${F.status}" title="${F.text}">${F.label}</span>`;

  /* ---------- 迷你走勢圖（inline SVG，不用 Chart.js） ---------- */
  function spark(vals, opts = {}) {
    const v = vals.map(x => x == null || !isFinite(x) ? null : x);
    const pts = v.map((y, i) => [i, y]).filter(p => p[1] != null);
    if (pts.length < 2) return '';
    const W = 120, H = 34, pad = 3;
    const ys = pts.map(p => p[1]); let lo = Math.min(...ys, opts.zero ? 0 : Infinity), hi = Math.max(...ys, opts.zero ? 0 : -Infinity);
    if (hi === lo) { hi += 1; lo -= 1; }
    const X = (i) => pad + i / (v.length - 1) * (W - 2 * pad), Y = (y) => H - pad - (y - lo) / (hi - lo) * (H - 2 * pad);
    const d = pts.map((p, k) => (k ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join(' ');
    const last = pts[pts.length - 1];
    const zero = opts.zero && lo < 0 && hi > 0 ? `<line x1="${pad}" x2="${W - pad}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="var(--axis)" stroke-dasharray="2 3"/>` : '';
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">${zero}<path d="${d}" fill="none" stroke="var(--s1)" stroke-width="1.6" stroke-linejoin="round"/><circle cx="${X(last[0]).toFixed(1)}" cy="${Y(last[1]).toFixed(1)}" r="2.4" fill="var(--s1)"/></svg>`;
  }

  /* ---------- 公司頁的「長期觀察」卡片 ---------- */
  function render(el, N, M) {
    const u = N.unitShort, K = 20, tail = (arr) => arr.slice(-K);
    const tiles = [
      { label: '近四季營收（TTM）', value: f0(M.ttmRev), unit: u, delta: `年增 <span class="${cls(M.ttmRevYoy)}">${sp(M.ttmRevYoy)}</span>`, chip: M.recordTtm ? '歷史新高' : '', sp: spark(tail(M.ttm)) },
      { label: '營收年化成長（CAGR）', value: M.cagr3 == null ? '—' : M.cagr3.toFixed(1), unit: '% / 3 年', delta: `5 年 ${pc(M.cagr5)} · 全期間 ${pc(M.cagrAll)}（${M.allYears} 年）`, sp: spark(tail(N.Q.map(q => q.yoy)), { zero: true }) },
      { label: '近四季 EPS', value: f2(M.ttmEpsNow), unit: N.epsUnit, delta: `年增 <span class="${cls(M.ttmEpsYoy)}">${sp(M.ttmEpsYoy)}</span> · 近四季淨利率 ${pc(M.ttmNm)}`, sp: spark(tail(M.ttmEps), { zero: true }) },
      { label: '毛利率（近四季加權）', value: pc(M.gmNow), unit: '', delta: `3 年前 ${pc(M.gm3y)} → <span class="${cls(M.gmDelta)}">${pp(M.gmDelta)}</span>`, sp: spark(tail(M.ttmGm)) },
      { label: '自由現金流率（近四季）', value: pc(M.ttmFcfM), unit: '', delta: M.ttmFcfNow == null ? '現金流資料不足四季' : `自由現金流 ${f0(M.ttmFcfNow)} ${u} · 3 年前 ${pc(M.ttmFcfM3y)}`, sp: spark(tail(M.ttmFcf), { zero: true }) },
      { label: '連續營收年增季數', value: String(M.streak), unit: '季', delta: `近 ${M.posN} 季有 ${pc(M.posShare, 0)} 的季度年增為正`, sp: spark(tail(N.Q.map(q => q.yoy)), { zero: true }) },
    ];
    el.innerHTML = `<div class="lt-grid">${tiles.map(t => `
      <div class="kpi lt">
        <span class="label">${t.label}</span>
        <span class="value">${t.value}${t.unit ? `<small>${t.unit}</small>` : ''}</span>
        <span class="delta">${t.delta}</span>
        ${t.sp}
        ${t.chip ? `<span class="chip">${t.chip}</span>` : ''}
      </div>`).join('')}</div>
      <p class="how lt-how"><b>怎麼看：</b>單季數字會被季節與一次性因素干擾，所以這裡全部用「近四季加總（TTM）」把一年看成一個整體；
      年化成長（CAGR）回答「平均每年長多少」，比單季年增率更能看出長期速度；毛利率與自由現金流率回答「生意有沒有越做越好賺、賺到的是不是真現金」；
      連續年增季數回答「成長穩不穩」。每一格的小折線是最近 ${K} 季的走勢。這些都是公開財報的整理與計算，不是預測，也不構成投資建議。</p>`;
  }

  const DISCLAIMER = '本站為公開資料的整理與計算，不構成任何投資建議、推薦或要約；數字以各公司公告與主管機關申報文件為準，整理過程可能有誤或延遲，使用前請自行核對。' +
    '「調整後」（non-GAAP）指標為各公司自訂口徑，不同公司間不可直接比較；標「待確定」的事件只是媒體報導、公司尚未證實。過去的財務表現不代表未來結果。';

  return { metrics, freshness, badge, spark, render, DISCLAIMER, f0, f2, pc, sp, pp, cls };
})();
