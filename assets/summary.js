/* 每季一頁摘要（最新一季重點）＋財測紀錄。資料在 data/<代號>.json 的 summary 與 guidanceHistory（格式見 docs/DATA_SCHEMA.md）。
   由 LT.render() 呼叫 SUM.mount()，所有公司頁（通用、台積電、PLTR）共用，沒有 summary 的公司什麼都不顯示。
   四種來源標籤（每一句都要標）：w 書面（申報文件／新聞稿）、o 口頭（電話會議，附逐字稿連結與發言人）、e 分析師預估（附快照日）、v 觀點（Claude 的判斷，不是事實）。 */
const SUM = (() => {
  const TAGS = { w: ['書面', '申報文件或公司公告'], o: ['口頭', '電話會議上講的，附逐字稿連結'], e: ['分析師預估', '市場共識，附快照日'], v: ['觀點', 'Claude 的判斷，不是事實'] };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const tag = (t, extra) => `<span class="src-tag src-${t}" title="${TAGS[t][1]}">${TAGS[t][0]}${extra ? ' · ' + esc(extra) : ''}</span>`;
  const link = (s) => s && s.url ? ` <a class="src-link" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.n || '來源')}${s.speaker ? '（' + esc(s.speaker) + '）' : ''}</a>` : '';
  const md = (d) => d ? d.slice(5).replace('-', '/') : '';
  const DIR = { up: ['上修', 'up'], flat: ['持平', ''], down: ['下修', 'down'], na: ['無新財測', ''] };
  const KEYS = { rev: ['營收', 'rev', 'f0', '下一季營收'], gm: ['毛利率', 'gm', 'pc', '下一季毛利率'], om: ['營業利益率', 'om', 'pc', '下一季營業利益率'], eps: ['EPS（GAAP 稀釋）', 'eps', 'f2', '下一季 EPS'] };

  function guideFor(D, q, label) {
    const all = [...(D.guidanceHistory || [])];
    for (const g of all.reverse()) {
      const it = (g.items || []).find(i => i.period === q && (label ? i.label === label || i.label.includes(label) : true));
      if (it) return Object.assign({ issued: g.issued }, it);
    }
    return null;
  }
  function verdict(v, lo, hi) {
    if (v == null || lo == null && hi == null) return '';
    const L = lo == null ? hi : lo, H = hi == null ? lo : hi;
    if (v > H) return '<span class="up">高於財測區間</span>'; if (v < L) return '<span class="down">低於財測區間</span>';
    return '區間內';
  }
  function fmt(kind, v) { return v == null ? '—' : (kind === 'f0' ? LT.f0(v) : kind === 'pc' ? LT.pc(v) : LT.f2(v)); }

  function scorecard(S, N) {
    const D = N.D, Q = N.Q.find(x => x.q === S.q);
    if (!Q || !S.scorecard || !S.scorecard.length) return '';
    const rows = S.scorecard.map(r => {
      const K = KEYS[r.k] || [r.label || r.k, r.k, 'f2', r.guideLabel];
      const act = Q[K[1]], g = guideFor(D, S.q, r.guideLabel || K[3]);
      const gTxt = g ? `${fmt(K[2], g.lo)}${g.hi !== g.lo ? ' ~ ' + fmt(K[2], g.hi) : ''}<small>${md(g.issued)} 發布</small>` : '<span class="muted">—</span>';
      const c = r.cons;
      const cTxt = c ? `${fmt(K[2], c.v)}${c.basis ? ` <small>${esc(c.basis)}</small>` : ''}<small>快照 ${md(c.snap)}${c.n != null ? ' · ' + c.n + ' 位' : ''}${c.n != null && c.n < 3 ? '（預估人數少）' : ''}</small>` : '<span class="muted">—</span>';
      const alt = c && c.actualAlt != null ? `<small>公司非 GAAP：${fmt(K[2], c.actualAlt)}</small>` : '';
      let cv = '';
      const cmp = c && c.v != null ? (c.actualAlt != null ? c.actualAlt : act) : null;
      if (cmp != null) cv = cmp > c.v * 1.0005 ? '<span class="up">高於預期</span>' : cmp < c.v * 0.9995 ? '<span class="down">低於預期</span>' : '符合預期';
      return `<tr><th scope="row">${esc(r.label || K[0])}</th><td>${fmt(K[2], act)}${alt}</td><td>${gTxt}<div>${g ? verdict(act, g.lo, g.hi) : ''}</div></td><td>${cTxt}<div>${cv}</div></td></tr>`;
    }).join('');
    return `<h3>成績單：實際 對 公司上季財測 對 市場預期</h3>
      <div class="tbl-wrap"><table class="sum-tbl"><thead><tr><th></th><th>實際 ${tag('w')}</th><th>公司上季財測 ${tag('w')}</th><th>市場預期 ${tag('e')}</th></tr></thead><tbody>${rows}</tbody></table></div>
      ${S.scorecardNote ? `<p class="how">${esc(S.scorecardNote)}</p>` : ''}`;
  }
  const list = (items) => items && items.length ? `<ul class="sum-list">${items.map(i => `<li>${tag(i.tag || 'w')} ${esc(i.t)}${link(i.src)}</li>`).join('')}</ul>` : '';
  const qa = (items) => items && items.length ? `<ul class="sum-list">${items.map(i => `<li>${tag(i.tag || 'o')} <b>${esc(i.q)}</b><br>${esc(i.a)}${link(i.src)}</li>`).join('')}</ul>` : '';

  function mount(secEl, N) {
    const D = N.D, S = D && D.summary;
    if (!S || !secEl || document.getElementById('summary')) return;
    const st = S.status === 'final' ? `定稿 ${md(S.finalDate)}` : `初版 ${md(S.flashDate)}`;
    const dir = S.outlook && DIR[S.outlook.dir];
    const hist = (D.summaryHistory || []).slice().reverse();
    const gh = (D.guidanceHistory || []).slice().reverse();
    const sec = document.createElement('section');
    sec.id = 'summary';
    sec.innerHTML = `<div class="sec-head"><span class="sec-tag">每季一頁摘要</span><h2>${esc(S.q)} 財報重點 <span class="chip ${S.status === 'final' ? '' : 'chip-warn'}">${st}</span></h2>
      <p class="sub">每一句話標明來源類別。${tag('w')} 申報文件或公司公告　${tag('o')} 電話會議（附逐字稿）　${tag('e')} 市場共識（附快照日）　${tag('v')} 判斷，不是事實。</p></div>
      <div class="card sum-card">
        ${S.headline ? `<p class="sum-head">${tag(S.headline.tag || 'w')} ${esc(S.headline.t)}</p>` : ''}
        ${scorecard(S, N)}
        ${S.outlook ? `<h3>展望變化${dir ? ` <span class="chip ${dir[1] === 'up' ? 'chip-up' : dir[1] === 'down' ? 'chip-down' : ''}">${dir[0]}</span>` : ''}</h3>${list(S.outlook.items)}` : ''}
        ${S.mgmt && S.mgmt.length ? `<h3>管理層說法（電話會議）</h3>${list(S.mgmt)}` : ''}
        ${S.qa && S.qa.length ? `<h3>問答重點</h3>${qa(S.qa)}` : ''}
        ${(S.risks && S.risks.length) || S.next ? `<h3>風險與下一季要看什麼</h3>${list(S.risks)}${S.next ? `<p>${tag('v')} ${esc(S.next)}</p>` : ''}` : ''}
        ${S.pending && S.pending.length ? `<p class="how"><b>尚待補完：</b>${S.pending.map(esc).join('；')}</p>` : ''}
        ${hist.length ? `<details><summary>歷季重點（${hist.length} 季，只從本站開始追蹤的季度累積，不回補舊季度）</summary><ul class="sum-list">${hist.map(h => `<li><b>${esc(h.q)}</b>（${esc(h.status === 'final' ? '定稿 ' + md(h.finalDate) : '初版 ' + md(h.flashDate))}）${tag(h.headline && h.headline.tag || 'w')} ${esc(h.headline && h.headline.t)}</li>`).join('')}</ul></details>` : ''}
        ${gh.length ? `<details><summary>財測紀錄（公司每次發布的財測，舊的保留不覆蓋）</summary>${gh.map(g => `<p class="how"><b>${esc(g.issued)}</b>　${(g.items || []).map(i => `${esc(i.label)}（${esc(i.period)}）${LT.f2(i.lo)}${i.hi !== i.lo ? '~' + LT.f2(i.hi) : ''}${esc(i.unit || '')}`).join('；')}</p>`).join('')}</details>` : ''}
      </div>`;
    secEl.parentNode.insertBefore(sec, secEl);
    const nav = document.getElementById('secnav');
    if (nav && !nav.querySelector('[href="#summary"]')) { const a = document.createElement('a'); a.href = '#summary'; a.textContent = '本季重點'; const first = nav.querySelector('a[href="#longterm"]'); first ? nav.insertBefore(a, first) : nav.appendChild(a); }
  }
  return { mount, tag };
})();
