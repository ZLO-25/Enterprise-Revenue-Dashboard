// 執行：node --test quant/tests/engine-phase2.test.mjs
// 第二階段新增的純函式：xirr、monthlyContribution（每月定期投入）、drawdownEpisodes（大跌與回本）
// 全部用手算得出答案的小例子；沒有用任何真實價格。
import test from "node:test";
import assert from "node:assert/strict";
import { xirr, monthlyContribution, drawdownEpisodes, assetDrawdown, toDay, fromDay } from "../js/engine.js";

const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps, `${a} 應該約等於 ${b}`);

/** 合成價格：從 startIso 起每個日曆天一筆（skip 內的日期當作休市），價格由 f(index, date) 決定 */
function mk(symbol, startIso, nDays, f, skip = []) {
  const dates = [], close = [];
  const d0 = toDay(startIso);
  for (let k = 0; k < nDays; k++) {
    const d = fromDay(d0 + k);
    if (skip.includes(d)) continue;
    dates.push(d); close.push(f(dates.length - 1, d));
  }
  return { symbol, dates, close };
}

// ---------------- xirr ----------------
test("xirr：投入 100，剛好 365 天後拿回 200 → 100%", () => {
  near(xirr([{ date: "2021-01-01", amount: -100 }, { date: "2022-01-01", amount: 200 }]), 1.0, 1e-9);
});
test("xirr：730 天翻倍 → √2 − 1", () => {
  near(xirr([{ date: "2020-01-01", amount: -100 }, { date: "2021-12-31", amount: 200 }]), Math.SQRT2 - 1, 1e-9);
});
test("xirr：賠錢（100 變 50，365 天）→ −50%", () => {
  near(xirr([{ date: "2021-01-01", amount: -100 }, { date: "2022-01-01", amount: 50 }]), -0.5, 1e-9);
});
test("xirr：兩筆投入，手算驗證 NPV 為 0", () => {
  const fl = [{ date: "2021-01-01", amount: -100 }, { date: "2021-07-02", amount: -100 }, { date: "2022-01-01", amount: 230 }];
  const r = xirr(fl);
  const t = fl.map((f) => (toDay(f.date) - toDay(fl[0].date)) / 365);
  const npv = fl.reduce((a, f, i) => a + f.amount / Math.pow(1 + r, t[i]), 0);
  near(npv, 0, 1e-7);
});
test("xirr：全部同方向、不足兩筆 → null", () => {
  assert.equal(xirr([{ date: "2021-01-01", amount: -100 }, { date: "2022-01-01", amount: -5 }]), null);
  assert.equal(xirr([{ date: "2021-01-01", amount: -100 }]), null);
});

// ---------------- monthlyContribution ----------------
test("價格固定：報酬 0、本金階梯、XIRR 0", () => {
  const s = mk("FLAT", "2020-01-01", 400, () => 10);   // 2020-01-01 起 400 天，每天都是交易日
  const r = monthlyContribution(s, { monthly: 1000, initial: 0, start: "2020-01-01", end: "2021-02-01" });
  // 2020-01 ~ 2021-02 共 14 個月，每月第一天買進
  assert.equal(r.count, 14);
  assert.equal(r.totalInvested, 14000);
  near(r.final, 14000, 1e-6);
  near(r.pnl, 0, 1e-6);
  near(r.xirr, 0, 1e-9);
  assert.equal(r.worst.rate === 0 || Math.abs(r.worst.rate) < 1e-12, true);
  assert.equal(r.underwater, null);
  // 本金是階梯：2020-01-31 還是 1000，2020-02-01 變 2000
  assert.equal(r.invested[r.dates.indexOf("2020-01-31")], 1000);
  assert.equal(r.invested[r.dates.indexOf("2020-02-01")], 2000);
});

test("價格翻倍（一次買進，365 天）→ XIRR 100%", () => {
  // 只有起始資金、每月 0 不行（monthly+initial 至少一個 > 0 即可）：initial 1000、monthly 0
  const d0 = toDay("2021-01-01");
  const dates = [fromDay(d0), fromDay(d0 + 365)];
  const s = { symbol: "X2", dates, close: [10, 20] };
  const r = monthlyContribution(s, { monthly: 0, initial: 1000, start: "2021-01-01", end: "2022-01-01" });
  assert.equal(r.totalInvested, 1000);
  near(r.final, 2000, 1e-9);
  near(r.pnlRate, 1.0, 1e-12);
  near(r.xirr, 1.0, 1e-9);
});

