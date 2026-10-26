# {{NAME}}（{{TICKER}}）資料來源與更新步驟

- 資料檔：`data/{{CODE}}.json`（schema `v1`）　頁面：`/{{CODE}}/`　模板：`templates/{{TEMPLATE}}.frag.html`（通用模板）
- 單位：**{{UNIT}}**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；每股數字（`eps`、`dps`）為{{EPS_UNIT}}。
- 頻率：每季。財報日約在＿＿月。
- 排程：每週一 08:00（台北）。**多數週沒有新財報，這時只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 期間

＿Q＿＿–最新一季（說明為什麼從這一季開始：公司最早可取得的季度財報）。

## 來源（依可信度）

1. 主管機關申報文件（美股：SEC EDGAR 10-Q／10-K／8-K；台股：公開資訊觀測站；其他市場請寫明）
   - 網址、檔名慣例、XBRL 概念名稱（例：`RevenueFromContractWithCustomerExcludingAssessedTax`）
2. 公司投資人關係網站（財報新聞稿、簡報、股東信）
3. 法說會逐字稿
4. 可信媒體（Reuters、Bloomberg、CNBC 等）：**只用於事件時間軸**；公司未證實的一律 `unc:1`

## 欄位定義（共用欄位 `quarters[]`，每季一筆，依時間排序）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 單季營收 |
| `gp`、`gm` | 毛利；`gm`＝`gp`÷`rev`×100（小數 1 位） |
| `opInc`、`om` | 營業利益（GAAP／IFRS） |
| `ni` | 歸屬母公司（普通股股東）淨利 |
| `eps` | 稀釋後每股盈餘；第四季取公司公布的 Q4 數字，不能用全年減前三季 |
| `ocf` | 營業活動現金流（年初累計要相減得單季） |
| `capex` | 購置不動產、廠房及設備（正數） |
| `fcf` | `ocf − capex` |
| `dps` | 該季每股現金股利；不配息填 `null` |

### 第四季推算
年報只有全年時：**4Q ＝ 全年 − 前三季累計**（EPS 除外）。

### 選用區塊
- `segments`：營收拆分 `{title, unit, keys:[{k, n}], quarters:[{q, k1, k2…}], note}`；各分部加總必須等於 `rev`。
- `extra`：公司專屬指標 `{title, note, keys:[{k, n, unit?, pct?, dec?, chart?:"bar"/"line", zero?, desc?}], quarters:[{q, …}]}`；沒揭露填 `null`，**不要估計**。
- `guidance.items[]`：`{label, period, lo, hi, unit, note}`。
- `notes.unavailable[]`：取不到的欄位，頁面會列出。

## 資料誠實規則
- 每個數字都要能追到來源，而且真的讀到。讀不到、算不出來、來源對不起來 → 填 `null`，在 `notes.unavailable` 加「待確認：哪一季、哪個欄位、為什麼」。
- 不估計、不內插、不從記憶補數字。`rev`、`gm`、`om`、`eps` 讀不到的那一季先不收。
- 只有媒體報導的事件 → `unc:1`，`note` 以「待確定：」開頭。

## 核對規則（`python3 tools/validate.py {{CODE}}` 會自動做）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `segments` 各分部加總 ＝ 營收。
4. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項。
5. 財測區間上下限沒有顛倒；日期格式正確。

需要公司專屬的核對（例：某個非 GAAP 指標對照公司全年公布值）→ 在 `tools/validate.py` 的 `CHECKS` 加 `"{{CODE}}": 函式`。

## 更新步驟（每週）

1. 查有沒有新的財報（申報系統全文搜尋或公司 IR 網站）。**沒有新財報 → 跳到第 5 步。**
2. 有新財報：新增一季到 `quarters[]`（與 `segments`、`extra` 的 `quarters[]`），第四季時新增 `annual`。
3. 更新 `guidance`、`waterfall`（換成新一季）、`events`（下一個公布日）。
4. `python3 tools/validate.py {{CODE}}`；通過才繼續。
5. 查事件時間軸：新合約、產品、併購、指數異動。公司證實的照常收錄；只有媒體報導的加 `unc:1`，`note` 以「待確定：」開頭。
6. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口（取不到或公司未揭露）

- （列出）
