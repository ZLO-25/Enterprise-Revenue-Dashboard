"""台股公司的股票酬勞（sbc）：從公開資訊觀測站 IFRS 合併財報的現金流量表讀「股份基礎給付酬勞成本」（科目代號 A21900），
產生和 bs_fetch.py 同格式的提案 data/bs-raw/<代號>.json，再用 python3 tools/bs_merge.py --only sbc <代號> 合併。

  python3 tools/tw_sbc.py <原始財報資料夾（tw-raw 分支的 raw/<股票代號>/fs）> <代號>

原始財報（<年>Q<季>.html）由 tw-raw 分支的 GitHub Actions 抓，這支程式只解析、不連網。

規則（不估計、不內插）：
- 現金流量表是「年初累計」，每份報表有兩欄：本期累計、去年同期累計。兩欄都當成公司公布的數字。
  同一個累計期間在兩份報表都有值而且不一樣時，用較新的報表（重編後的數字），並在 why 記下來。
- 單季 ＝ 本期累計 − 上一季累計；第一季 ＝ 第一季累計。兩個累計都要「明確讀到」（包含報表上印的 0）才算。
- 報表上沒有這一行，不等於 0（公司可能併進「其他項目」，萬潤 2025 年報就是這樣），所以一律 null 並寫原因。
- 金額：財報單位是新台幣仟元，÷ 1000 換成百萬元（和 quarters[] 其他欄位一致）。
"""
import html, json, os, re, sys

LABELS = ("股份基礎給付酬勞成本",)
CODE = "A21900"
MOPS = "https://mopsov.twse.com.tw/server-java/t164sb01?step=1&CO_ID={co}&SYEAR={y}&SSEASON={s}&REPORT_ID=C"


def _text(c):
    return html.unescape(re.sub(r"<[^>]+>", " ", c)).replace("　", " ").strip()


def _num(c):
    t = _text(c)
    if not t:
        return None
    neg = t.startswith("(") or t.startswith("-") or 'sign="-"' in c
    t = re.sub(r"[(),\s-]", "", t)
    if not re.fullmatch(r"[\d.]+", t):
        return None
    v = float(t)
    return -v if neg else v


def read_row(b):
    """回傳 (本期累計, 去年同期累計)（仟元）；報表沒有這一行回傳 None。b 是已解碼的 HTML 文字。"""
    for row in re.findall(r"<tr[^>]*>(.*?)(?=<tr|</table)", b, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 2:
            continue
        texts = [_text(c) for c in cells]
        # 新格式：第一格是科目代號、第二格是「中文 英文」；舊格式：第一格就是中文科目
        idx = None
        for i in (0, 1):
            if i < len(texts) and any(texts[i] == l or texts[i].startswith(l + " ") for l in LABELS):
                idx = i
                break
        if idx is None:
            continue
        if idx == 1 and texts[0] not in ("", CODE):
            continue
        vals = [_num(c) for c in cells[idx + 1:]]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        return vals[0], (vals[1] if len(vals) > 1 else None)
    return None


def has_cashflow(b):
    return "營業活動之淨現金流入（流出）" in b


def build(files):
    """files: {(年, 季): HTML 文字}。回傳 (ytd, quarters)：
    ytd[(年, 季)] = {"v": 仟元, "from": "<年>Q<季>", "col": "本期"|"去年同期", "restated": 舊值或 None}
    quarters = [{"q": "3Q26", "end":…, "vals": {"sbc": 百萬元}, "prov": {...}, "why": {...}}]（每一份有現金流量表的報表一季）"""
    ytd = {}
    for (y, s) in sorted(files):          # 由舊到新：較新的報表蓋掉較舊的
        row = read_row(files[(y, s)])
        if row is None:
            continue
        for key, v, col in (((y, s), row[0], "本期"), ((y - 1, s), row[1], "去年同期")):
            if v is None:
                continue
            old = ytd.get(key)
            ytd[key] = {"v": v, "from": f"{y}Q{s}", "col": col, "restated": old["v"] if old and old["v"] != v else None}
    out = []
    for (y, s) in sorted(files):
        if not has_cashflow(files[(y, s)]):
            continue
        r = {"q": f"{s}Q{str(y)[2:]}", "end": f"{y}-{('03-31', '06-30', '09-30', '12-31')[s - 1]}", "vals": {}, "prov": {}, "why": {}}
        cur, prev = ytd.get((y, s)), (ytd.get((y, s - 1)) if s > 1 else {"v": 0.0, "from": None})
        if cur is None:
            r["why"]["sbc"] = "現金流量表沒有列「股份基礎給付酬勞成本」這一行（可能是 0，也可能併入其他項目；沒有讀到數字所以不填）"
        elif prev is None:
            r["why"]["sbc"] = "現金流量表是年初累計，上一季的累計沒有列這一行，單季算不出來"
        else:
            r["vals"]["sbc"] = round((cur["v"] - prev["v"]) / 1000, 3)
            r["prov"]["sbc"] = [{"c": f"{CODE} 股份基礎給付酬勞成本（現金流量表，{x['col']}累計欄）", "file": x["from"]} for x in (cur, prev) if x.get("from")]
            if cur.get("restated") is not None or (prev.get("restated") is not None):
                r["note"] = "累計數在較新的報表有重編，採用較新的數字"
        out.append(r)
    return ytd, out


def main():
    src, code = sys.argv[1], sys.argv[2]
    files = {}
    for f in sorted(os.listdir(src)):
        m = re.fullmatch(r"(\d{4})Q([1-4])\.html", f)
        if m:
            files[(int(m.group(1)), int(m.group(2)))] = open(os.path.join(src, f), "rb").read().decode("big5", "replace")
    ytd, Q = build(files)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "bs-raw", code + ".json")
    co = os.path.basename(os.path.dirname(os.path.abspath(src)))
    json.dump({"code": code, "source": "公開資訊觀測站 IFRS 合併財務報告的現金流量表（" + MOPS.format(co=co, y="<年>", s="<季>") + "）",
               "unit": "百萬元新台幣（財報仟元 ÷ 1000）", "ytd": {f"{y}Q{s}": v for (y, s), v in sorted(ytd.items())}, "quarters": Q},
              open(path, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    have = [r["q"] for r in Q if "sbc" in r["vals"]]
    print(code, f"{len(files)} 份報表，{len(have)} 季有單季值：", " ".join(f"{r['q']}={r['vals']['sbc']}" for r in Q if "sbc" in r["vals"]))


if __name__ == "__main__":
    main()