test("期間不到 1 年：不給 XIRR", () => {
  const s = mk("S", "2021-01-01", 200, (i) => 10 + i * 0.01);
  const r = monthlyContribution(s, { monthly: 100, initial: 0, start: "2021-01-01", end: "2021-07-01" });
  assert.ok(r.years < 1);
  assert.equal(r.xirr, null);
});

test("月初不是交易日：順延到當月第一個交易日", () => {
  // 2024-09-01 是週日；這個合成序列把 09-01、09-02 都當休市 → 9 月的買進落在 09-03
  const s = mk("D", "2024-07-01", 120, () => 10, ["2024-09-01", "2024-09-02"]);
  const r = monthlyContribution(s, { monthly: 500, initial: 0, start: "2024-07-01", end: "2024-10-31" });
  const dates = r.buys.map((b) => b.date);
  assert.deepEqual(dates, ["2024-07-01", "2024-08-01", "2024-09-03", "2024-10-01"]);
});

test("開始日不是月初：開始日當天（或之後第一個交易日）買進，下個月初再買", () => {
  // start 2024-03-10；03-10 當天有交易
  const s = mk("M", "2024-01-01", 200, () => 10);
  const r = monthlyContribution(s, { monthly: 100, initial: 0, start: "2024-03-10", end: "2024-06-30" });
  assert.deepEqual(r.buys.map((b) => b.date), ["2024-03-10", "2024-04-01", "2024-05-01", "2024-06-01"]);
  // start 落在休市日 → 之後第一個交易日
  const s2 = mk("M2", "2024-01-01", 200, () => 10, ["2024-03-10", "2024-03-11"]);
  const r2 = monthlyContribution(s2, { monthly: 100, initial: 0, start: "2024-03-10", end: "2024-04-30" });
  assert.deepEqual(r2.buys.map((b) => b.date), ["2024-03-12", "2024-04-01"]);
});

test("一開始已有的資金：第一天一次投入，加上當月的每月投入", () => {
  const s = mk("I", "2022-01-03", 100, () => 20);
  const r = monthlyContribution(s, { monthly: 100, initial: 1000, start: "2022-01-03", end: "2022-03-31" });
  assert.equal(r.buys[0].amount, 1100);
  assert.equal(r.invested[0], 1100);
  assert.equal(r.totalInvested, 1100 + 100 + 100);   // 1 月 1100、2 月 100、3 月 100
  near(r.final, r.totalInvested, 1e-9);
  // 年表：當年投入包含起始資金
  assert.equal(r.annual[0].contributed, 1300);
});

test("資料起點晚於開始日：從資料第一天算起，actualStart 照實回報", () => {
  const s = mk("L", "2024-03-15", 100, () => 10);
  const r = monthlyContribution(s, { monthly: 100, initial: 0, start: "2024-01-01", end: "2024-06-30" });
  assert.equal(r.actualStart, "2024-03-15");
  assert.deepEqual(r.buys.map((b) => b.date), ["2024-03-15", "2024-04-01", "2024-05-01", "2024-06-01"]);
});

test("最難熬的時候與低於本金的最長天數", () => {
  // 每月 100。價格：1~2 月 10；3/1 起跌到 5（持續到 4/30）；5/1 起回到 20
  const s = mk("W", "2022-01-01", 181, (i, d) => (d < "2022-03-01" ? 10 : d < "2022-05-01" ? 5 : 20));
  const r = monthlyContribution(s, { monthly: 100, initial: 0, start: "2022-01-01", end: "2022-06-30" });
  // 3/1 買進後：股數 = 10 + 10 + 20 = 40，價格 5 → 資產 200、累積投入 300 → 率 −1/3
  // 4/1 買進後：股數 60 → 資產 300、投入 400 → 率 −0.25；4/30 前都在水下，最低的是 3/1 當天的 −1/3
  assert.equal(r.worst.date, "2022-03-01");
  near(r.worst.rate, -1 / 3, 1e-9);
  assert.equal(r.worst.invested, 300);
  near(r.worst.value, 200, 1e-9);
  // 水下：3/1 ~ 4/30（61 天）；5/1 價格 20 → 資產 80*20 = 1600 > 本金 500 → 回到本金以上
  assert.equal(r.underwater.from, "2022-03-01");
  assert.equal(r.underwater.to, "2022-04-30");
  assert.equal(r.underwater.days, 61);
  assert.equal(r.underwater.recovered, true);
  assert.equal(r.underwater.recoveryDate, "2022-05-01");
});

