/* 體質總覽：四組指標（成長、獲利品質、資本效率、估值）一張表，點一列才展開那個指標的歷史圖（一次只開一張，手機不會太長）。
   資料：N.Q（標準季度序列）、LT.metrics、D.valuation（本益比）、D.health（tools/health.py 算出的新指標）。這裡只做「畫」與中位數、百分位。
   算不出來的格子顯示原因（不是空白）。由 LT.render() 呼叫 HEALTH.mount()。 */
const HEALTH = (() => {
  const WHY = { missing: '欄位待確認', nosbc: '股票酬勞（sbc）欄位待確認：尚未收錄單季股票酬勞資料（非 SEC XBRL 申報或尚待合併）', neg: '分母不是正數', tax: '有效稅率不合理', loss: '稅前虧損或預估成長 ≤ 0，不適用', nopx: '沒有分析師預估', price: '股價待確認', short: '已公布未滿四季', none: '沒有資料', noidx: '沒有資料', nobond: '網站沒有該國公債資料', norates: '讀不到公債資料', noisy: '本益比超過 200 倍', nodps: '本站沒有收錄每股股利', cash_rich: '現金大於股東權益＋有息負債（輕資產／超額現金體質，本業稅後營業利益為正）' };
  const num = (v) => v != null && isFinite(v);
  const TIPS = {"ROE": "報酬率是我們先問的問題：股東投入一塊錢，一年能賺回多少。長期穩定在 15% 以上，才像有護城河。", "營收年增（近四季）": "成長只有在投入資本的報酬率高的時候，才創造價值。先看報酬率，再看長得多快。", "EPS 年增（近四季）": "每股盈餘長得快，也要問報酬率有沒有跟著撐住。成長要配上高報酬率才值錢。", "毛利率（近四季）": "好生意有對手搶不走的優勢，常表現在長期穩定的高毛利率。看方向，也看穩不穩。", "營業利益率（近四季）": "長期穩定的高利潤率，是護城河留下的痕跡。突然變薄要問為什麼。", "自由現金流率（近四季）": "真正屬於股東的錢，是賺到的現金扣掉維持生意必須花的錢。這一列還沒扣股票酬勞；股票酬勞是真實費用，扣掉之後的版本在「巴菲特常看」那一組（扣股票酬勞後的自由現金流率）。沒有酬勞資料的公司，那一列會寫明算不出來的原因。", "ROIC": "投入的每一塊錢能賺回多少，是我們最先問的問題。長期高而且穩，才是護城河的證據。", "近四季回購金額": "管理層最重要的工作是決定賺來的錢怎麼用。回購只有在價格低於價值時，才對股東有利。", "稀釋股數年增": "股票酬勞是真實費用。股數一直變多，等於老股東被稀釋；回購讓股數變少才是好事。", "本益比": "用明顯低於價值的價格買，留下犯錯的空間。利率越高，所有資產的價值被拉得越低，所以也要跟公債比。", "自由現金流殖利率": "股票要跟公債比。利率越高，同樣的現金流值得付的價格越低。", "企業價值對營收（EV/Sales）": "營收不是獲利。這個指標只適合還沒有穩定獲利的公司或循環股，穩定獲利的公司請看本益比。", "預估本益比": "這是分析師預估，不是財報數字。他們不靠預估做決定。", "本益成長比（PEG）": "這是分析師預估，不是財報數字。他們不靠預估做決定。"};
  const ROE_TIP = 'ROE 很高也可能是因為大量回購或槓桿讓股東權益變小，不一定代表生意變強。蘋果就是例子。要和 ROIC、自由現金流一起看。';
  const GOODWILL_TIP = '連續併購的公司，收購溢價會記成資產負債表上的「商譽」、墊高投入資本與股東權益分母，使帳面 ROIC／ROE 偏低；評估管理層併購成績看帳面 ROIC，評估本業產品力請同時對照毛利率與自由現金流率。';
  function stat(series, step) {
    const v = series.filter(p => num(p[1])); if (!v.length || series[series.length - 1][1] == null) return { now: null };
    const now = series[series.length - 1][1];
    const tail = (n) => series.slice(-n).map(p => p[1]).filter(num);
    const w5 = tail(5 * step), w10 = tail(10 * step), srt = (a) => a.slice().sort((x, y) => x - y);
    const med = step > 1 && w5.length >= Math.max(4, step) ? srt(w5)[Math.floor((w5.length - 1) / 2)] / 2 + srt(w5)[Math.ceil((w5.length - 1) / 2)] / 2 : null;
    let pct = null; if (step > 1 && w10.length >= 2 * step) { const b = w10.filter(x => x < now).length, e = w10.filter(x => x === now).length; pct = Math.round((b + e / 2) / w10.length * 100); }
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
    out.push({ g: '分析師預估', n: '預估本益比', tag: 'e', s: vm.map(x => [x.m, x.fpe]), f: F.x, st: 12, why: 'nopx' });
    out.push({ g: '分析師預估', n: '本益成長比（PEG）', tag: 'e', s: hm.map(x => [x.m, x.peg]), f: F.x2, st: 12, why: H && lastWhy(hm, 'peg') });
    out.push({ g: '估值', n: '自由現金流殖利率', s: hm.map(x => [x.m, x.fcfY]), f: F.pc, st: 12, why: H && lastWhy(hm, 'fcfY') });
    out.push({ g: '估值', n: '企業價值對營收（EV/Sales）', s: hm.map(x => [x.m, x.evS]), f: F.x, st: 12, why: H && lastWhy(hm, 'evS') });
    const BQ = D.buffett, TY = BQ && BQ.tenYear || [], EY = BQ && BQ.ey, QL = BQ && BQ.quality;
    if (BQ && QL) {
      const yr = (k) => TY.map(x => [x.q, x[k]]), wq = (k) => QL.why && QL.why[k];
      out.push({ g: '巴菲特常看', n: '淨利率（近四季）', s: yr('npm'), f: F.pc, st: 1, why: wq('npm'), tip: '賺錢能力的最後一道數字：每 100 元營收留下多少給股東。', nostat: true });
      out.push({ g: '巴菲特常看', n: '資本支出 ÷ 淨利', s: yr('capexNi'), f: (v) => v.toFixed(0) + '%', st: 1, why: wq('capexNi'), tip: '維持生意要花多少錢。比例長期很低的生意，賺到的錢比較能留下來。', nostat: true });
      out.push({ g: '巴菲特常看', n: '自由現金流 ÷ 淨利', s: yr('fcfNi'), f: (v) => v.toFixed(0) + '%', st: 1, why: wq('fcfNi'), tip: '帳面獲利有沒有變成現金。長期接近或高於 100%，盈餘才是真的。', nostat: true });
      out.push({ g: '巴菲特常看', n: '負債幾年還清（有息負債 ÷ 近四季淨利）', s: QL.debtYears == null ? [] : [[QL.q, QL.debtYears]], f: (v) => v.toFixed(1) + ' 年', st: 1, why: wq('debtYears'), tip: '好生意不需要很多負債。負債讓你在壞年份沒有退路。淨負債版本見十年成績單。', nostat: true });
      out.push({ g: '巴菲特常看', n: '每股淨值五年年化成長', s: QL.bvCagr5 == null ? [] : [[QL.q, QL.bvCagr5]], f: F.pc, st: 1, why: wq('bvCagr5'), tip: '留在公司裡的盈餘，有沒有讓每一股的帳面價值長大。', nostat: true });
      const OW = BQ.owner;
      if (OW) {
        const ow = OW.series || [], wo = (k) => (OW.why || {})[k] || (OW.have === 0 ? 'nosbc' : 'missing');
        out.push({ g: '巴菲特常看', n: '股票酬勞占營收（近四季）', s: ow.map(x => [x[0], x[1]]), f: F.pc, st: 4, why: wo('sbcRev'), tip: '股票酬勞是真實的費用，等於用股東的股份付薪水。占營收的比例越高，帳面獲利和自由現金流越被高估。' });
        out.push({ g: '巴菲特常看', n: '扣股票酬勞後的自由現金流率（近四季）', s: ow.map(x => [x[0], x[2]]), f: F.pc, st: 4, why: wo('fcfSbcRate'), tip: '業主盈餘的近似：賺到的現金，扣掉資本支出與股票酬勞。財報沒有拆維持性與成長性資本支出，所以全部資本支出都扣，只是近似。' });
      }
      out.push({ g: '巴菲特常看', n: '盈餘殖利率減十年期公債（百分點）', s: (EY.series || []).map(x => [x[0], x[3]]), f: (v) => (v > 0 ? '+' : '') + v.toFixed(2), st: 12, why: EY.why || EY.bondWhy || 'none', tip: '股票要跟公債比。盈餘殖利率是 100 ÷ 本益比，至少要不輸十年期公債，否則承擔股票風險沒有額外補償。' });
    }
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
    const R = rows(N), groups = ['成長', '獲利品質', '資本效率', '巴菲特常看', '估值'], fgroups = ['分析師預估'];
    const sec = document.createElement('section'); sec.id = 'health';
    const cell = (r) => {
      if (r.now == null) return `<td colspan="3" class="muted">—　<small>${WHY[r.why] || WHY.none}</small></td>`;
      return `<td>${r.f(r.now)}<small>${r.nowLabel}</small></td><td>${r.med == null || r.nostat ? '—' : r.f(r.med)}</td><td>${r.pct == null || r.nostat ? '—' : '第 ' + r.pct + ' 百分位'}</td>`;
    };
    const M = LT.metrics(N), D = N.D;
    const roicRow = R.find(x => x.n === 'ROIC'), latestRoic = roicRow ? roicRow.now : null;
    const shChg5 = D.buffett && D.buffett.buyback ? D.buffett.buyback.shChg5 : null;
    const gmNow = M.gmNow;
    const tipOf = (r) => {
      let t = r.tip || TIPS[r.n] || '';
      if (r.n === 'ROE' && num(r.now) && (r.now > 100 || (r.now >= 30 && num(latestRoic) && r.now > latestRoic * 2))) {
        t += (t ? ' ' : '') + ROE_TIP;
      }
      if ((r.n === 'ROIC' || r.n === 'ROE') && num(shChg5) && shChg5 > 10 && num(r.now) && r.now < 15 && num(gmNow) && gmNow >= 45) {
        t += (t ? ' ' : '') + GOODWILL_TIP;
      }
      return t ? `<p class="how h-tip">${typeof SUM !== 'undefined' ? SUM.tag('v') + ' ' : ''}<b>他們怎麼看（巴菲特＋蒙格，意譯，不是原話）</b>　${t}</p>` : '';
    };
    const build = (gs) => { let body = '';
      gs.forEach(g => R.filter(r => r.g === g).forEach((r, i, a) => {
        const id = 'h' + R.indexOf(r);
        body += `<tr class="h-row" data-id="${id}" tabindex="0" role="button" aria-expanded="false">${i === 0 ? `<th class="h-grp" rowspan="${a.length}" data-n="${a.length}" scope="rowgroup">${g}</th>` : ''}<td class="h-name">${r.n}${r.tag ? ' ' + SUM.tag(r.tag) : ''}</td>${cell(r)}<td class="h-spark">${LT.spark(r.s.slice(-40).map(p => p[1]), {})}</td></tr>
          <tr class="h-chart" id="${id}" hidden><td colspan="5">${chart(r)}${tipOf(r)}</td></tr>`;
      }));
      return body; };
    const head = '<thead><tr><th></th><th>指標</th><th>現在</th><th>近 5 年中位數</th><th>近 10 年位置</th><th>趨勢</th></tr></thead>';
    sec.innerHTML = `<div class="sec-head"><span class="sec-tag">指標總覽</span><h2>體質總覽</h2>
      <p class="sub">成長、獲利品質、資本效率、巴菲特常看、估值五組。每一列點開，看那個指標的歷史圖與「他們怎麼看」。算不出來的格子寫明原因，不是空白。</p></div>
      <div class="card"><div class="tbl-wrap"><table class="sum-tbl h-tbl">${head}<tbody>${build(groups)}</tbody></table></div>
      <details class="bm-det"><summary>分析師預估（他們不用這個做決定）</summary><div class="tbl-wrap"><table class="sum-tbl h-tbl">${head}<tbody>${build(fgroups)}</tbody></table></div></details>
      <p class="how">公式固定：ROE ＝ 近四季淨利 ÷ 平均股東權益；ROIC ＝ 近四季稅後營業利益 ÷ 平均（股東權益 ＋ 有息負債 − 現金與投資），這是本站公式，各家算法不同，不可直接拿去比別處的數字；自由現金流殖利率 ＝ 近四季自由現金流 ÷ 市值；EV/Sales ＝（市值 ＋ 有息負債 − 現金與投資）÷ 近四季營收；PEG ＝ 預估本益比 ÷ 預估 EPS 成長率（分析師預估，只有有預估快照的月份才有，不回填）。市值用「當時已公布」的最新一季期末股數。「近 10 年位置」是目前數字在過去 10 年裡的百分位，高低不代表貴或便宜。</p></div>`;
    secEl.parentNode.insertBefore(sec, secEl.nextSibling);
    // 組別格的 rowspan 只算看得到的列（隱藏的圖表列不算，否則組別格會往下吃到別組的列、整張表錯位）；展開一列時該組 +1
    const grpOf = (row) => { let r = row; while (r && !r.querySelector('.h-grp')) r = r.previousElementSibling; return r && r.querySelector('.h-grp'); };
    const toggle = (row) => { const open = row.getAttribute('aria-expanded') === 'true'; sec.querySelectorAll('.h-row').forEach(x => { x.setAttribute('aria-expanded', 'false'); document.getElementById(x.dataset.id).hidden = true; });
      sec.querySelectorAll('.h-grp').forEach(th => { th.rowSpan = +th.dataset.n; });
      if (!open) { row.setAttribute('aria-expanded', 'true'); document.getElementById(row.dataset.id).hidden = false; const th = grpOf(row); if (th) th.rowSpan = +th.dataset.n + 1; } };
    sec.addEventListener('click', e => { const row = e.target.closest('.h-row'); if (row) toggle(row); });
    sec.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { const row = e.target.closest('.h-row'); if (row) { e.preventDefault(); toggle(row); } } });
    const nav = document.getElementById('secnav');
    if (nav && !nav.querySelector('[href="#health"]')) { const a = document.createElement('a'); a.href = '#health'; a.textContent = '體質總覽'; const lt = nav.querySelector('a[href="#longterm"]'); lt ? lt.after(a) : nav.appendChild(a); }
  }
  return { mount, rows };
})();
