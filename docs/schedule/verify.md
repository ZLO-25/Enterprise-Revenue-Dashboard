# 每日排程附件：核對＋論點卡

> 每日排程的附件（`docs/SCHEDULE_PROMPT.md` 的 ⓪ 跑 `python3 tools/daily.py brief`，⑪ 列出才讀；安靜日不用讀）。2026-11-20 之前這段寫在 SCHEDULE_PROMPT.md 裡，現在只放這裡，改規則改這份。

### ③ 核對（狀態 completed 的公司）
- 等 10-Q／年報出來（看 `sec-feed.json` 的 periodic，或該公司 SOURCES.md 的核對來源），把快報數字對 XBRL／正式申報。**美股先跑 `python3 tools/daily.py inbox <代號>`**：每日準備已讀 SEC XBRL 做好核對表（營收、毛利、營業利益、淨利、稀釋 EPS、營業現金流、資本支出，最近 3 季）。全部 ✓ → 不用開 10-Q，直接解除待確認；有 ✗ 才打開該季 10-Q 查原因（口徑不同就照 SOURCES.md，不是自動以 SEC 為準）；新一季顯示「還沒有」＝10-Q 尚未申報。資產負債表 9 欄位：`python3 tools/bs_merge.py <代號>`（bs-raw 已由每日準備重算，不用觸發 bs-fetch），解除 `notes.unavailable` 裡的「待確認：XBRL 核對」類項目；不一致就以 SOURCES.md 指定的來源為準並在回報寫出差多少。
- **這次核對用的是年度申報（10-K、20-F、台積電／台達電年報、三星事業報告）時，同一天加做「公司簡介與營收比例」一節。**
- 完成：`python3 tools/daily.py set <代號> verified`（回到 waiting）。10-Q 還沒出來就維持 completed，**不算失敗、不加 try**，但超過 45 天仍沒有，回報提醒。

## 論點卡（有 approved 的公司才做）
每日 ③ 核對後執行 `python3 tools/thesis.py`：燈號由綠轉黃／紅，或觸及 `breakWhen`，要寫進每日回報「⑤ 未完成」一段（置頂標明）。**只有核心體質（biz，`role` 為 core）燈號轉差才置頂；估值（val）與輔助（aux）轉差只放附錄**（brief ⑧ 已分開兩行）。回報的論點卡段落分「體質核心／輔助／估值」三組。黃燈是季度警示，先觀察，不是賣出理由；只有結構性變化（`breakWhen`：ROE 連續下滑、毛利率三年累計下滑等）才寫建議。`status:"draft"` 的頁面會顯示（標草稿），但不進每日回報燈號、不改門檻，只能由 ZL 確認後改 approved。
