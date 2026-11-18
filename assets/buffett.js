/* 巴菲特＋蒙格檢查表：個股頁「論點卡」之後。四關各一張小卡（他們問什麼、數字、他們怎麼看、問自己）＋「反過來想」。
   數字全部來自 tools/buffett.py 在建置時算好的 D.buffett（前端只畫，不重算）；論點卡風險來自 D.thesis。
   觀念文字是意譯，不是原話（清單在 docs/BUFFETT_MUNGER.md），一律標「觀點」。第 ① 關與「反過來想」只有提問：不做輸入框、不存檔。
   由 LT.render() 呼叫 BUFFETT.mount()，所有公司頁（通用、台積電、PLTR）共用。 */
const BUFFETT = (() => {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const WHY = { missing: '欄位待確認', neg: '分母不是正數或虧損', short: '資料不夠長', noprice: '沒有股價資料', loss: '虧損或本益比不可用', noisy: '本益比超過 200 倍，近四季 EPS 接近零', norates: '讀不到公債資料',
    nobond: '網站沒有該國公債資料', noidx: '網站沒有不含股息的同幣別指數資料', nodps: '本站沒有收錄每股股利', nosbc: '股票酬勞（sbc）欄位待確認：這家公司的來源不是 SEC 申報檔，尚未從年報讀取', none: '沒有資料' };
  const num = (v) => v != null && isFinite(v);
  const why = (c) => `<span class="bm-why">算不出來：${esc(WHY[c] || WHY.none)}</span>`;
  const pc = (v, d = 1) => num(v) ? v.toFixed(d) + '%' : '—';
  const sg = (v, d = 1) => num(v) ? (v > 0 ? '+' : '') + v.toFixed(d) : '—';
  const x1 = (v) => num(v) ? v.toFixed(1) + ' 倍' : '—';
  const TYPE = { compounder: '穩健複利', growth: '高成長', cyclical: '循環股', turnaround: '轉機／早期', option: '選擇權' };
  const tag = (t) => (typeof SUM !== 'undefined' ? SUM.tag(t) : '');
  const f = (t) => `<small class="bm-f">怎麼算：${t}</small>`;
  const n = (label, val, formula) => `<div class="bm-n"><span class="bm-nl">${label}</span><b class="bm-nv">${val}</b>${formula ? f(formula) : ''}</div>`;
  const view = (concept, text) => `<p class="bm-view"><span class="bm-vt">他們怎麼看（巴菲特＋蒙格口吻，意譯，不是原話）${concept}</span>${text}</p>`;
  const ask = (q) => `<p class="bm-ask">他們問：${q}</p>`;
  const self = (items) => `<div class="bm-self"><b>問自己</b><ul>${items.map(i => `<li>${i}</li>`).join('')}</ul></div>`;
  const card = (id, title, body) => `<div class="bm-card" id="${id}"><h3>${title}</h3>${body}</div>`;
  const table = (head, rows) => `<div class="tbl-wrap"><table class="sum-tbl bm-tbl"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((c, i) => i ? `<td>${c}</td>` : `<th scope="row">${c}</th>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const cell = (v, fmt, w) => num(v) ? fmt(v) : `<span class="bm-why" title="${esc(WHY[w] || WHY.none)}">—</span>`;

  /* ① 我看得懂嗎（能力圈）：只有提問；公司簡介就在本頁資料裡（D.profile） */
  function gate1(D) {
    const P = D.profile, li = (arr) => (arr || []).slice(0, 4).map(x => `<li>${x.n ? `<b>${esc(x.n)}</b>：${esc(x.d)}` : esc(x)}</li>`).join('');
    const prof = P ? `<details class="bm-det"><summary>這家公司靠什麼賺錢（公司簡介）</summary>
      <h4>主力產品</h4><ul class="sum-list">${li(P.products)}</ul><h4>解決什麼痛點</h4><ul class="sum-list">${li(P.pains)}</ul>
      <h4>護城河（${P.status === 'approved' ? '' : '草稿，待 ZL 確認；'}Claude 的判斷）</h4><ul class="sum-list">${li(P.moat)}</ul></details>` : '<p class="bm-why">公司簡介尚未整理（待確認），先用自己的話寫下這家公司怎麼賺錢。</p>';
    return card('bmG1', '① 我看得懂嗎（能力圈）', ask('這門生意，我真的看得懂嗎？') +
      view('・能力圈', '我們只投資自己看得懂的生意。看不懂的，放進「太難」那一堆，這樣做一點都不丟臉。') +
      self(['十年後，這家公司靠什麼賺錢？我能用一句話講給別人聽嗎？', '如果股市關門五年，我還願意持有它嗎？', '看不懂不丟臉：我可以把它放進「太難」那一堆，分析結論選「太難，跳過」。']) + prof);
  }

  /* ② 護城河撐得久嗎 */
  function gate2(B) {
    const S = B.summary, R = B.record, Y = B.tenYear || [];
    if (!S) return card('bmG2', '② 護城河撐得久嗎', ask('這門生意的好表現，能撐很多年嗎？') + `<p>${why('short')}（不到四季）</p>`);
    const roe20 = S.roeOk, roe40 = S.roeOk40, w = S.why || {};
    const nums = `<div class="bm-nums">
      ${n('ROE 達 15% 的季數（近 20 季）', roe20.n ? `${roe20.ok} / ${roe20.n}` : why('missing'), 'ROE ＝ 近四季淨利 ÷ 平均股東權益；15% 是巴菲特常看的長期門檻（意譯）')}
      ${n('ROE 達 15% 的季數（近 40 季）', roe40.n ? `${roe40.ok} / ${roe40.n}` : why('missing'), '同上，只算 ROE 有值的季')}
      ${n('每股盈餘比前一年高', S.epsUp.n ? `${S.epsUp.up} / ${S.epsUp.n} 年` : why('short'), '年度點：每隔四季一點；近四季 EPS 比前一點高就算一年')}
      ${n('虧損年數', S.years ? `${S.lossYears} / ${S.years} 年` : why('missing'), '年度點裡近四季 EPS ≤ 0 的個數')}
      ${n('毛利率三年變化', S.gmChg3 == null ? why(w.gmChg3 || 'missing') : `${sg(S.gmChg3)} 個百分點`, '最新年度點的近四季毛利率 − 三年前年度點')}
      ${n('ROE 連續三年下滑', S.roeTrend3 == null ? why(w.roeTrend3 || 'missing') : (S.roeTrend3 ? '是' : '否'), '最近 4 個年度點的 ROE 一點比一點低')}
      ${(B.structure && B.structure.basis === 'roic') ? n('ROIC 連續三年下滑（這張論點卡的核心是 ROIC）', S.roicTrend3 == null ? why(w.roicTrend3 || 'missing') : (S.roicTrend3 ? '是' : '否'), '最近 4 個年度點的 ROIC 一點比一點低；論點卡的結構檢查用這個') : ''}
    </div>`;
    const rows = Y.slice().reverse().map(r => [esc(r.q), cell(r.eps, v => v.toFixed(2), (r.why || {}).eps), cell(r.epsYoy, v => sg(v, 0) + '%', (r.why || {}).epsYoy), cell(r.roe, v => v.toFixed(1) + '%', (r.why || {}).roe),
      cell(r.gm, v => v.toFixed(1) + '%', (r.why || {}).gm), cell(r.npm, v => v.toFixed(1) + '%', (r.why || {}).npm), cell(r.fcfNi, v => v.toFixed(0) + '%', (r.why || {}).fcfNi),
      cell(r.capexNi, v => v.toFixed(0) + '%', (r.why || {}).capexNi), cell(r.netDebtNi, v => v.toFixed(1), (r.why || {}).netDebtNi), cell(r.bvps, v => v.toFixed(2), (r.why || {}).bvps)]);
    const tbl = `<details class="bm-det"><summary>十年成績單（${Y.length} 個年度點）</summary>${table(['近四季至', 'EPS', 'EPS 年增', 'ROE', '毛利率', '淨利率', '自由現金流 ÷ 淨利', '資本支出 ÷ 淨利', '淨負債 ÷ 淨利（年）', '每股淨值'], rows)}
      <p class="how">每一列是「該季與前三季加總」的近四季，往前每隔四季取一點，最多 11 點；缺任一季就留白。淨負債 ＝ 有息負債 − 現金與投資，負數代表現金比負債多；淨利 ≤ 0 時三個「÷ 淨利」欄不算。每股淨值 ＝ 股東權益 ÷ 期末流通股數。
      ${S.bvCagr5 == null ? '' : `每股淨值五年年化成長 ${pc(S.bvCagr5)}。`}</p>
      <p class="how"><b>穩健複利的資格（十年紀錄）</b>：${R.tenYearOk == null ? '算不出來（' + esc((R.why || []).join('；')) + '）' : (R.tenYearOk ? '通過' : '未通過（' + esc((R.why || []).join('；')) + '）')}。規則：至少 40 季、近 10 個年度點沒有虧損、近 40 季 ROE 有值 20 季以上且 80% 以上達 15%。</p></details>`;
    return card('bmG2', '② 護城河撐得久嗎', ask('這門生意的好表現，能撐很多年嗎？') +
      view('・護城河、報酬率先於成長', '好生意有對手搶不走的優勢，會表現在年復一年的高報酬率與穩定的毛利率。我們先看一塊錢能賺回多少，再看它長得多快；成長只有在報酬率高的時候才創造價值。') +
      nums + self(['對手要花多少錢、多少年，才追得上這項優勢？', '過去十年，它的報酬率有沒有在壞年份撐住？']) + tbl);
  }

  /* ③ 管理層會用錢嗎 */
  function gate3(B) {
    const BB = B.buyback, RT = B.retained, OW = B.owner;
    if (!BB) return card('bmG3', '③ 管理層會用錢嗎', ask('賺來的錢，管理層怎麼用？') + `<p>${why('short')}（不到四季）</p>`);
    const rows = (BB.rows || []).filter(r => num(r.buyback) && r.buyback > 0);
    const cnt = (w) => rows.filter(r => r.where === w).length, tagged = rows.filter(r => r.where).length;
    const wh = tagged ? `偏貴時買 ${cnt('偏貴時買')} 年、接近平常 ${cnt('接近平常')} 年、偏便宜時買 ${cnt('偏便宜時買')} 年` : (rows.length ? why('short') : '這段期間沒有回購（回購金額為 0 或待確認）');
    const rat = RT.ratio == null ? why(RT.why || 'missing') : `${RT.ratio.toFixed(2)} 元${RT.ratio >= 1 ? '' : '（不到 1 元）'}`;
    const nums = `<div class="bm-nums">
      ${n('回購買在什麼價位', wh, '每個年度點：那 12 個月的月底平均本益比，對比現在的近 5 年本益比中位數；高於 1.1 倍算偏貴，低於 0.9 倍算偏便宜（只看有回購的年度）')}
      ${n('流通股數五年變化', BB.shChg5 == null ? why((BB.why || {}).shChg5 || 'missing') : pc(BB.shChg5), '最新一季期末流通股數 ÷ 五年前同一點 − 1；負數代表股數變少')}
      ${n('近四季回購占市值', BB.buybackYield == null ? why((BB.why || {}).buybackYield || 'missing') : pc(BB.buybackYield, 2), '近四季回購金額 ÷ 最新月底市值')}
      ${n('每留下 1 元盈餘，創造幾元市值', rat, '（現在市值 − 五年前市值）÷（近 20 季淨利 − 近 20 季股利）。股利開始以前的空白季度當 0（見下方算式）')}
      ${OW ? n('股票酬勞占營收（近四季）', OW.sbcRev == null ? why((OW.why || {}).sbcRev || 'missing') : `<b>${pc(OW.sbcRev)}</b>${OW.sbcRev5med == null ? '' : `（近五年中位數 ${pc(OW.sbcRev5med)}）`}`, `近四季股票酬勞費用 ÷ 近四季營收${OW.q && OW.sbcRev != null ? `（${esc(OW.q)}）` : ''}。股票酬勞是真實的費用，等於用股東的股份付薪水（意譯）`) : ''}
    </div>`;
    const bbRows = (BB.rows || []).slice().reverse().map(r => [esc(r.q), cell(r.buyback, v => LT.f0(v), 'missing'), cell(r.avgPe, v => v.toFixed(1), 'short'), r.where ? esc(r.where) : '—', esc(r.from + ' 至 ' + r.to)]);
    const ret = RT.kept == null ? `<p>${why(RT.why || 'missing')}${RT.note ? '　' + esc(RT.note) : ''}</p>` :
      `<p class="how">保留盈餘測試（${esc(RT.m0 || '')} 到 ${esc(RT.mNow || '')}，五年）：近 20 季淨利 ${LT.f0(RT.ni20)} − 近 20 季股利 ${LT.f0(RT.div20)}${RT.noDiv ? '（這家公司沒有配息紀錄，股利當 0）' : ''}${RT.preDivQ ? `（${RT.preDivQ} 季以前尚未配息，股利當 0）` : ''} ＝ 留下 <b>${LT.f0(RT.kept)}</b>；
      市值 ${LT.f0(RT.mcapNow)} − 五年前 ${RT.mcap0 == null ? '（算不出來）' : LT.f0(RT.mcap0)} ＝ 增加 <b>${RT.mcapChg == null ? '—' : LT.f0(RT.mcapChg)}</b>；相除 ＝ ${RT.ratio == null ? why(RT.why || 'missing') : '<b>' + RT.ratio.toFixed(2) + '</b>'}。金額單位同本頁財報（百萬）。市值 ＝ 月底收盤價 × 當時已公布的期末股數。</p>`;
    const tbl = `<details class="bm-det"><summary>回購成績單與保留盈餘算式</summary>${table(['年度點（近四季至）', '近四季回購金額', '那 12 個月平均本益比', '回購買在', '月份區間'], bbRows)}
      <p class="how">月份區間：以該季名目期末日的所在月份為終點往前數 12 個月（期末日在 15 日以後算當月，14 日以前算前一個月）；有本益比的月份少於 6 個就留白；本益比超過 200 倍的月份不納入平均。回購金額為 0 不標。對照的中位數是：${BB.rows && BB.rows[0] && num(BB.rows[0].med5) ? BB.rows[0].med5.toFixed(1) + ' 倍（目前的近 5 年中位數，每一年共用同一個）' : '算不出來'}。</p>${ret}</details>`;
    return card('bmG3', '③ 管理層會用錢嗎', ask('賺來的錢，管理層怎麼用？') +
      view('・資本配置、一元測試', '管理層最重要的工作，是決定賺來的錢怎麼用。回購只有在價格低於價值時，才對股東有利。我們也問：每留下一元盈餘，長期有沒有多出至少一元的市值？') +
      nums + self(['這幾年的回購，是在股價便宜時買，還是不管價格照買？', '留在公司裡的錢，有沒有變成更多的市值？']) + tbl);
  }

  /* ④ 價格有安全邊際嗎 */
  function gate4(B, type) {
    const E = B.ey, I = B.implied, V = B.vsIndex, NP = B.normPe, cyc = type === 'cyclical';
    let main;
    if (E.ey == null) main = why(E.why || 'loss');
    else if (E.bond) main = `盈餘殖利率 <b>${E.ey.toFixed(2)}%</b> 對 ${esc(E.bond.name)} <b>${E.bond.v.toFixed(2)}%</b> ＝ 差 <b class="${E.spread >= 0 ? 'up' : 'down'}">${sg(E.spread, 2)}</b> 個百分點`;
    else main = `盈餘殖利率 <b>${E.ey.toFixed(2)}%</b>；${why(E.bondWhy || 'nobond')}${E.ref ? `。參考：${esc(E.refNote)}，${E.ref.v.toFixed(2)}%（${esc(E.ref.d)}）` : ''}`;
    const meaning = E.spread == null ? '' : (E.spread >= 0 ? '盈餘殖利率不輸公債：承擔股票風險，至少有一點額外補償。' : '盈餘殖利率低於公債：這個差距，要靠公司未來的成長補上。');
    const eyNum = `<div class="bm-nums">${n('盈餘殖利率對公債', main, E.ey == null ? '盈餘殖利率 ＝ 100 ÷ 本益比' : `盈餘殖利率 ＝ 100 ÷ 本益比（${E.pe} 倍，${esc(E.m)} 月底）；公債取最新一點${E.bond ? `（${esc(E.bond.d)}，${esc(E.bond.src || '')}）` : ''}。${meaning}`)}</div>`;
    const OW = B.owner || {}, W = OW.why || {};
    let oeMain;
    if (OW.oeYield == null) oeMain = why(W.oeYield || 'missing');
    else if (OW.bond) oeMain = `<b>${OW.oeYield.toFixed(2)}%</b> 對 ${esc(OW.bond.name)} <b>${OW.bond.v.toFixed(2)}%</b> ＝ 差 <b class="${OW.oeSpread >= 0 ? 'up' : 'down'}">${sg(OW.oeSpread, 2)}</b> 個百分點`;
    else oeMain = `<b>${OW.oeYield.toFixed(2)}%</b>；${why(W.oeSpread || 'nobond')}`;
    const oeNum = `<div class="bm-nums">${n('扣股票酬勞後的自由現金流殖利率', oeMain, '（近四季自由現金流 − 近四季股票酬勞）÷ 最新月底市值。這是業主盈餘的近似：財報沒有拆維持性與成長性資本支出，所以把全部資本支出都扣掉。' + (OW.fcfSbcRate == null ? '' : `近四季扣酬勞後現金流占營收 ${pc(OW.fcfSbcRate)}（未扣酬勞 ${pc(OW.fcfRate)}）。`) + '公債取最新一點')}</div>`;
    const g = I.g || {};
    const imp = !(I.g && num(g['15'])) ? `<div class="bm-nums">${n('價格隱含的成長', why(I.why || 'loss'), '')}</div>` :
      `<div class="bm-nums">${n('價格隱含的成長（每年）', `<b>${pc(g['15'])}</b>（十年後本益比 15 倍）／<b>${pc(g['20'])}</b>（20 倍）`,
        `假設（原樣寫出）：${esc(String(I.assume.text).replace(/^假設：/, ''))}。g ＝ ((本益比 × 1.1<sup>10</sup>) ÷ 終點本益比)<sup>1/10</sup> − 1。對照：公司近五年 EPS 年化成長 ${I.epsCagr5 == null ? '算不出來（兩端要大於 0）' : pc(I.epsCagr5)}`)}</div>`;
    const vr = (V.rows || []);
    const vs = V.why ? `<div class="bm-nums">${n('不買它、買指數呢', why(V.why), '')}</div>` :
      `<h4>不買它、買指數呢（${esc(V.index)}）</h4>${table(['期間', '這支股價', '指數', '差（百分點）'], vr.map(r => [r.years + ' 年', cell(r.stock, v => sg(v) + '%', r.why), cell(r.index, v => sg(v) + '%', r.why), cell(r.diff, v => sg(v), r.why)]))}
      <p class="how">${esc(V.note)}。月底對月底；缺起點就留白。</p>${view('・機會成本', '每個投資都要跟我們最好的替代選擇比。對多數人來說，定期買指數就已經很好。')}`;
    const np = NP.normPe == null ? `${why(NP.why || 'short')}` : `<b>${x1(NP.normPe)}</b>（收盤價 ${NP.close} ÷ 十年平均 EPS ${NP.avgEps}，${NP.n} 個年度點）`;
    const npBlock = `<div class="bm-nums">${n('十年平均獲利本益比', np, '最新月底收盤價 ÷ 年度點近四季 EPS 的平均（至少 5 個年度點，平均要大於 0）')}</div>`;
    return card('bmG4', '④ 價格有安全邊際嗎', ask('現在這個價格，有留給我犯錯的空間嗎？') +
      view('・安全邊際、利率是地心引力', '我們用明顯低於價值的價格買，留下犯錯的空間。利率越高，所有資產的價值就被拉得越低，所以股票要跟公債比。') +
      eyNum + oeNum + imp + (cyc ? `<div class="bm-cyc">${view('・循環看整輪', '循環生意要看整個景氣循環的平均獲利，不看高峰那一年。')}</div>${npBlock}` : '') + vs +
      (cyc ? '' : `<details class="bm-det"><summary>其他常看：十年平均獲利本益比（循環股才是主角）</summary>${npBlock}</details>`) +
      self(['如果我的判斷錯一半，這個價格還能讓我不虧本嗎？', '價格已經假設了什麼？我相信那個假設嗎？']));
  }

  /* 反過來想：它會怎麼死 */
  function invert(D) {
    const T = D.thesis, risks = (T && T.risks) || [];
    const items = risks.map(r => `<li>${esc(r)}<br><span class="bm-q">看到什麼數字，代表它正在發生？</span></li>`).join('');
    return card('bmInv', '反過來想：它會怎麼死', ask('這件事會怎麼失敗？先想清楚，然後避開。') +
      view('・反過來想', '我們常常先問：這門生意會怎麼死？想清楚了，就知道要避開什麼、要盯哪個數字。') +
      (items ? `<h4>論點卡列出的風險</h4><ul class="sum-list bm-risk">${items}</ul>` : '<p class="bm-why">這家公司的論點卡還沒有上線，沒有風險清單可以接。</p>') +
      self(['對手可以用什麼方法，把我們的客戶搶走？', '有沒有新技術，會讓它的產品變得不重要？', '管理層會不會把賺來的錢，花在不該花的地方（亂併購、亂擴張）？']));
  }

  function mount(secEl, N) {
    const D = N.D;
    if (!secEl || !D || document.getElementById('buffett')) return;
    const B = D.buffett, type = (D.thesis && D.thesis.type) || (B && B.type) || null;
    const opt = type === 'option' ? `<p class="note bm-opt">這家公司還沒有穩定獲利，這裡的檢查多半算不出來。這類投資是買一個可能性，金額要小到全部虧掉也不影響生活。（意譯）</p>` : '';
    const sec = document.createElement('section'); sec.id = 'buffett';
    sec.innerHTML = `<div class="sec-head"><span class="sec-tag">價值投資</span><h2>巴菲特＋蒙格檢查表 ${tag('v')}</h2>
      <p class="sub">觀念（意譯，不是原話）；數字由程式用本站資料算，不手填。四關加一個反向問題。${type ? `目前類型：${esc(TYPE[type] || type)}。` : ''}</p></div>
      ${opt}<div class="bm-grid">${gate1(D)}${B ? gate2(B) : ''}${B ? gate3(B) : ''}${B ? gate4(B, type) : ''}${invert(D)}</div>
      ${B ? '' : '<p class="bm-why">第 ②③④ 關算不出來：這家公司沒有可用的財務資料。</p>'}
      <p class="how">每個數字下面的小字是算法；算不出來的地方寫明原因，不是空白。盈餘殖利率對公債、價格隱含的成長是分析工具，不是買賣訊號。</p>`;
    const th = document.getElementById('thesis');
    if (th) th.after(sec); else secEl.parentNode.insertBefore(sec, secEl);
    const nav = document.getElementById('secnav') || document.querySelector('.secnav .scroller');
    if (nav && !nav.querySelector('[href="#buffett"]')) {
      const a = document.createElement('a'); a.href = '#buffett'; a.textContent = '檢查表';
      const t = nav.querySelector('a[href="#thesis"]'), lt = nav.querySelector('a[href="#longterm"]');
      t ? t.after(a) : lt ? nav.insertBefore(a, lt) : nav.appendChild(a);
    }
  }
  /* 指標小辭典的新名詞（三個版型共用：generic、tsmc、pltr 的小辭典 concat 這份）。觀念是意譯，不是原話。 */
  const GLOSS = [
    ['盈餘殖利率', 'Earnings yield', '本益比倒過來看：用現在的股價買進，每 100 元一年分到多少盈餘。拿來跟十年期公債殖利率比。', '100 ÷ 本益比（%）'],
    ['業主盈餘', 'Owner earnings', '觀念（巴菲特＋蒙格，意譯）：真正屬於股東的錢，是賺到的現金扣掉維持生意必須花的錢；股票酬勞也是真實費用。財報沒有拆維持性資本支出，本站目前用自由現金流當近似，還沒扣股票酬勞。', '營業現金流 − 維持生意必須的資本支出'],
    ['保留盈餘測試', 'Retained earnings test', '觀念（意譯）：公司每留下 1 元盈餘（沒發成股利的部分），長期應該至少創造 1 元市值。', '（現在市值 − 五年前市值）÷（近 20 季淨利 − 近 20 季股利）'],
    ['安全邊際', 'Margin of safety', '觀念（意譯）：用明顯低於價值的價格買，留下犯錯的空間。本站不算「價值」，用盈餘殖利率對公債、價格隱含的成長幫忙判斷。', '沒有單一公式'],
    ['能力圈', 'Circle of competence', '觀念（意譯）：只投資自己看得懂的生意；看不懂就放進「太難」那一堆，不丟臉。', '沒有公式：檢查表第 ① 關的提問'],
    ['十年平均獲利本益比', 'Normalized P/E', '循環股看整個景氣循環的平均獲利，不看高峰那一年。用它比單看本益比更不容易在景氣高峰買貴。', '最新月底收盤價 ÷ 年度點近四季 EPS 的平均（至少 5 點）'],
    ['價格隱含的成長', 'Implied growth', '倒過來算：照現在的本益比，公司每年要成長多少，十年後買進的人才有 10% 年報酬。假設十年後本益比 15 倍、不計股利與回購。', '((本益比 × 1.1^10) ÷ 15)^(1/10) − 1'],
  ];
  return { mount, WHY, GLOSS };
})();
