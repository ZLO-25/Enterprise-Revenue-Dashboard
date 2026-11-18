/* 首頁「今天該看什麼」與財報行事曆頁共用的純函式（不碰 DOM，Node 也能測：node --test tools/tests/today.test.js）。
   日期一律用台北日期（YYYY-MM-DD 字串比較）。事件資料來自各公司 events[]；系統紅燈、燈號變化、估值訊號是三個小檔，讀不到就略過那一類。 */
const EVCAL = (() => {
  const addDays = (d, n) => { const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
  const tpeDate = (now) => new Date((now || new Date()).getTime() + 8 * 3600e3).toISOString().slice(0, 10);
  const dow = (d) => new Date(d + 'T00:00:00Z').getUTCDay();          // 0=週日
  const monday = (d) => addDays(d, -((dow(d) + 6) % 7));
  const WD = ['日', '一', '二', '三', '四', '五', '六'];
  const md = (d) => d.slice(5).replace('-', '/');
  const mdw = (d) => md(d) + ' 週' + WD[dow(d)];
  const days = (a, b) => Math.round((new Date(b + 'T00:00:00Z') - new Date(a + 'T00:00:00Z')) / 86400e3);

  /* events: [{d, code, name, t, est}]；回傳排序後（日期、已公告在前） */
  const sortEv = (evs) => evs.slice().sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : (!!a.est - !!b.est) || (a.code < b.code ? -1 : 1));

  /* 首頁：最多 limit 則，優先順序固定。回傳 {items:[{kind,text,href}], more} */
  function pick(o) {
    const today = o.today, limit = o.limit || 3, items = [];
    if (o.alerts && o.alerts.length) items.push({ kind: 'alert', text: '系統有 ' + o.alerts.length + ' 個紅燈：' + o.alerts.slice(0, 2).join('；') + (o.alerts.length > 2 ? '…' : ''), href: o.statusHref });
    const ev = sortEv(o.events || []);
    const fmt = (e) => (e.d === today ? '今天' : mdw(e.d)) + ' ' + e.name + ' ' + e.t + (e.est ? '（預估）' : '（已公告）');
    ev.filter(e => e.d === today).forEach(e => items.push({ kind: 'event', text: fmt(e), href: e.href }));
    const week = ev.filter(e => e.d > today && e.d <= addDays(today, 7));
    week.filter(e => !e.est).concat(week.filter(e => e.est)).forEach(e => items.push({ kind: 'event', text: fmt(e), href: e.href }));
    const cut = addDays(today, -7);
    (o.lights || []).filter(c => c.d >= cut && c.g !== 'val' && (c.to === 'y' || c.to === 'r')).forEach(c =>
      items.push({ kind: 'light', text: '體質燈號轉' + (c.to === 'r' ? '紅' : '黃') + '：' + (c.cname || c.code.toUpperCase()) + ' ' + (c.name || c.k) + '（' + md(c.d) + '）', href: c.href }));
    (o.signals || []).filter(s => s.d >= cut).forEach(s =>
      items.push({ kind: 'signal', text: '估值' + (s.kind === 'exceed' ? '超出' : '回到') + '門檻：' + (s.cname || s.code.toUpperCase()) + ' ' + s.name + ' ' + s.now + '（' + md(s.d) + '）· 提醒，不是買賣建議', href: s.href }));
    return { items: items.slice(0, limit), more: Math.max(0, items.length - limit) };
  }

  /* 行事曆：依週一起算分組。回傳 [{start, end, label, items}]；沒有事件的連續週合併成一筆 empty:true */
  function weeks(evs, today, span) {
    const last = addDays(today, span || 90), out = [];
    const inRange = sortEv(evs).filter(e => e.d >= today && e.d <= last);
    let w = monday(today), emptyFrom = null;
    const flush = (to) => { if (emptyFrom) { out.push({ start: emptyFrom, end: to, empty: true, items: [] }); emptyFrom = null; } };
    for (; w <= last; w = addDays(w, 7)) {
      const end = addDays(w, 6), items = inRange.filter(e => e.d >= w && e.d <= end);
      if (!items.length) { if (!emptyFrom) emptyFrom = w; continue; }
      flush(addDays(w, -1));
      out.push({ start: w, end, items });
    }
    flush(addDays(w, -1));
    return out;
  }

  /* .ics：只含「已公告」事件，全天事件 */
  function ics(evs) {
    const esc = (s) => String(s).replace(/([,;\\])/g, '\\$1');
    const L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Enterprise Revenue Dashboard//TW', 'CALSCALE:GREGORIAN'];
    evs.filter(e => !e.est).forEach(e => {
      const d = e.d.replace(/-/g, '');
      L.push('BEGIN:VEVENT', 'UID:' + e.code + '-' + d + '@erd', 'DTSTAMP:' + d + 'T000000Z', 'DTSTART;VALUE=DATE:' + d, 'DTEND;VALUE=DATE:' + addDays(e.d, 1).replace(/-/g, ''), 'SUMMARY:' + esc(e.name + ' ' + e.t), 'END:VEVENT');
    });
    L.push('END:VCALENDAR');
    return L.join('\r\n');
  }
  return { addDays, tpeDate, dow, monday, md, mdw, days, sortEv, pick, weeks, ics };
})();
if (typeof module !== 'undefined') module.exports = EVCAL;
