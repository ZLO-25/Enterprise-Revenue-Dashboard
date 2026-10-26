/* 共用前端函式（新公司的模板用；以 COMMON_JS 占位符內嵌進頁面）。
   依賴頁面已載入 Chart.js，且 assets/theme.css 的 CSS 變數存在。 */
const $ = (s) => document.querySelector(s);
const T = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const f0 = (n) => n == null ? '—' : nf0.format(n);
const f1 = (n) => n == null ? '—' : nf1.format(n);
const f2 = (n) => n == null ? '—' : nf2.format(n);
const sp = (n, d = 1) => n == null ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(d) + '%';
const pc = (n, d = 1) => n == null ? '—' : n.toFixed(d) + '%';
const cls = (n) => n == null ? '' : (n >= 0 ? 'up' : 'down');
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const r1 = (n) => n == null ? null : Math.round(n * 10) / 10;
const tint = (hex, a) => { const n = parseInt(hex.replace('#', ''), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };

function legend(el, items) {
  $(el).innerHTML = items.map(i => `<span><i class="${i.line ? 'ln' : ''}" style="background:${i.c}"></i>${i.t}</span>`).join('');
}
function baseOpts(extra = {}) {
  return Object.assign({
    responsive: true, maintainAspectRatio: false,
    animation: reduce ? false : { duration: 350 },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: T('--surface'), titleColor: T('--ink'), bodyColor: T('--ink-2'),
        borderColor: T('--axis'), borderWidth: 1, padding: 10, boxPadding: 4, cornerRadius: 8,
        titleFont: { family: 'IBM Plex Sans, Noto Sans TC, sans-serif', weight: '600' },
        bodyFont: { family: 'IBM Plex Mono, Noto Sans TC, monospace', size: 12 },
        usePointStyle: true,
      },
    },
    scales: {},
  }, extra);
}
const tip = (o) => ({ ...baseOpts().plugins, tooltip: { ...baseOpts().plugins.tooltip, ...o } });
function yAxis(o = {}, t = {}) {
  return Object.assign({ border: { display: false }, grid: { color: T('--grid'), drawTicks: false },
    ticks: Object.assign({ color: T('--tick'), padding: 8, font: { family: 'IBM Plex Mono, monospace', size: 11 } }, t) }, o);
}
function xAxis(o = {}, t = {}) {
  return Object.assign({ border: { color: T('--axis') }, grid: { display: false },
    ticks: Object.assign({ color: T('--tick'), maxRotation: 0, autoSkip: true, font: { family: 'IBM Plex Mono, monospace', size: 11 } }, t) }, o);
}
const bar = (o) => Object.assign({ type: 'bar', borderRadius: 3, borderSkipped: 'start', categoryPercentage: 0.8, barPercentage: 0.9 }, o);
const line = (o) => Object.assign({ type: 'line', borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.2, spanGaps: false }, o);
/* ---------- 比較圖共用：線尾標籤、對數刻度、季度刻度、缺口虛線 ---------- */
/* 線尾標籤：在每條線最後一個有值的點右邊寫「公司名 數值」，互相重疊時往上下推開 */
const endLabels = {
  id: 'endLabels',
  afterDatasetsDraw(chart, _a, opts) {
    const { ctx, chartArea: { right, top, bottom } } = chart;
    const fmt = opts.fmt || (v => v);
    const narrow = chart.width < 520;
    const items = [];
    chart.data.datasets.forEach((ds, di) => {
      const meta = chart.getDatasetMeta(di); if (meta.hidden) return;
      let k = ds.data.length - 1; while (k >= 0 && ds.data[k] == null) k--;
      if (k < 0 || !meta.data[k]) return;
      const pt = meta.data[k];
      items.push({ x: pt.x, y: pt.y, c: ds.borderColor, t: narrow ? ds.label : `${ds.label} ${fmt(ds.data[k])}` });
    });
    items.sort((a, b) => a.y - b.y);
    const h = 14;
    for (let i = 1; i < items.length; i++) if (items[i].y - items[i - 1].y < h) items[i].y = items[i - 1].y + h;
    for (let i = items.length - 1; i >= 0; i--) { items[i].y = Math.min(items[i].y, bottom - 2); if (i < items.length - 1 && items[i + 1].y - items[i].y < h) items[i].y = items[i + 1].y - h; }
    ctx.save();
    ctx.font = `600 11px IBM Plex Sans, Noto Sans TC, system-ui, sans-serif`;
    ctx.textBaseline = 'middle';
    items.forEach(it => {
      const w = ctx.measureText(it.t).width;
      const x = Math.min(Math.max(it.x, right) + 6, chart.width - w - 2);
      ctx.fillStyle = T('--surface'); ctx.fillRect(x - 2, it.y - 7, w + 4, 14);
      ctx.fillStyle = it.c; ctx.fillText(it.t, x, Math.max(top + 7, it.y));
    });
    ctx.restore();
  },
};
if (window.Chart) Chart.register(endLabels);
/* 線尾標籤需要右邊留白 */
const endPad = (w) => ({ layout: { padding: { right: w || 84, top: 8 } } });
/* 對數刻度：以 100 為中心，每一格翻一倍（…50、100、200、400…），剛好蓋住資料範圍 */
function logTicks(values, base = 100) {
  const vs = values.filter(v => v != null && v > 0);
  const lo0 = Math.min(base, ...vs), hi0 = Math.max(base, ...vs);
  let lo = base, hi = base;
  while (lo > lo0) lo /= 2;
  while (hi < hi0) hi *= 2;
  const ticks = []; for (let v = lo; v <= hi; v *= 2) ticks.push(v);
  return { min: lo, max: hi, ticks };
}
/* 季度標籤 'nQyy'：短期間每季都標，長期間只在第一季標年份 */
function qTicks(labels) {
  const yearOnly = labels.length > 20;
  return { autoSkip: !yearOnly, maxTicksLimit: 8, callback: (v) => { const l = labels[v]; if (!l) return ''; return yearOnly ? (l[0] === '1' ? '20' + l.slice(2) : '') : l; } };
}
/* 基準線（100 或 0）畫深一點，其他格線淡 */
const gridWithBase = (baseVal) => ({ color: (c) => c.tick.value === baseVal ? T('--axis') : T('--grid'), lineWidth: (c) => c.tick.value === baseVal ? 1.5 : 1, drawTicks: false });
/* 缺資料（null）的地方用虛線跨過，而不是假裝連起來；最後一個點畫圓點 */
function cmpLine(o) {
  return line(Object.assign({ borderWidth: 2.25, spanGaps: true,
    segment: { borderDash: (c) => c.p0.skip || c.p1.skip ? [4, 4] : undefined },
    pointRadius: (c) => { const d = c.dataset.data; let k = d.length - 1; while (k >= 0 && d[k] == null) k--; const f = d.findIndex(v => v != null); return c.dataIndex === k || (f > 0 && c.dataIndex === f) ? 3 : 0; },
    pointHoverRadius: 4 }, o));
}
function syncSeg(id, attr, val) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.setAttribute('aria-pressed', String(b.dataset[attr] === val)));
}
function copyBtn(btn, ok, fn) {
  $(btn).addEventListener('click', async () => {
    const text = fn();
    try { await navigator.clipboard.writeText(text); $(ok).textContent = '已複製'; }
    catch (e) {
      const ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      let done = false; try { done = document.execCommand('copy'); } catch (er) {}
      ta.remove(); $(ok).textContent = done ? '已複製' : '瀏覽器擋下複製，請改用表格選取';
    }
    $(ok).hidden = false; setTimeout(() => { $(ok).hidden = true; }, 2500);
  });
}

