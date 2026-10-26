# 三星電子（KRX 005930）資料來源與更新步驟

- 資料檔：`data/samsung.json`（schema `v1`）　頁面：`/samsung/`　模板：`templates/generic.frag.html`（通用模板）
- 口徑：**K-IFRS（韓國採用的國際財務報導準則）合併報表**。三星不在 SEC 申報，法定申報在韓國金融監督院 DART。
- 單位：**百萬韓元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；每股數字（`eps`）為**韓元**；官方簡報是兆韓元，填資料時乘以 1,000,000（首頁的單位標籤固定是「百萬＋幣別」，所以一律用百萬韓元）。普通股基本 EPS（三星沒有稀釋性證券，簡報只列基本 EPS）。

```
單位換算
1 兆韓元 = 1,000 十億韓元 = 1,000,000 百萬韓元 = 10,000 億韓元
（DART 財報用百萬韓元；官方簡報用兆韓元；2011 年以前的簡報用「億韓元」）
```

- 頻率：每季。節奏：季底後約 1 週公布「初步業績」（只有營收與營業利益概數），季底後約 4 週開法說會（完整損益與現金流），約 45 天後在 DART 申報季報。
- 排程：每月 12 日 07:48（台北）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 期間

1Q18–最新一季。為什麼從 2018 年開始：

```
2009 以前   舊韓國會計準則（K-GAAP）→ 口徑不同，不收
2010–2017   K-IFRS 合併數字都有，但「第四季單季 EPS」公司從未公布
            （韓國年報只列全年 EPS；2018 年以前的簡報沒有 EPS 欄）→ EPS 是必要欄位，不收
2018 起     2019 年起的簡報有 EPS 欄，並列出 2018 年各季（含 4Q18）→ 從 1Q18 開始
```

## 來源（依可信度）

1. **三星電子法說會簡報（英文）**：IR 網站 `https://www.samsung.com/global/ir/financial-information/earnings-release/` 列出每季 PDF。檔名慣例：
   - 2019 年以後：`https://images.samsung.com/is/content/samsung/{p5|assets}/global/ir/docs/{年}_{季}Q_conference_eng.pdf`（2023 年 3Q、4Q 檔名多 `_01`；2020 年 4Q 起路徑是 `assets`，之前是 `p5`）
   - 2017 年：`…/p5/global/ir/docs/{年}_{季}Q_Earnings_Release_Samsung_Electronics.pdf`
   - 附錄 1 損益表（當季、上季、去年同季；第四季另有全年兩欄）、附錄 4 現金流量摘要（營業現金流、購置不動產廠房及設備）。
2. **季度損益表 PDF**（`{年}_con_quarter0{1|2|3}_soi.pdf`，單位百萬韓元）：DART 季報的英文版損益表，可用來核對第一到第三季。
3. **DART 電子公示** `https://dart.fss.or.kr/`（韓文法定申報，需要時核對）。容器與使用者電腦的 curl 都連不到 samsung.com 與 DART，用 WebFetch 讀 PDF。
4. 初步業績：Samsung Newsroom「Samsung Electronics Announces Earnings Guidance for {Third} Quarter {年}」。
5. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 簡報損益表 Sales |
| `gp`、`gm` | Gross profit；`gm`＝`gp`÷`rev`×100 |
| `opInc`、`om` | Operating profit（三星的營業費用「SG&A」已包含研發費用） |
| `ni` | Controlling interests（歸屬母公司業主淨利），不是 Net profit |
| `eps` | EPS（韓元，普通股基本 EPS，2018 年 1 拆 50 之後的股數） |
| `ocf` | 現金流量摘要 Cash flows from operating activities（單季） |
| `capex` | 現金流量摘要 Purchase of PP&E（取正數）。注意：這是現金流量表的現金支出，不是簡報另一頁「設備投資（CAPEX）」的應計金額 |
| `fcf` | `ocf − capex` |
| `dps` | 簡報沒有每股股利，`null` |

### 同一季出現在三份簡報時取哪一個

每一季會出現在「當季」「下一季（上季欄）」「隔年同季（去年同季欄）」三份簡報。規則：**取印得最精細（小數位數最多）的數字；一樣精細就取最晚公布的那份**。2024 年第四季起簡報只印到小數 1 位，所以 1Q24–3Q24 用當季簡報的 2 位小數。目前三份互相比對完全一致（差異 ≤ 四捨五入）。

### 第四季
第四季簡報直接列單季數字（不用全年相減）；`annual` 取第四季簡報的全年兩欄（FY），驗證四季加總 ＝ 全年。

## 核對規則（`python3 tools/validate.py samsung`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（容許 0.1%，四捨五入）。
3. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項；第一列營收＝最新一季 `rev`。
4. 同一季在不同簡報的數字要一致；不一致就以最新一份為準，並在 `notes.unavailable` 寫「待確認」。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每月排程）

1. 查 IR 網站有沒有新的法說會簡報（1、4、7、10 月下旬）。**沒有 → 只檢查有沒有新的初步業績（1、4、7、10 月上旬）：有就更新 `guidance`（label 寫「初步營收／初步營業利益（公司預告）」）與時間軸，然後跳到第 6 步。**
2. 有新簡報：讀附錄 1 損益表與附錄 4 現金流量摘要，取當季數字；同時用「上季」「去年同季」欄核對已收的季度。
3. 新增一季到 `quarters[]`；第四季時新增 `annual`。更新 `waterfall`（附錄 1 全部列）、`events`（下一次法說會日期；公司未公告前加 `est:1`）。
4. 簡報若註明「external review not completed」，在 `notes.unavailable` 保留一行「待確認：xQyy 數字核閱尚未完成」；下一季確認沒變再刪。
5. `python3 tools/validate.py samsung`；通過才繼續。
6. 查事件時間軸：股票分割、庫藏股、配息政策、重大投資與併購（優先公司新聞稿與 DART 公告）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口（頁面「沒能取得的欄位」會列出）

- 2010–2017（第四季 EPS 未揭露）與 2009 年以前（K-GAAP）。
- 每股股利、分部營收（DX／DS／SDC／Harman，簡報有，尚未收錄；2021 年 12 月組織調整前後口徑不同）。
