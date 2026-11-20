"""執行：python -m unittest discover -s quant/tests -p 'test_*.py'
快取事故防護（2026-11-20，見 docs/QUANT.md）的靜態保證：
  1. quant/js 內所有相對 import 都帶 ?v=<版本>，而且版本和 tools/build.py 現算的 quant_ver() 一致（沒跑 build.py 就會失敗）
  2. quant/js/*.js 全部列在 loader.js 的 FILES（載入失敗自動復原要重抓的清單）；清單裡的檔案都真的存在
  3. 版本號對 ?v= 不敏感（否則 build 每次結果都不同）"""
import re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402

JS = sorted((ROOT / "quant" / "js").glob("*.js"))
# 任何相對路徑的 import／from／import()，不管帶不帶 ?v=
REL = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*)(["'])(\.{1,2}/[^"']+)\1""")


class CacheHealTest(unittest.TestCase):
    def test_imports_versioned(self):
        qv = build.quant_ver()
        found = 0
        for f in JS:
            for m in REL.finditer(f.read_text(encoding="utf8")):
                found += 1
                self.assertTrue(m.group(2).endswith(f".js?v={qv}"), f"{f.name}: import {m.group(2)} 沒帶 ?v={qv}（改了 quant/ 要先跑 python3 tools/build.py）")
        self.assertGreater(found, 0)

    def test_loader_file_list(self):
        src = (ROOT / "quant" / "loader.js").read_text(encoding="utf8")
        listed = set(re.findall(r'"([\w./-]+\.(?:js|css|html))"', src[src.index("var FILES"):src.index("var HEAL_KEY")]))
        want = {"js/" + f.name for f in JS} | {"loader.js", "view.html", "quant.css", "rates.css"}
        self.assertEqual(want - listed, set(), "loader.js 的 FILES 漏了檔案")
        for f in listed:
            self.assertTrue((ROOT / "quant" / f).exists(), f"FILES 列了不存在的檔案 {f}")

    def test_version_ignores_import_query(self):
        raw = b'import { a } from "./x.js?v=deadbeef";\nimport("./y.js");'
        self.assertEqual(build._quant_js_norm(raw), b'import { a } from "./x.js";\nimport("./y.js");')


if __name__ == "__main__":
    unittest.main()