/* 日期：支援 YYYY-MM-DD、YYYY-MM、YYYY-Qn、YYYY-Hn、YYYY */
const dy = (s) => {
  let m;
  if ((m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/))) return +m[1] + (m[2] - 1) / 12 + (m[3] - 1) / 365;
  if ((m = s.match(/^(\d{4})-(\d{2})$/))) return +m[1] + (m[2] - 0.5) / 12;
  if ((m = s.match(/^(\d{4})-Q(\d)$/))) return +m[1] + (m[2] - 0.5) / 4;
  if ((m = s.match(/^(\d{4})-H(\d)$/))) return +m[1] + (m[2] - 0.5) / 2;
  return +s.slice(0, 4) + 0.5;
};
const dfmt = (s) => {
  let m;
  if ((m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/))) return `${m[1]}/${m[2]}/${m[3]}`;
  if ((m = s.match(/^(\d{4})-(\d{2})$/))) return `${m[1]}/${m[2]}`;
  if ((m = s.match(/^(\d{4})-Q(\d)$/))) return `${m[1]} Q${m[2]}`;
  if ((m = s.match(/^(\d{4})-H(\d)$/))) return `${m[1]} ${m[2] === '1' ? '上' : '下'}半年`;
  return `${s} 年`;
};
const UNC = '<span class="unc-chip">待確定</span>';
const srcLink = (o) => o.src ? `<a href="${o.src}" target="_blank" rel="noopener">${(o.unc || /^媒體報導/.test(o.note || '')) ? '媒體' : '來源'}</a>` : '';

/* 從營收到淨利的拆解圖（HTML 長條） */
function drawWaterfall(W, el) {
  const R = W.rows[0].v; let run = 0; const rows = [];
  const scale = 100 / (R * 1.03);
  W.rows.forEach(r => {
    let a, b;
    if (r.t) { a = 0; b = r.v; run = r.v; } else { a = run; b = run + r.v; run = b; }
    const lo = Math.min(a, b), hi = Math.max(a, b);
    const color = r.t ? T('--s1') : (r.v < 0 ? T('--neg') : T('--pos-soft'));
    const share = r.v / R * 100;
    rows.push(`<div class="wf-row${r.t ? ' total' : ''}">
      <span class="nm">${r.n}</span>
      <span class="wf-track"><span class="wf-bar" style="left:${lo * scale}%;width:${Math.max((hi - lo) * scale, 0.4)}%;background:${color}"></span></span>
      <span class="v">${r.t ? '' : (r.v > 0 ? '+' : '−')}${f1(Math.abs(r.v))}<em>${r.t ? '占營收 ' + share.toFixed(1) + '%' : (share > 0 ? '+' : '−') + Math.abs(share).toFixed(1) + '%'}</em></span>
    </div>`);
  });
  $(el).innerHTML = rows.join('');
}
