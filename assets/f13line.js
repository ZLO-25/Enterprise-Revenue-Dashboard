/* 個股頁的「13F 參考」一行（三個版型共用：generic、tsmc、pltr 的 LONGTERM 合併檔）。
   執行時讀 ../data/13f/by-company.json（只由 Actions 的 f13-quarterly 寫入）；讀不到就不顯示（還沒抓過不報錯）。
   不在 tracked 的台股、韓股：顯示「13F 不涵蓋」。13F 是書面（SEC 申報），落後最多 45 天，只是參考。 */
const F13LINE = (() => {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const qlab = (p) => p ? p.slice(0, 4) + 'Q' + Math.ceil(+p.slice(5, 7) / 3) : '';
  function text(code, B) {
    const nc = (B.notCovered || {})[code];
    if (nc) return '13F 參考：不涵蓋（' + esc(nc) + '）';
    const e = (B.companies || {})[code];
    if (!e) return '';
    if (!e.cusipsKnown) return '13F 參考：<span class="pend">待確認</span> 這家公司的 CUSIP 對照尚未確認，暫不判斷。';
    const top = B.period, ms = (e.managers || []).filter((x) => x.period === top);
    const nTotal = Object.keys(B.latestByManager || {}).length, nFiled = Object.values(B.latestByManager || {}).filter((p) => p === top).length;
    const c = { add: 0, reduce: 0, new: 0, exit: 0 };
    const held = ms.filter((x) => x.chg !== 'exit');
    ms.forEach((x) => { if (c[x.chg] != null) c[x.chg]++; });
    const unk = held.filter((x) => x.chg == null).length;
    return '13F 參考（' + qlab(top) + '）：' + held.length + ' 位大師持有；本季 加碼 ' + c.add + '、減碼 ' + c.reduce + '、新增 ' + c.new + '、出清 ' + c.exit +
      (unk ? '（' + unk + ' 位上一季無法比較）' : '') + (nFiled < nTotal ? '；另有 ' + (nTotal - nFiled) + ' 位尚未申報本季' : '') +
      ' → <a href="../13f/">看大師持股</a>';
  }
  function mount(secEl, N) {
    if (!secEl || !window.fetch || document.getElementById('f13ref')) return;
    const code = N && N.c && N.c.code;
    if (!code) return;
    fetch('../data/13f/by-company.json', { cache: 'no-cache' }).then((r) => r.ok ? r.json() : null).then((B) => {
      if (!B || document.getElementById('f13ref')) return;
      const t = text(code, B);
      if (!t) return;
      const p = document.createElement('p');
      p.id = 'f13ref'; p.className = 'note';
      p.style.cssText = 'font-size:.85rem;color:var(--muted);margin:14px 0 0';
      p.innerHTML = t + ' <span class="tag-src" style="font-size:.72rem;border:1px solid var(--line);border-radius:999px;padding:0 6px">書面（SEC 13F）・參考，落後最多 45 天</span>';
      const after = document.getElementById('buffett') || document.getElementById('thesis') || null;
      if (after) after.after(p); else secEl.appendChild(p);
    }).catch(() => {});
  }
  return { mount, text };
})();
