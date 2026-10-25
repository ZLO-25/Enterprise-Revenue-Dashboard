# 新增公司的 Prompt 模板

把下面整段複製給 Claude，**只要填第一段的 4 個欄位**（公司名稱必填，其餘可留空讓 Claude 查）。其餘文字不用改。

---

```
請在「企業財報追蹤板」加入一家新公司。

公司名稱：＿＿＿＿＿＿（例：輝達）
股票代號／交易所：＿＿＿＿（例：NVDA／Nasdaq；可留空由你查）
期間：＿＿＿＿（例：2019 年起；留空＝公司公開財報可取得的最早一季）
公司專屬指標（選填）：＿＿＿＿（例：資料中心營收拆分、客戶數；留空＝你依財報判斷）

## 專案
- GitHub repo：ZLO-25/Enterprise-Revenue-Dashboard（main 分支，GitHub Pages 從根目錄發佈）
- 先用 add_repo（owner ZLO-25、repo Enterprise-Revenue-Dashboard、access push）附加 repo 並 clone。
- 讀這三份文件再動手，照著做：docs/ADDING_A_COMPANY.md（流程）、docs/DATA_SCHEMA.md（資料格式）、companies/pltr/SOURCES.md（範例）。
- 全程用繁體中文；先用你自己的話重述要加哪家公司、哪個交易所、幣別、公布頻率、哪些專屬指標，再開始。會影響做法的問題一次問完；能用合理預設就直接做，最後告訴我選了什麼。

## 步驟
1. 腳手架：python3 tools/new_company.py <代號> --name <中文名> --name-en <英文名> --ticker <代號> --exchange "<交易所 代號>" --currency <幣別>
   （代號用小寫英數字，同時是網址路徑；不要手動建檔。）
2. 寫 companies/<代號>/SOURCES.md：來源依可信度排序（主管機關申報文件 → 公司 IR → 法說會 → 可信媒體只用於事件）、欄位定義與單位、第四季推算方式、核對規則、每週更新步驟、已知缺口。要寫到沒看過這個專案的人也能照做，因為每週排程會照這份執行。
3. 蒐集資料填進 data/<代號>.json（schema v1）：
   - 共用欄位每季都要有：rev、gm、om、eps 不能是 null；gp、opInc、ni、ocf、capex、fcf、dps 取不到填 null，不要估計。
   - 單位：美股用「百萬美元」、台股用「百萬元新台幣」（或在 company.unit 寫明）；每股用美元／元。
   - 第四季 = 全年 − 前三季累計（EPS 除外，取公司公布的 Q4）。
   - annual 只放公司公布的全年數字；guidance 用 items[] 形式；events 放下一個公布日（公司未公告的加 est:1）；waterfall 換成最新一季；milestones 列上市、重大產品、合約、併購、指數納入（只有媒體報導的加 unc:1、note 以「待確定：」開頭）；sources 列頁面要顯示的來源連結；notes.unavailable 列取不到的欄位。
   - 有分部營收就放 segments（分部加總＝營收）；公司專屬指標放 extra（keys 指定哪些要畫圖）。
4. 核對：python3 tools/validate.py <代號>。沒過就修資料，不要放寬核對。需要公司專屬核對（例：非 GAAP 數字對照公司全年公布值）再加進 tools/validate.py 的 CHECKS。
5. companies.json 把這家公司的 enabled 改成 true，補 primarySource {n, url}；python3 tools/validate.py && python3 tools/build.py。
6. 用無頭瀏覽器（Playwright）開首頁與 /<代號>/：桌機 1280、手機 390、深色模式；沒有 JavaScript 錯誤、沒有水平捲動、沒有 undefined／NaN。容器的 curl 多半被擋，讀網頁用 WebFetch／WebSearch；Chart.js 在 repo 的 assets/vendor/ 有本地副本。
7. commit（繁體中文訊息，例「加入輝達（NVDA）財報追蹤板」）、git push -u origin main。
8. 更新合併版 Artifact：先用 Artifact 工具 read companies.json 的 site.artifact 網址，再 publish dist/artifacts/all.html 到同一個 url。不要建立新的 Artifact。
9. 不要動 assets/、tools/build.py、其他公司的檔案與任何排程；排程下週一會自動把新公司納入（它只看 companies.json 的 enabled）。

## 最後回報（繁體中文，先用自己的話重述目標，多用 ASCII 圖）
- 網站網址（首頁與 /<代號>/）、Artifact 是否更新成功
- 資料涵蓋期間、單位、資料來源連結
- 取不到的欄位與原因、選了哪些預設
- 用小 ASCII 表列出最新一季與近四季的營收、毛利率、營益率、EPS、自由現金流
- 下一個公布日，以及下一次排程（週一 08:00 台北）會做什麼
```

---

## 這份模板為什麼這樣設計

```
你只填：公司名稱（＋代號／期間／專屬指標，可留空）
            │
            ▼
Claude 照固定流程：腳手架 → SOURCES.md → 填資料 → 驗證 → 建置 → 瀏覽器檢查 → push → Artifact
            │
            ▼
排程下週一自動納入（只看 companies.json 的 enabled）
```

- **共用程式不用改**：資料符合 v1 就直接用通用頁面 `templates/generic.frag.html`，首頁卡片、記分板、比較圖、長期指標自動納入。
- **錯不了的地方交給程式**：`tools/validate.py` 檢查設定完整、毛利率與金額自洽、四季＝全年、分部加總、損益拆解加總、財測區間；沒過就不發佈。
- **人要判斷的只有來源與口徑**：寫在 `SOURCES.md`，排程每週照做。
