"""把一份新的公司分析存成 data/analysis/<代號>.json，舊的那份自動精簡進 history（只留季度、日期、結論）。

用法：python3 tools/analysis_save.py <代號> <新分析.json>
新分析.json 的格式見 docs/DATA_SCHEMA.md「公司分析」（不用寫 history，這支程式會接上）。
存完會跑 validate 的分析核對；沒過就不寫檔、以非 0 結束。
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate as V

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    code, src = sys.argv[1], sys.argv[2]
    new = json.load(open(src, encoding="utf8"))
    new["code"] = code
    path = os.path.join(ROOT, "data", "analysis", code + ".json")
    hist = []
    if os.path.exists(path):
        old = json.load(open(path, encoding="utf8"))
        hist = old.get("history") or []
        if (old.get("q"), old.get("date")) != (new.get("q"), new.get("date")):
            hist = [h for h in hist if h.get("q") != old.get("q")] + [{k: old.get(k) for k in ("q", "date", "verdict", "conclusion")}]
    new["history"] = [h for h in hist if h.get("q") != new.get("q")][-12:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    backup = open(path, encoding="utf8").read() if os.path.exists(path) else None
    with open(path, "w", encoding="utf8") as f:
        json.dump(new, f, ensure_ascii=False, indent=1)
        f.write("\n")
    err = []
    V.check_analysis(code, V.load(code), err)
    if err:
        if backup is None:
            os.remove(path)
        else:
            open(path, "w", encoding="utf8").write(backup)
        print("沒過，未寫入：\n  - " + "\n  - ".join(err))
        sys.exit(1)
    print(f"已寫入 data/analysis/{code}.json（{new.get('q')} {new.get('verdict')}；history {len(new['history'])} 筆）")


if __name__ == "__main__":
    main()
