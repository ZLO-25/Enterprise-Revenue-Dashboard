/* 資料格式轉接層（normalization layer）
   目的：不管公司資料是哪一種格式（schema），都轉成同一種「標準季度序列」，
   讓首頁、跨公司比較、長期指標（assets/longterm.js）只需要認得一種格式。

   標準序列 N：
     N.Q[]      每季：{ q, yr, qi, rev, gp, gm, om, nm, ni, eps, ocf, capex, fcf, dps }  金額單位 = N.unit
     N.unit     金額單位的中文（例：百萬美元、億元新台幣）
     N.unitShort 放在數字旁的短單位（例：百萬美元、億）
     N.epsUnit  每股單位（美元、元）
     N.latest   首頁卡片用的「最新一期」摘要：{ revLabel, rev, revUnit, yoy, qLabel, gm, om, eps, epsUnit, next }
     N.next     下一個公布日 {date, t, est?} 或 null
   新增一種資料格式 → 在 ADAPTERS 加一個以 schema 名稱為鍵的函式；符合 v1 的公司什麼都不用加。 */
const nextEvent = (D) => (D.events || []).filter(e => e.date > D.asOf).sort((a, b) => a.date < b.date ? -1 : 1)[0] || null;
const qParts = (q) => ({ yr: 2000 + Number(q.slice(2)), qi: Number(q[0]) });
const ADAPTERS = {
  /* 台積電舊格式：monthly 為新台幣百萬元、quarters 的 rev/ni 為百萬元、capex/ocf 為十億元 → 一律換成「億元」 */
  'tsmc-legacy': (D, c) => {
    const Q = D.quarters.map(q => {
      const rev = q.rev / 100, ocf = q.ocf == null ? null : q.ocf * 10, capex = q.capex == null ? null : q.capex * 10;
      return Object.assign({ q: q.q, rev, gp: rev * q.gm / 100, gm: q.gm, om: q.om, ni: q.ni / 100, nm: q.ni / q.rev * 100, eps: q.eps,
        ocf, capex, fcf: ocf == null || capex == null ? null : ocf - capex, dps: q.dps }, qParts(q.q));
    });
    const ys = Object.keys(D.monthly).map(Number).sort((a, b) => a - b), y = ys[ys.length - 1];
    const arr = D.monthly[String(y)], m = arr.length, v = arr[m - 1], prev = (D.monthly[String(y - 1)] || [])[m - 1];
    const L = Q[Q.length - 1];
    return { Q, unit: '億元新台幣', unitShort: '億', epsUnit: '元', next: nextEvent(D),
      latest: { revLabel: `${y}/${String(m).padStart(2, '0')} 月營收`, rev: v / 100, revUnit: '億元新台幣', yoy: prev ? (v / prev - 1) * 100 : null,
        qLabel: L.q, gm: L.gm, om: L.om, eps: L.eps, epsUnit: '元', next: nextEvent(D) } };
  },
  /* 共用格式 v1：quarters[] 為「百萬」單位（幣別看 companies.json 的 currency） */
  'v1': (D, c) => {
    const cur = { USD: '百萬美元', TWD: '百萬元新台幣', JPY: '百萬日圓', EUR: '百萬歐元', HKD: '百萬港元', CNY: '百萬人民幣' }[c.currency] || ('百萬' + c.currency);
    const epsUnit = { USD: '美元', TWD: '元', JPY: '日圓', EUR: '歐元', HKD: '港元', CNY: '人民幣' }[c.currency] || c.currency;
    const Q = D.quarters.map(q => Object.assign({}, q, qParts(q.q), {
      gp: q.gp == null ? (q.gm == null ? null : q.rev * q.gm / 100) : q.gp,
      nm: q.ni == null ? null : q.ni / q.rev * 100,
      fcf: q.fcf != null ? q.fcf : (q.ocf == null || q.capex == null ? null : q.ocf - q.capex),
    }));
    const L = Q[Q.length - 1], P = Q[Q.length - 5];
    return { Q, unit: cur, unitShort: cur, epsUnit, next: nextEvent(D),
      latest: { revLabel: `${L.q} 營收`, rev: L.rev, revUnit: cur, yoy: P ? (L.rev / P.rev - 1) * 100 : null,
        qLabel: L.q, gm: L.gm, om: L.om, eps: L.eps, epsUnit, next: nextEvent(D) } };
  },
};
function normalize(D, c) {
  const N = (ADAPTERS[c.schema] || ADAPTERS.v1)(D, c);
  N.Q.forEach((x, i) => {
    x.yoy = i >= 4 && N.Q[i - 4].rev ? (x.rev / N.Q[i - 4].rev - 1) * 100 : null;
    x.qoq = i >= 1 && N.Q[i - 1].rev ? (x.rev / N.Q[i - 1].rev - 1) * 100 : null;
  });
  N.c = c; N.D = D; N.asOf = D.asOf;
  return N;
}
