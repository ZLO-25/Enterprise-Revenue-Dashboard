/* 共用前端函式（新公司的模板用；以 {{COMMON_JS}} 內嵌進頁面）。
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
