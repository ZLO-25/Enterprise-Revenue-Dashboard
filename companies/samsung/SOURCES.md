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
- 排程：週二至週六 08:30（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

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

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

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

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `005930.KS`（主要掛牌地普通股，幣別 韓元） |
| 股價起點 | 2018-01 |
| 股票分割 | 2018-05 一拆五十股票分割：Yahoo Close 已調整，抽查時要確認（Yahoo Close 已依分割調整、不含股利調整，才跟本站已換算成今天股數的 EPS 對得上） |
| EPS 口徑 | 基本 EPS，普通股（不用特別股）；都是公認會計準則數字，不用調整後 EPS |
| 財報公布日 `rd` 來源 | 三星 IR 活動頁的 Earnings Conference Call 日期（rdB:c；季初的初步業績沒有 EPS，不算） |

**更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）**
1. 新增一季時，同時填該季 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`。讀不到就填 `null`，在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用「季度結束後幾天」推算**。最新一季的 `rd` 不可為 null。
2. 股價檔 `data/prices/samsung.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填、不修改；排程只檢查上個月有沒有進來。
3. 本益比（`tools/pe.py`）與預估本益比不存檔，建置時算出；預估只有每月 1–6 日 Actions 存下的快照，**不回填**。
4. 若這家公司發生股票分割：同一次完成 EPS 重編與股價檔重抓（手動觸發 prices-monthly 並填 `accept=samsung`），否則 validate 會因相鄰月份本益比跳動超過 3 倍而失敗。
5. 抽查紀錄（回補時每家人工對第二個獨立來源抽 3 個月：最早一個月、最近一次分割前一個月、最新一個月）：見下表。

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| 2018-01（2018-01-31） | 49900.0 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2018-04（2018-04-30） | 53000.0 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2026-10（2026-10-30） | 225000.0 | stockanalysis.com/quote/krx/005930/history | 一致（225000.0；2026-11-12 讀取，頁面標示已依分割調整） |


## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）

單位：百萬韓元（股數欄位為百萬股，本檔沒有值）。2026-11-12 補入，1Q18–3Q26 共 35 季。

| 欄位 | 口徑與來源 |
| --- | --- |
| `cash` | 現金及約當現金（Cash and cash equivalents，不含短期金融商品）。來源：IR 季度財報 PDF `https://images.samsung.com/is/content/samsung/assets/global/ir/docs/{年}_con_quarter0{1-3}_bs.pdf`（2019 年第一季在 `p5/global/ir/docs/`）；每份有「當季末」與「上年底」兩欄，第四季取下一年度各份的上年底欄（4Q25 取 `2025_con_quarter04_bs.pdf`） |
| `debt` | 短期借款＋一年內到期長期負債＋公司債（Debentures，非流動）＋長期借款，四項相加，同上 bs PDF。核對：3Q25 相加 16,672,280，與 3Q26 簡報的 Debts 欄 16,672.3 十億韓元一致；2Q26 相加 22,408.7 十億韓元與簡報一致 |
| `equity` | Equity attributable to owners of the parent（歸屬母公司權益，不含非控制權益），同上 bs PDF（2021 年以前標示為「of the Company」，同一小計列） |
| `pretax` | Profit before income tax（單季）。來源：`{年}_con_quarter0{1-4}_soi.pdf`。第一到第三季取 3M 欄；第四季＝全年（`quarter04_soi`）− 前九個月（9M 欄）；每年都驗算 3M 加總 ＝ 6M／9M 欄 |
| `tax` | Income tax expense（單季），算法同 `pretax`。4Q22 為所得稅利益（負值，−18,786,528）、2Q23、3Q23、4Q23 也是負值（所得稅利益），照來源保留負號 |
| `buyback` | 現金流量表 Purchase of treasury shares（`{年}_con_quarter0{1-4}_cf.pdf`，正數）。累計欄逐期相減：Q2＝6M−3M、Q3＝9M−6M、Q4＝全年−9M。2023 全年與 2024 前三季來源印「-」，填 0；2024 全年 1,811,775、2025 全年 8,189,263、2026 上半年 13,248,625 |
| `shOut`、`dilSh` | 全部 null。Samsung IR 的財報 PDF 在可讀範圍內（股本附註 15、每股盈餘附註 23 被截斷）沒有股數；簡報也沒有。不用淨利÷EPS 推算 |

3Q26 特例：DART／IR 的 3Q26 合併財報 PDF 尚未公布（2026-11-12），只用法說會簡報（`2026_3Q_conference_eng.pdf`，註明會計師核閱尚未完成）：

- `debt` 17,191,200：簡報 Debts 17,191.2 十億韓元；簡報的 Debts 口徑已用 2Q26、3Q25 對過，與上述四項相加一致。
- `pretax` 98,500,000、`tax` 23,400,000、`buyback` 12,500,000：簡報只印到 0.1 兆韓元，所以是四捨五入值（稅前 98.5 − 稅 23.4 ＝ 淨利 75.1，與簡報一致）。
- `cash`、`equity` 填 null：簡報的 Cash 含短期金融商品，口徑不符；簡報只有權益總額（含非控制權益）。等 3Q26 季報公布後補，並把 `pretax`、`tax`、`buyback` 換成附註精確值。

有值季數：`cash` 34、`debt` 35、`equity` 34、`pretax` 35、`tax` 35、`buyback` 15（2023 起）、`shOut` 0、`dilSh` 0。

`buyback` 2018–2022 為 null：現金流量表財務活動沒有買回庫藏股列（合計與各列加總一致），無法確認是真的沒買回，還是改列在其他區塊（如信託），所以不填 0。要補需讀權益變動表或附註。

淨利÷稀釋股數的 4% 核對：因 `dilSh` 全 null，沒有適用。