test("到資料最後一天還在水下：recovered=false", () => {
  const s = mk("U", "2022-01-01", 90, (i, d) => (d < "2022-02-01" ? 10 : 5));
  const r = monthlyContribution(s, { monthly: 100, initial: 0, start: "2022-01-01", end: "2022-03-31" });
  assert.equal(r.underwater.recovered, false);
  assert.equal(r.underwater.to, "2022-03-31");
});

test("逐年表：年底累積投入與年底資產", () => {
  const s = mk("Y", "2021-11-01", 150, () => 10);   // 2021-11 ~ 2022-03
  const r = monthlyContribution(s, { monthly: 100, initial: 0, start: "2021-11-01", end: "2022-03-31" });
  assert.equal(r.annual.length, 2);
  assert.equal(r.annual[0].year, "2021"); assert.equal(r.annual[0].contributed, 200); assert.equal(r.annual[0].endInvested, 200);
  assert.equal(r.annual[1].year, "2022"); assert.equal(r.annual[1].contributed, 300); assert.equal(r.annual[1].endInvested, 500);
  near(r.annual[1].endValue, 500, 1e-9);
  near(r.annual[1].pnlRate, 0, 1e-12);
});

// ---------------- drawdownEpisodes ----------------
const D = (n) => Array.from({ length: n }, (_, i) => fromDay(toDay("2020-01-01") + i));

test("一段大跌：高點、低點、回本日與各段天數", () => {
  const v = [100, 90, 70, 60, 80, 100, 110];
  const ep = drawdownEpisodes(D(v.length), v, 0.2);
  assert.equal(ep.length, 1);
  const e = ep[0];
  assert.equal(e.peakDate, "2020-01-01"); assert.equal(e.troughDate, "2020-01-04");
  near(e.depth, -0.4, 1e-12);
  assert.equal(e.daysToTrough, 3);
  assert.equal(e.recoveryDate, "2020-01-06");   // 回到 100（>= 前高）
  assert.equal(e.daysToRecover, 2); assert.equal(e.daysTotal, 5);
  assert.equal(e.recovered, true); assert.equal(e.daysSincePeak, null);
});

test("尚未回本：recoveryDate 為 null，記錄從高點到最後一天的天數", () => {
  const v = [100, 120, 100, 80, 90];
  const ep = drawdownEpisodes(D(v.length), v, 0.2);
  assert.equal(ep.length, 1);
  assert.equal(ep[0].peakDate, "2020-01-02");
  assert.equal(ep[0].troughDate, "2020-01-04");
  near(ep[0].depth, 80 / 120 - 1, 1e-12);
  assert.equal(ep[0].recoveryDate, null); assert.equal(ep[0].daysToRecover, null); assert.equal(ep[0].daysTotal, null);
  assert.equal(ep[0].recovered, false);
  assert.equal(ep[0].daysSincePeak, 3);   // 01-02 → 01-05
});

test("連續兩段：回到前高才算結束，之後再跌是新的一段", () => {
  const v = [100, 70, 100, 130, 90, 135];
  const ep = drawdownEpisodes(D(v.length), v, 0.2);
  assert.equal(ep.length, 2);
  assert.equal(ep[0].peakDate, "2020-01-01"); assert.equal(ep[0].recoveryDate, "2020-01-03");   // 剛好回到 100 就算回本
  assert.equal(ep[1].peakDate, "2020-01-04"); assert.equal(ep[1].troughDate, "2020-01-05"); assert.equal(ep[1].recoveryDate, "2020-01-06");
});

