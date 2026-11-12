/* 體質總覽：四組指標（成長、獲利品質、資本效率、估值）一張表，點一列才展開那個指標的歷史圖（一次只開一張，手機不會太長）。
   資料：N.Q（標準季度序列）、LT.metrics、D.valuation（本益比）、D.health（tools/health.py 算出的新指標）。這裡只做「畫」與中位數、百分位。
   算不出來的格子顯示原因（不是空白）。由 LT.render() 呼叫 HEALTH.mount()。 */
const HEALTH = (() => {
  const WHY = { missing: '欄位待確認', neg: '分母不是正數', tax: '有效稅率不合理', loss: '稅前虧損或預估成長 ≤ 0，不適用', nopx: '沒有分析師預估', price: '股價待確認', short: '已公布未滿四季', none: '沒有資料' };
  const num = (v) => v != null && isFinite(v);
  function stat(series, step) {
    const v = series.filter(p => num(p[1])); if (!v.length || series[series.length - 1][1] == null) return { now: null };
    const now = series[series.length - 1][1];
    const tail = (n) => series.slice(-n).map(p => p[1]).filter(num);
    const w5 = tail(5 * step), w10 = tail(10 * step), srt = (a) => a.slice().sort((x, y) => x - y);
    const med = w5.length >= Math.max(4, step) ? srt(w5)[Math.floor((w5.length - 1) / 2)] / 2 + srt(w5)[Math.ceil((w5.length - 1) / 2)] / 2 : null;
    let pct = null; if (w10.length >= 2 * step) { const b = w10.filter(x => x < now).length, e = w10.filter(x => x === now).length; pct = Math.round((b + e / 2) / w10.length * 100); }
    return { now, nowLabel: series[series.length - 1][0], med, pct };
  }
  function lastWhy(arr, key) { for (let i = arr.length - 1; i >= 0; i--) { const w = arr[i].why && arr[i].why[key]; if (arr[i][key] != null) return null; if (w) return w; } return 'none'; }
  const F = { pc: (v) => LT.pc(v), pp: (v) => LT.pc(v, 1), x: (v) => v.toFixed(1) + ' 倍', x2: (v) => v.toFixed(2), money: (v, u) => LT.f0(v) + ' ' + u };

  function rows(N) {
    const M = LT.metrics(N), Q = N.Q, D = N.D, H = D.health, V = D.valuation, u = N.unitShort;
    const lab = (i) => Q[i].q;
    const yoy = (arr) => arr.map((v, k) => k >= 4 && num(v) && arr[k - 4] > 0 && v > 0 ? [lab(k), (v / arr[k - 4] - 1) * 100] : [lab(k), null]);
    const ser = (arr) => arr.map((v, k) => [lab(k), num(v) ? v : null]);
    const fcfRate = M.ttm.map((r, k) => r && M.ttmFcf[k] != null ? M.ttmFcf[k] / r * 100 : null);
    const hq = H ? H.quarterly : [], hm = H ? H.monthly : [];
    const out = [
      { g: '成長', n: '營收年增（近四季）', s: yoy(M.ttm), f: F.pc, st: 4 },
      { g: '成長', n: 'EPS 年增（近四季）', s: yoy(M.ttmEps), f: F.pc, st: 4 },
      { g: '獲利品質', n: '毛利率（近四季）', s: ser(M.ttmGm), f: F.pc, st: 4 },
      { g: '獲利品質', n: '營業利益率（近四季）', s: ser(M.ttmOm), f: F.pc, st: 4 },
      { g: '獲利品質', n: '自由現金流率（近四季）', s: ser(fcfRate), f: F.pc, st: 4 },
      { g: '資本效率', n: 'ROIC', s: hq.map(x => [x.q, x.roic]), f: F.pc, st: 4, why: H && lastWhy(hq, 'roic') },
      { g: '資本效率', n: 'ROE', s: hq.map(x => [x.q, x.roe]), f: F.pc, st: 4, why: H && lastWhy(hq, 'roe') },
      { g: '資本效率', n: '近四季回購金額', s: hq.map(x => [x.q, x.buybackTtm]), f: (v) => F.money(v, u), st: 4, why: H && lastWhy(hq, 'buybackTtm') || (H ? null : 'missing'), nostat: true },
      { g: '資本效率', n: '稀釋股數年增', s: hq.map(x => [x.q, x.dilYoy]), f: F.pc, st: 4, why: H && lastWhy(hq, 'dilYoy') },
    ];
    const vm = V ? V.monthly : [];
    out.push({ g: '估值', n: '本益比', s: vm.map(x => [x.m, x.pe]), f: F.x, st: 12, why: vm.length ? lastWhy(vm, 'pe') : 'none' });
    out.push({ g: '估值', n: '預估本益比', tag: 'e', s: vm.map(x => [x.m, x.fpe]), f: F.x, st: 12, why: 'nopx' });
    out.push({ g: '估值', n: '本益成長比（PEG）', tag: 'e', s: hm.map(x => [x.m, x.peg]), f: F.x2, st: 12, why: H && lastWhy(hm, 'peg') });
    out.push({ g: '估值', n: '自由現金流殖利率', s: hm.map(x => [x.m, x.fcfY]), f: F.pc, st: 12, why: H && lastWhy(hm, 'fcfY') });
    out.push({ g: '估值', n: '企業價值對營收（EV/Sales）', s: hm.map(x => [x.m, x.evS]), f: F.x, st: 12, why: H && lastWhy(hm, 'evS') });
    return out.map(r => Object.assign(r, stat(r.s, r.st)));
  }

  function chart(r) {
    const pts = r.s.map((p, i) => [i, p[1]]).filter(p => num(p[1]));
    if (pts.length < 2) return '<p class="how">資料點不足，畫不出歷史圖。</p>';
    const W = 640, H = 190, pl = 44, pr = 10, pt = 10, pb = 22;
    const ys = pts.map(p => p[1]); let lo = Math.min(...ys), hi = Math.max(...ys); if (num(r.med)) { lo = Math.min(lo, r.med); hi = Math.max(hi, r.med); } if (hi === lo) { hi += 1; lo -= 1; }
    const X = (i) => pl + i / (r.s.length - 1) * (W - pl - pr), Y = (y) => H - pb - (y - lo) / (hi - lo) * (H - pt - pb);
    const d = pts.map((p, k) => (k ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join(' ');
    const fmt = (v) => Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
    const med = num(r.med) ? `<line x1="${pl}" x2="${W - pr}" y1="${Y(r.med).toFixed(1)}" y2="${Y(r.med).toFixed(1)}" stroke="var(--s2)" stroke-dasharray="4 4"/><text x="${W - pr}" y="${(Y(r.med) - 4).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--s2)">近 5 年中位數 ${fmt(r.med)}</text>` : '';
    const zero = lo < 0 && hi > 0 ? `<line x1="${pl}" x2="${W - pr}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="var(--axis)"/>` : '';
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${r.n} 歷史圖" style="max-width:${W}px">${zero}${med}
      <text x="${pl - 4}" y="${pt + 8}" text-anchor="end" font-size="10" fill="var(--muted)">${fmt(hi)}</text><text x="${pl - 4}" y="${H - pb}" text-anchor="end" font-size="10" fill="var(--muted)">${fmt(lo)}</text>
      <text x="${pl}" y="${H - 6}" font-size="10" fill="var(--muted)">${r.s[0][0]}</text><text x="${W - pr}" y="${H - 6}" text-anchor="end" font-size="10" fill="var(--muted)">${r.s[r.s.length - 1][0]}</text>
      <path d="${d}" fill="none" stroke="var(--s1)" stroke-width="1.8" stroke-linejoin="round"/></svg>`;
  }

  function mount(secEl, N) {
    if (!secEl || document.getElementById('health')) return;
    const R = rows(N), groups = ['成長', '獲利品質', '資本效率', '估值'];
    const sec = document.createElement('section'); sec.id = 'health';
    const cell = (r) => {
      if (r.now == null) return `<td colspan="3" class="muted">—　<small>${WHY[r.why] || WHY.none}</small></td>`;
      return `<td>${r.f(r.now)}<small>${r.nowLabel}</small></td><td>${r.med == null || r.nostat ? '—' : r.f(r.med)}</td><td>${r.pct == null || r.nostat ? '—' : '第 ' + r.pct + ' 百分位'}</td>`;
    };
    let body = '';
    groups.forEach(g => R.filter(r => r.g === g).forEach((r, i, a) => {
      const id = 'h' + R.indexOf(r);
      body += `<tr class="h-row" data-id="${id}" tabindex="0" role="button" aria-expanded="false">${i === 0 ? `<th class="h-grp" rowspan="${a.length * 2}" scope="rowgroup">${g}</th>` : ''}<td class="h-name">${r.n}${r.tag ? ' ' + SUM.tag(r.tag) : ''}</td>${cell(r)}<td class="h-spark">${LT.spark(r.s.slice(-40).map(p => p[1]), {})}</td></tr>
        <tr class="h-chart" id="${id}" hidden><td colspan="6">${chart(r)}</td></tr>`;
    }));
    sec.innerHTML = `<div class="sec-head"><span class="sec-tag">指標總覽</span><h2>體質總覽</h2>
      <p class="sub">成長、獲利品質、資本效率、估值四組。每一列點開，才看那個指標的歷史圖。算不出來的格子寫明原因，不是空白。</p></div>
      <div class="card"><div class="tbl-wrap"><table class="sum-tbl h-tbl"><thead><tr><th></th><th>指標</th><th>現在</th><th>近 5 年中位數</th><th>近 10 年位置</th><th>趨勢</th></tr></thead><tbody>${body}</tbody></table></div>
      <p class="how">公式固定：ROE ＝ 近四季淨利 ÷ 平均股東權益；ROIC ＝ 近四季稅後營業利益 ÷ 平均（股東權益 ＋ 有息負債 − 現金與投資），這是本站公式，各家算法不同，不可直接拿去比別處的數字；自由現金流殖利率 ＝ 近四季自由現金流 ÷ 市值；EV/Sales ＝（市值 ＋ 有息負債 − 現金與投資）÷ 近四季營收；PEG ＝ 預估本益比 ÷ 預估 EPS 成長率（分析師預估，只有有預估快照的月份才有，不回填）。市值用「當時已公布」的最新一季期末股數。「近 10 年位置」是目前數字在過去 10 年裡的百分位，高低不代表貴或便宜。</p></div>`;
    secEl.parentNode.insertBefore(sec, secEl.nextSibling);
    const tb = sec.querySelector('tbody');
    const toggle = (row) => { const open = row.getAttribute('aria-expanded') === 'true'; tb.querySelectorAll('.h-row').forEach(x => { x.setAttribute('aria-expanded', 'false'); document.getElementById(x.dataset.id).hidden = true; }); if (!open) { row.setAttribute('aria-expanded', 'true'); document.getElementById(row.dataset.id).hidden = false; } };
    tb.addEventListener('click', e => { const row = e.target.closest('.h-row'); if (row) toggle(row); });
    tb.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { const row = e.target.closest('.h-row'); if (row) { e.preventDefault(); toggle(row); } } });
    const nav = document.getElementById('secnav');
    if (nav && !nav.querySelector('[href="#health"]')) { const a = document.createElement('a'); a.href = '#health'; a.textContent = '體質總覽'; const lt = nav.querySelector('a[href="#longterm"]'); lt ? lt.after(a) : nav.appendChild(a); }
  }
  return { mount, rows };
})();
