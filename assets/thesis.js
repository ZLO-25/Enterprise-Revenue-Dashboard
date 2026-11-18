/* 論點卡：每家公司一張，「觀點」標籤。論點文字與門檻是人的判斷（只有 status:"approved" 才會被 build.py 放進頁面），
   燈號與「最新一季」數字由 tools/thesis.py 在建置時算好（D.thesis.lights），這裡只畫。排程只更新燈號，不改論點文字或門檻。 */
const THESIS = (() => {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const LIGHT = { g: ['綠', '達標'], y: ['黃', '最新一點沒達標，前一點有'], r: ['紅', '連續兩點沒達標'], n: ['灰', '目前算不出來'] };
  const fmt = (v) => v == null ? '—' : Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
  function mount(secEl, N) {
    const T = N.D && N.D.thesis;
    if (!T || !secEl || document.getElementById('thesis')) return;
    const row = (m) => { const L = (T.lights || {})[m.k] || { light: 'n' }; const l = LIGHT[L.light];
      return `<tr><th scope="row">${esc(m.name)}${m.note ? `<small>${esc(m.note)}</small>` : ''}</th><td>${m.op === '>=' ? '高於' : '不高於'} ${esc(m.thr)}<small>${m.by === 'ZL' ? '你定的門檻' : m.by === 'analyst' ? '分析師建議，ZL 可改' : '草擬門檻'}</small></td><td>${fmt(L.now)}<small>${esc(L.label || '')}</small></td><td><span class="light light-${L.light}" title="${l[1]}">${l[0]}</span></td></tr>`; };
    const tbl = (title, list) => list.length ? `<h3>${title}</h3><div class="tbl-wrap"><table class="sum-tbl"><thead><tr><th>關鍵指標</th><th>門檻</th><th>最新</th><th>燈號</th></tr></thead><tbody>${list.map(row).join('')}</tbody></table></div>` : '';
    const ms = T.metrics || [], aux = ms.filter(m => m.role === 'aux'), biz = ms.filter(m => m.group !== 'val' && m.role !== 'aux'), valm = ms.filter(m => m.group === 'val' && m.role !== 'aux');
    const TYPE = { compounder: '穩健複利', growth: '高成長', cyclical: '循環股', turnaround: '轉機／早期', option: '選擇權' };
    const rows = tbl('體質（論點破功只看這一區）', biz) + tbl('輔助觀察（成長要配上報酬率才有價值）', aux) + tbl('估值（只提醒貴不貴，不單獨構成破功）', valm);
    const BF = N.D.buffett && N.D.buffett.structure, yn = (v) => v == null ? '算不出來' : (v ? '是' : '否');
    const struct = BF ? `<h3>結構檢查（程式算的事實，不下結論）</h3><ul class="sum-list"><li>ROE 連續三年下滑：<b>${yn(BF.roeDown3)}</b></li><li>毛利率三年累計下滑超過 5 個百分點：<b>${yn(BF.gmDown3)}</b>${BF.gmChg3 == null ? '' : `（三年變化 ${BF.gmChg3 > 0 ? '+' : ''}${BF.gmChg3.toFixed(1)} 個百分點）`}</li><li>最新近四季 EPS ≤ 0：<b>${yn(BF.lossNow)}</b></li></ul>` : '';
    const brk = T.warnWhen ? `<h3>季度警示（黃燈，先觀察，不是賣出理由）</h3><p>${esc(T.warnWhen)}</p>
      <p class="note">${SUM.tag('v')} 巴菲特＋蒙格口吻（意譯，不是原話）：好公司買到以後，大部分時間什麼都不做。單季不如預期、股價下跌，都不是賣出的理由。</p>
      ${T.breakWhen ? `<h3>論點破了（結構性，才需要重新考慮持有）</h3><p>${esc(T.breakWhen)}</p>` : ''}${struct}` : (T.breakWhen ? `<h3>論點破了的條件</h3><p>${esc(T.breakWhen)}</p>` : '');
    const hist = (T.history || []).slice(-8).reverse();
    const sec = document.createElement('section'); sec.id = 'thesis';
    sec.innerHTML = `<div class="sec-head"><span class="sec-tag">投資論點</span><h2>論點卡 ${SUM.tag('v')}</h2>
      <p class="sub">最後修改 ${esc(T.updated)}（${esc(T.updatedBy)}）。論點文字與門檻是判斷，不是事實；燈號由程式用網站已有的數字算，只有「最新一季」那欄是事實。</p></div>
      <div class="card"><p class="sum-head">${T.type ? `<span class="chip">${esc(TYPE[T.type] || T.type)}</span> ` : ''}${esc(T.oneLiner)}</p>
      ${T.caveat ? `<p class="note">${esc(T.caveat)}</p>` : ''}
      ${rows}
      ${brk}
      ${(T.risks || []).length ? `<h3>風險</h3><ul class="sum-list">${T.risks.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
      ${hist.length ? `<details><summary>燈號歷史（每季快報時記一次）</summary><ul class="sum-list">${hist.map(h => `<li><b>${esc(h.q)}</b>　${Object.entries(h.lights).map(([k, v]) => `${esc(((T.metrics || []).find(m => m.k === k) || {}).name || k)}：<span class="light light-${v}">${LIGHT[v][0]}</span>`).join('　')}</li>`).join('')}</ul></details>` : ''}</div>`;
    secEl.parentNode.insertBefore(sec, secEl);
    const nav = document.getElementById('secnav');
    if (nav && !nav.querySelector('[href="#thesis"]')) { const a = document.createElement('a'); a.href = '#thesis'; a.textContent = '論點'; const lt = nav.querySelector('a[href="#longterm"]'); lt ? nav.insertBefore(a, lt) : nav.appendChild(a); }
  }
  return { mount };
})();
