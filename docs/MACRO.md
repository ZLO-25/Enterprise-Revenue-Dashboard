# 總經儀表板（macro/）

目標：個股頁回答「這家公司好不好、貴不貴」，這一頁回答「現在整體景氣在循環的哪一段」。
指標清單照愛榭克（Izaax）《景氣循環投資》書裡用到的美國經濟數據整理，再加上台灣景氣燈號與「AI 資本支出鏈」。

```
data/macro/config.json（指標清單、四階段對照表、外部連結；Claude 維護）
        │
        ├─▶ GitHub Actions：macro-weekly（台北週六、週三清晨；不經過 Claude）
        │       tools/macro_fetch.py
        │         ├ 美國：FRED 公開 CSV（免金鑰）
        │         └ 台灣：政府資料開放平臺的國發會官方檔（景氣指標及燈號 6099、採購經理人指數 6100）
        │       └─▶ data/macro/latest.json（只有 Actions 會寫；年增率與方向燈都在這裡算好）
        │
        └─▶ tools/build.py
                ├ tools/capex_chain.py：用各公司財報加總「AI 資本支出鏈」（建置時算，不存檔）
                └─▶ macro/index.html（templates/macro.frag.html；打開頁面時才讀 latest.json，所以每週更新不必重建網站）
```

## 資料誠實

- 數字只由 Actions 寫入，Claude 不手填、不修改 `data/macro/latest.json`。
- 某條序列抓不到：沿用上一次的資料，並在 `unavailable` 寫「待確認：」；從沒抓到過就不顯示。不估計、不內插。
- 沒有免費官方資料檔的指標（美國 ISM、經濟諮商局消費者信心、巴菲特指標與 Shiller 本益比）不抓，只在「外部網站」給連結。
- 書的內容來自讀者筆記，不是原書原文：頁面一律標「整理，不是原話」，不用引號假裝引述。筆記連結在 `config.json` 的 `about.notes`。
- 這一頁**不判定現在是哪個階段**，只把數據和書裡的判讀並排。

## 內容分哪幾種

| 標籤 | 意思 | 例子 |
|---|---|---|
| 書面 | 官方統計或公司財報的數字 | 每一列的最新值、台灣燈號、各公司資本支出 |
| 公式 | 用書面數字照固定公式算的 | 年增率、方向燈、四家資本支出合計 |
| 整理，不是原話 | 讀者筆記記錄的書中判讀 | 「書裡怎麼看」、四個階段對照表 |
| 觀點 | Claude 的說明 | 「怎麼讀」 |

## 方向燈（唯一計算處：`tools/macro_fetch.py` 的 `stats()`）

```
半年變動 = 最新值 − 半年前的值（月資料往前 6 筆、季資料往前 2 筆）
平常幅度 = 過去 10 年每一個半年變動的 MAD × 1.4826（用中位數算，不怕 2020 年疫情那種極端值）
z = 半年變動 ÷ 平常幅度
    z 往壞的方向 ≥ 1 → 轉差；往好的方向 ≥ 1 → 轉好；其餘 → 持平
```

- 「壞的方向」寫在每條指標的 `bad`（`up`／`down`）；空白代表沒有固定好壞方向（利率、油價、美元、儲蓄率…），不亮燈。
- 方向燈只說「最近半年明顯在變」，不是買賣訊號。門檻（1 倍）是分析師草稿，ZL 可改。

## 怎麼改

| 想做的事 | 改哪裡 |
|---|---|
| 加／刪一條美國指標 | `data/macro/config.json` 的 `groups[].series`（`fred` 填 FRED 代號）。push 後 macro-weekly 會自動重抓 |
| 改顯示單位（千人 → 萬人） | 同一條的 `scale`、`showUnit`、`showDigits`（存檔仍是原始單位） |
| 改四階段對照表 | `phases[].checks`（`keys` 必須是存在的指標） |
| 加外部連結 | `links[]` |
| 改資本支出鏈的公司 | `chain.buyers`／`chain.suppliers`（買方的季末必須在 3／6／9／12 月） |
| 檢查連結有沒有失效、台灣檔案格式 | Actions 手動執行 macro-weekly，勾 probe（404 才要修；403 多半是網站擋機器人） |

測試：`python3 -m unittest discover -s tools/tests -p 'test_macro.py'`、`-p 'test_capex_chain.py'`。
