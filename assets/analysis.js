/* 公司分析（長期投資人觀點）：放在個股頁「XXX 財報追蹤板」標題正下方。
   資料在 data/analysis/<代號>.json（格式見 docs/DATA_SCHEMA.md「公司分析」），由 build.py 放進 D.analysis。
   平常只顯示「結論＋重點」；按「more」才展開全文（Markdown，這裡用一個很小的轉換器畫成 HTML）。
   整段都是觀點（Claude 依 .claude/skills/long-term-company-analysis 產生），不是事實；每個重點仍標來源類別。
   由 LT.render() 呼叫 ANALYSIS.mount()；沒有分析檔的公司什麼都不顯示。 */
const ANALYSIS = (() => {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const TAGS = { w: ['書面', '申報文件或公司公告'], o: ['口頭', '電話會議上講的'], e: ['分析師預估', '市場共識'], v: ['觀點', 'Claude 的判斷，不是事實'], m: ['媒體', '只有媒體報導，公司未證實（待確定）'] };
  const tag = (t) => { const x = TAGS[t] || TAGS.v; return `<span class="src-tag src-${TAGS[t] ? t : 'v'}" title="${x[1]}">${x[0]}</span>`; };
  const VERD = { '加碼': 'chip-up', '不動': '', '續抱': '', '減碼': 'chip-down', '觀察': 'chip-warn', '太難，跳過': 'chip-warn' };
  const qk = (q) => q && /^[1-4]Q\d{2}$/.test(q) ? +q.slice(2) * 10 + +q[0] : 0;

  // 行內：**粗體**、`程式碼`、[文字](網址)
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // 很小的 Markdown 轉換器：標題、段落、清單、``` 程式碼（ASCII 圖）、表格、引言。分析全文只用到這些。
  function md(text) {
    const L = String(text || '').replace(/\r/g, '').split('\n'), out = [];
    let i = 0;
    while (i < L.length) {
      const l = L[i];
      if (/^```/.test(l)) { const buf = []; i++; while (i < L.length && !/^```/.test(L[i])) buf.push(L[i++]); i++; out.push(`<pre class="an-pre">${esc(buf.join('\n'))}</pre>`); continue; }
      const h = l.match(/^(#{1,4})\s+(.*)$/);
      if (h) { const n = Math.min(4, h[1].length + 2); out.push(`<h${n}>${inline(h[2])}</h${n}>`); i++; continue; }
      if (/^\s*\|/.test(l)) {
        const rows = []; while (i < L.length && /^\s*\|/.test(L[i])) rows.push(L[i++]);
        const cells = (r) => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
        const body = rows.filter(r => !/^\s*\|?\s*:?-{2,}/.test(r));
        const head = body.shift();
        out.push(`<div class="tbl-wrap"><table class="sum-tbl"><thead><tr>${cells(head).map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${body.map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
        continue;
      }
      if (/^\s*([-*]|\d+[.)])\s+/.test(l)) {
        const ordered = /^\s*\d+[.)]/.test(l), items = [];
        while (i < L.length && /^\s*([-*]|\d+[.)])\s+/.test(L[i])) {
          let t = L[i++].replace(/^\s*([-*]|\d+[.)])\s+/, '');
          while (i < L.length && /^\s{2,}\S/.test(L[i]) && !/^\s*([-*]|\d+[.)])\s+/.test(L[i])) t += ' ' + L[i++].trim();
          items.push(`<li>${inline(t)}</li>`);
        }
        out.push(ordered ? `<ol class="sum-list">${items.join('')}</ol>` : `<ul class="sum-list">${items.join('')}</ul>`);
        continue;
      }
      if (/^>\s?/.test(l)) { const buf = []; while (i < L.length && /^>\s?/.test(L[i])) buf.push(L[i++].replace(/^>\s?/, '')); out.push(`<p class="note">${inline(buf.join(' '))}</p>`); continue; }
      if (!l.trim()) { i++; continue; }
      const buf = []; while (i < L.length && L[i].trim() && !/^(#{1,4}\s|```|\s*\||\s*([-*]|\d+[.)])\s+|>)/.test(L[i])) buf.push(L[i++]);
      out.push(`<p>${inline(buf.join(' '))}</p>`);
    }
    return out.join('\n');
  }

  function mount(_, N) {
    const A = N.D && N.D.analysis;
    if (!A || document.getElementById('analysis')) return;
    const head = document.querySelector('header.masthead');
    if (!head) return;
    const latest = (N.Q || []).map(x => x.q).filter(Boolean).sort((a, b) => qk(a) - qk(b)).pop();
    const stale = latest && A.q && qk(latest) > qk(A.q);
    const hist = (A.history || []).slice(-6).reverse();
    const sec = document.createElement('section'); sec.id = 'analysis';
    sec.innerHTML = `<div class="sec-head"><span class="sec-tag">長期投資人分析</span><h2>${esc(A.q)} 分析結論 ${tag('v')}
        <span class="chip ${VERD[A.verdict] || ''}">${esc(A.verdict)}</span>${stale ? ` <span class="chip chip-warn">最新一季 ${esc(latest)} 尚未分析</span>` : ''}</h2>
      <p class="sub">${esc(A.date)} ${esc(A.mode || '快評')}。整段是判斷，不是事實；數字來自本頁的財報資料，新聞標「媒體」。結論五選一：不動（預設）／加碼／減碼／觀察／太難，跳過。</p>
      <p class="note">${tag('v')} 巴菲特＋蒙格口吻（意譯，不是原話）：好公司買到以後，大部分時間什麼都不做。沒有明確理由，就是「不動」。${A.reason ? `<br>理由類別：${esc(({ filters: '第 ① 關（能力圈）過不了', A: '護城河壞了', B: '管理層變了', C: '貴到離譜而且有明顯更好的去處' })[A.reason] || A.reason)}` : ''}</p></div>
      <div class="card an-card">
        <p class="sum-head">${esc(A.conclusion)}</p>
        <h3>重點</h3>
        <ul class="sum-list">${(A.points || []).map(p => `<li>${tag(p.tag || 'v')} ${inline(p.t)}</li>`).join('')}</ul>
        ${(A.verify || []).length ? `<h3>下一季要驗證</h3><ul class="sum-list">${A.verify.map(v => `<li>${inline(v)}</li>`).join('')}</ul>` : ''}
        <div class="an-full" id="anFull" hidden>${md(A.full)}
          ${(A.pending || []).length ? `<h3>待確認</h3><ul class="sum-list">${A.pending.map(v => `<li>${inline(v)}</li>`).join('')}</ul>` : ''}
          ${hist.length ? `<h3>歷次結論</h3><ul class="sum-list">${hist.map(h => `<li><b>${esc(h.q)}</b>（${esc(h.date)}）<span class="chip ${VERD[h.verdict] || ''}">${esc(h.verdict)}</span> ${esc(h.conclusion)}</li>`).join('')}</ul>` : ''}
        </div>
        <button type="button" class="an-more" aria-expanded="false" aria-controls="anFull">more ▾　看完整分析</button>
      </div>`;
    head.parentNode.insertBefore(sec, head.nextSibling);
    const btn = sec.querySelector('.an-more'), full = sec.querySelector('#anFull');
    btn.addEventListener('click', () => {
      const open = full.hidden; full.hidden = !open;
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? 'less ▴　收起完整分析' : 'more ▾　看完整分析';
      if (!open) sec.scrollIntoView({ block: 'start' });
    });
    // 從首頁「看完整分析 →」過來（#analysis-full）：直接展開全文並捲到這裡；#analysis 只捲動。區塊是腳本後插的，瀏覽器原本的錨點捲動找不到它
    const h = location.hash;
    if (h === '#analysis-full' || h === '#analysis') {
      if (h === '#analysis-full') btn.click();
      requestAnimationFrame(() => sec.scrollIntoView({ block: 'start' }));
    }
    const nav = document.getElementById('secnav') || document.querySelector('.secnav .scroller');
    if (nav && !nav.querySelector('[href="#analysis"]')) {
      const a = document.createElement('a'); a.href = '#analysis'; a.textContent = '分析';
      const first = [...nav.querySelectorAll('a')].find(x => !x.classList.contains('homelink') && x.getAttribute('href') !== '#overview');
      first ? nav.insertBefore(a, first) : nav.appendChild(a);
    }
  }
  return { mount, md };
})();
