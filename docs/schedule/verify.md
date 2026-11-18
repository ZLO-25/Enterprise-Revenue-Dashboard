# 每日排程附件：核對＋論點卡

> 每日排程的附件（由 docs/schedule/core.md 指示才讀）。內容與舊版 docs/SCHEDULE_PROMPT.md 同一節一字不改，只是拆出來，安靜日不用讀。

### ③ 核對（狀態 completed 的公司）
- 等 10-Q／年報出來（看 `sec-feed.json` 的 periodic，或該公司 SOURCES.md 的核對來源），把快報數字對 XBRL／正式申報，解除 `notes.unavailable` 裡的「待確認：XBRL 核對」類項目；不一致就以 SOURCES.md 指定的來源為準並在回報寫出差多少。
- **這次核對用的是年度申報（10-K、20-F、台積電／台達電年報、三星事業報告）時，同一天加做「公司簡介與營收比例」一節。**
- 完成：`python3 tools/daily.py set <代號> verified`（回到 waiting）。10-Q 還沒出來就維持 completed，**不算失敗、不加 try**，但超過 45 天仍沒有，回報提醒。

## 論點卡（有 approved 的公司才做）
每日 ③ 核對後執行 `python3 tools/thesis.py`：燈號由綠轉黃／紅，或觸及 `breakWhen`，要寫進每日回報「⑤ 未完成」一段（置頂標明）；只看核心（role: core）指標，輔助（aux）與估值只放附錄。`warnWhen` 是季度警示（黃燈先觀察），`breakWhen` 才是結構性條件。`status:"draft"` 的不上線、不改燈號，只能由 ZL 確認後改 approved。