test("剛好等於門檻算（跌 20% 整）；差一點不算", () => {
  const ep20 = drawdownEpisodes(D(3), [100, 80, 100], 0.2);
  assert.equal(ep20.length, 1);
  const ep19 = drawdownEpisodes(D(3), [100, 80.5, 100], 0.2);   // 只跌 19.5%
  assert.equal(ep19.length, 0);
});

test("資料第一天就是高點：從第一天算起", () => {
  const ep = drawdownEpisodes(D(4), [50, 30, 35, 50], 0.3);
  assert.equal(ep.length, 1);
  assert.equal(ep[0].peakDate, "2020-01-01"); assert.equal(ep[0].recoveryDate, "2020-01-04");
});

test("一路創新高、或跌幅都沒到門檻 → 空陣列；門檻越高段數越少", () => {
  assert.deepEqual(drawdownEpisodes(D(4), [1, 2, 3, 4], 0.1), []);
  const v = [100, 85, 100, 60, 100, 45, 100];
  assert.equal(drawdownEpisodes(D(7), v, 0.1).length, 3);
  assert.equal(drawdownEpisodes(D(7), v, 0.3).length, 2);
  assert.equal(drawdownEpisodes(D(7), v, 0.5).length, 1);
});

test("相同高點：與前高持平不算回本後的新一段；水下期間的持平高點算從最後一次持平開始", () => {
  // 100、100（持平，沒有跌）→ 70 → 100（回本）→ 100 → 60（新一段，從 01-05 的 100 算起）
  const ep = drawdownEpisodes(D(7), [100, 100, 70, 100, 100, 60, 61], 0.2);
  assert.equal(ep.length, 2);
  assert.equal(ep[0].peakDate, "2020-01-02"); assert.equal(ep[0].recoveryDate, "2020-01-04");
  assert.equal(ep[1].peakDate, "2020-01-05"); assert.equal(ep[1].recovered, false);
});

// ---------------- assetDrawdown（資產從高點回落最多的一次） ----------------
test("assetDrawdown：以跌幅 % 最大的那一次為準（不是金額最大）", () => {
  // 第一次 100 → 50（−50%，回落 50）；第二次 1000 → 700（−30%，回落 300）→ 取第一次
  const v = [100, 50, 120, 1000, 700, 800];
  const a = assetDrawdown(D(6), v);
  assert.equal(a.peakDate, "2020-01-01"); assert.equal(a.troughDate, "2020-01-02");
  near(a.pct, -0.5, 1e-12); near(a.amount, -50, 1e-12);
  assert.equal(a.recoveryDate, "2020-01-03");
});
test("assetDrawdown：還沒回到高點 → recoveryDate null；一路上漲或持平 → null", () => {
  const a = assetDrawdown(D(4), [100, 200, 150, 160]);
  assert.equal(a.peakDate, "2020-01-02"); assert.equal(a.troughDate, "2020-01-03");
  near(a.pct, -0.25, 1e-12); assert.equal(a.recoveryDate, null);
  assert.equal(assetDrawdown(D(3), [1, 2, 3]), null);
  assert.equal(assetDrawdown(D(3), [5, 5, 5]), null);
});
test("monthlyContribution 的 valueDrawdown：期間內新投入的錢也算在資產裡", () => {
  // 每月 100；價格 1/1~1/14 是 10、1/15 起是 5。1/1 買 10 股 → 資產 100，持平到 1/14（持平取最早的高點 1/1）
  // 1/15 資產 = 10 × 5 = 50 → 從 100 回落 50%（這段沒有新錢，和股價跌幅相同）
  // 2/1 再投入 100 → 資產 150 ≥ 100：資產「回到高點」是新錢墊回來的，股價其實沒有回升
  const s = mk("V", "2022-01-01", 59, (i, d) => (d < "2022-01-15" ? 10 : 5));
  const r = monthlyContribution(s, { monthly: 100, initial: 0, start: "2022-01-01", end: "2022-02-28" });
  assert.equal(r.valueDrawdown.peakDate, "2022-01-01");
  near(r.valueDrawdown.peakValue, 100, 1e-9);
  assert.equal(r.valueDrawdown.troughDate, "2022-01-15");
  near(r.valueDrawdown.troughValue, 50, 1e-9);
  near(r.valueDrawdown.pct, -0.5, 1e-12);
  assert.equal(r.valueDrawdown.recoveryDate, "2022-02-01");
});
