"""13F 抓取與檢查的離線測試：用真實 SEC 檔案（tools/tests/fixtures/f13/）。網路不在測試裡（假的 Http）。"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import f13_fetch as F
import f13_check as C

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "f13")


def fx(name):
    with open(os.path.join(FX, name), "rb") as f:
        return f.read()


class FakeHttp:
    """url → 內容。submissions 與 index.json 由 add_filing 組出來；其他檔案指到 fixture。"""
    def __init__(self):
        self.files, self.subs = {}, {}

    def add_sub(self, cik, name, filings):
        b = {"form": [], "accessionNumber": [], "filingDate": [], "reportDate": []}
        for f in filings:
            for k, v in zip(("form", "accessionNumber", "filingDate", "reportDate"), (f[0], f[1], f[2], f[3])):
                b[k].append(v)
        self.files[f"https://data.sec.gov/submissions/CIK{cik}.json"] = json.dumps({"name": name, "filings": {"recent": b, "files": []}}).encode()

    def add_filing(self, cik, acc, primary, table=None, table_name="infotable.xml"):
        base = F.folder_url(cik, acc)
        items = [{"name": "primary_doc.xml", "type": "text.gif"}]
        self.files[base + "primary_doc.xml"] = fx(primary)
        if table:
            items.append({"name": table_name, "type": "text.gif"})
            self.files[base + table_name] = fx(table)
        self.files[base + "index.json"] = json.dumps({"directory": {"item": items}}).encode()

    def get(self, url):
        if url not in self.files:
            raise F.FetchError("no fixture " + url)
        return self.files[url]

    def json(self, url):
        return json.loads(self.get(url).decode())


class Parse(unittest.TestCase):
    def test_berkshire_merge(self):
        p = F.parse_primary(fx("berkshire__primary_doc.xml"))
        self.assertEqual((p["form"], p["period"], p["entries"], p["totalValue"]), ("13F-HR", "2026-09-30", 89, 304196581325))
        rows = F.parse_info_table(fx("berkshire__60471.xml"))
        self.assertEqual(len(rows), 89)
        hs = F.merge_rows(rows, "2026-11-14")
        self.assertLess(len(hs), 89)                       # 同 CUSIP 多列已合併
        self.assertEqual(len({(h["cusip"], h["putCall"], h["type"]) for h in hs}), len(hs))
        self.assertEqual(sum(h["value"] for h in hs), p["totalValue"])
        self.assertEqual(sum(h["value"] for h in hs), sum(r["value"] for r in rows))
        ally = [h for h in hs if h["cusip"] == "02005N100"]
        self.assertEqual(len(ally), 1)
        self.assertEqual(ally[0]["shares"], sum(r["shares"] for r in rows if r["cusip"] == "02005N100"))
        self.assertEqual(ally[0]["name"], "ALLY FINL INC")

    def test_namespaces_vary(self):   # 預設 namespace、ns1: 前綴都要讀得到
        rows = F.parse_info_table(fx("himalaya_q4__13fhciq425.xml"))
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0]["cusip"], "02079K107")
        self.assertEqual(rows[0]["type"], "SH")

    def test_entities_unescaped(self):
        rows = F.parse_info_table(fx("dj_amend__F13InfoTable_77922.xml"))
        self.assertIn("Wells Fargo & Co", [r["name"] for r in rows])

    def test_restatement_primary(self):
        for n in ("himalaya_amend__primary_doc.xml", "dj_amend__primary_doc.xml"):
            p = F.parse_primary(fx(n))
            self.assertEqual((p["form"], p["isAmendment"], p["amendType"]), ("13F-HR/A", True, "RESTATEMENT"))
        self.assertEqual(F.parse_primary(fx("himalaya_amend__primary_doc.xml"))["period"], "2025-12-31")

    def test_pershing_notice(self):
        p = F.parse_primary(fx("pershing_nt__primary_doc.xml"))
        self.assertEqual(p["form"], "13F-NT")
        self.assertEqual(p["reportType"], "13F NOTICE")
        self.assertIsNone(p["entries"])
        self.assertEqual(p["otherManagers"], [{"cik": "0002026053", "name": "PERSHING SQUARE INC.", "file": "028-25746"}])

    def test_value_units(self):
        self.assertEqual(F.scale_value(5, "2022-11-14"), 5000)        # 千元
        self.assertEqual(F.scale_value(5, "2023-01-02"), 5000)
        self.assertEqual(F.scale_value(5, "2023-01-03"), 5)           # 元
        self.assertEqual(F.scale_value(5, "2026-11-14"), 5)
        hs = F.merge_rows([{"cusip": "X", "name": "A", "cls": "C", "value": 7, "shares": 1, "type": "SH", "putCall": ""}], "2022-02-14")
        self.assertEqual(hs[0]["value"], 7000)

    def test_pick_xml_names(self):
        idx = {"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "F13InfoTable_77922.xml"}, {"name": "x-index.htm"}, {"name": "0001.txt"}]}}
        self.assertEqual(F.pick_xml_names(idx), ("primary_doc.xml", ["F13InfoTable_77922.xml"]))

    def test_prev_quarter(self):
        self.assertEqual([F.prev_quarter(x) for x in ("2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31")], ["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"])


class Pipeline(unittest.TestCase):
    def berkshire(self):
        h = FakeHttp()
        h.add_sub("0001067983", "BERKSHIRE HATHAWAY INC", [("13F-HR", "0000950123-26-000002", "2026-08-14", "2026-06-30"), ("13F-HR", "0000950123-26-000003", "2026-11-14", "2026-09-30")])
        h.add_filing("0001067983", "0000950123-26-000002", "berkshire_prev__primary_doc.xml", "berkshire_prev__56757.xml", "56757.xml")
        h.add_filing("0001067983", "0000950123-26-000003", "berkshire__primary_doc.xml", "berkshire__60471.xml", "60471.xml")
        return h

    def test_berkshire_q2_q3_changes(self):
        cfg = {"id": "berkshire", "cik": "0001067983", "name": "BERKSHIRE HATHAWAY INC"}
        d = F.build_manager(self.berkshire(), cfg, {"037833100": "aapl"})
        self.assertEqual([q["period"] for q in d["quarters"]], ["2026-09-30", "2026-06-30"])
        q3, q2 = d["quarters"]
        self.assertEqual((q3["entries"], q3["rawRows"]), (89, 89))
        self.assertEqual(q3["sumValue"], q3["totalValue"])
        self.assertEqual(q3["totalValue"], 304196581325)
        self.assertEqual(q2["totalValue"], 299253556246)
        self.assertEqual(q2["sumValue"], q2["totalValue"])
        self.assertTrue(all(h["chg"] is None for h in q2["holdings"]))     # 沒有更早一季可比
        self.assertIn("待確認", q2["chgNote"])
        rows3 = {h["cusip"]: h for h in q3["holdings"] if h["chg"] != "exit"}
        p2 = {h["cusip"]: h for h in q2["holdings"]}
        for c, h in rows3.items():
            if c in p2:
                self.assertEqual(h["prev"], p2[c]["shares"])
                want = "add" if h["shares"] > p2[c]["shares"] else "reduce" if h["shares"] < p2[c]["shares"] else "same"
                self.assertEqual(h["chg"], want, c)
            else:
                self.assertEqual(h["chg"], "new")
        exits = [h for h in q3["holdings"] if h["chg"] == "exit"]
        self.assertEqual({h["cusip"] for h in exits}, set(p2) - set(rows3))
        for h in exits:
            self.assertEqual((h["value"], h["shares"], h["prev"]), (0, 0, p2[h["cusip"]]["shares"]))
        self.assertEqual(rows3["037833100"]["code"], "aapl")
        self.assertAlmostEqual(sum(h["pct"] for h in rows3.values()), 100, places=2)
        self.assertEqual(len(d["seen"]), 2)

    def test_himalaya_restatement(self):
        h = FakeHttp()
        h.add_sub("0001709323", "Himalaya Capital Management LLC", [("13F-HR", "0001-26-000001", "2026-02-10", "2025-12-31"), ("13F-HR/A", "0001-26-000002", "2026-02-18", "2025-12-31")])
        h.add_filing("0001709323", "0001-26-000001", "himalaya_q4__primary_doc.xml", "himalaya_q4__13fhciq425.xml")
        h.add_filing("0001709323", "0001-26-000002", "himalaya_amend__primary_doc.xml", "himalaya_amend__13fhciq425v2.xml")
        d = F.build_manager(h, {"id": "himalaya", "cik": "0001709323", "name": "x"}, {})
        q = d["quarters"][0]
        self.assertTrue(q["amended"])
        self.assertEqual(q["rawRows"], 9)                      # 整份取代，不是 18
        self.assertEqual(q["amendments"][0]["type"], "RESTATEMENT")
        amend = F.merge_rows(F.parse_info_table(fx("himalaya_amend__13fhciq425v2.xml")), "2026-02-18")
        self.assertEqual({x["cusip"]: x["shares"] for x in q["holdings"]}, {x["cusip"]: x["shares"] for x in amend})
        self.assertEqual(q["acc"], "0001-26-000001")

    def test_new_holdings_amendment_adds(self):
        p = F.parse_primary(fx("dj_amend__primary_doc.xml"))
        q = {}
        rows = F.parse_info_table(fx("dj_amend__F13InfoTable_77922.xml"))
        F._apply(q, p, rows, "2026-01-10", "1", "a", "13F-HR", True)
        p2 = dict(p, amendType="NEW HOLDINGS", entries=2, totalValue=100)
        F._apply(q, p2, rows[:2], "2026-02-10", "1", "b", "13F-HR/A", False)
        self.assertEqual((len(q["_raw"]), q["entries"], q["totalValue"]), (6, 6, p["totalValue"] + 100))

    def test_dj_restatement_check_passes(self):
        h = FakeHttp()
        h.add_sub("0000783412", "DAILY JOURNAL CORP", [("13F-HR/A", "0002-25-000002", "2025-10-20", "2025-09-30")])
        h.add_filing("0000783412", "0002-25-000002", "dj_amend__primary_doc.xml", "dj_amend__F13InfoTable_77922.xml", "F13InfoTable_77922.xml")
        d = F.build_manager(h, {"id": "dailyjournal", "cik": "0000783412", "name": "x"}, {})
        q = d["quarters"][0]
        self.assertEqual((q["form"], q["rawRows"], q["entries"]), ("13F-HR/A", 4, 4))
        self.assertTrue(any("待確認" in n for n in q["notes"]))   # 沒有原始版：要報出來
        self.assertEqual(q["sumValue"], q["totalValue"])

    def test_pershing_notice_then_successor(self):
        h = FakeHttp()
        h.add_sub("0001336528", "Pershing Square Capital Management, L.P.", [("13F-NT", "0003-26-000001", "2026-11-16", "2026-09-30")])
        h.add_filing("0001336528", "0003-26-000001", "pershing_nt__primary_doc.xml")
        cfg = {"id": "pershing", "ciks": ["0001336528", "0002026053"], "name": "x"}
        h.add_sub("0002026053", "PERSHING SQUARE INC.", [])
        d = F.build_manager(h, cfg, {})
        q = d["quarters"][0]
        self.assertEqual((q["form"], q["holdingsKnown"], q["holdings"]), ("13F-NT", False, []))
        self.assertEqual(q["notice"]["by"][0]["name"], "PERSHING SQUARE INC.")
        # 接手申報人有 13F-HR → 該季用它的持股，標明來源
        h.add_sub("0002026053", "PERSHING SQUARE INC.", [("13F-HR", "0004-26-000001", "2026-11-16", "2026-09-30")])
        h.add_filing("0002026053", "0004-26-000001", "himalaya_q4__primary_doc.xml", "himalaya_q4__13fhciq425.xml")
        q = F.build_manager(h, cfg, {})["quarters"][0]
        self.assertTrue(q["holdingsKnown"])
        self.assertEqual(q["via"]["name"], "PERSHING SQUARE INC.")
        self.assertEqual(q["via"]["primaryNotice"]["form"], "13F-NT")
        # 兩邊都有 13F-HR：主 CIK 為準並報出
        h.add_sub("0001336528", "x", [("13F-HR", "0005-26-000001", "2026-11-14", "2026-09-30")])
        h.add_filing("0001336528", "0005-26-000001", "dj_amend__primary_doc.xml", "dj_amend__F13InfoTable_77922.xml", "t.xml")
        q = F.build_manager(h, cfg, {})["quarters"][0]
        self.assertEqual(q["acc"], "0005-26-000001")
        self.assertTrue(any("以主 CIK" in n for n in q["notes"]))


class Aggregate(unittest.TestCase):
    def setUp(self):
        self.cfg = {"managers": [{"id": "berkshire", "cik": "0001067983", "name": "B"}], "groups": ["g"],
                    "tracked": {"aapl": {"cusips": ["037833100"], "issuerKeys": ["APPLE INC"]}, "googl": {"cusips": ["02079K305", "02079K107"], "issuerKeys": ["ALPHABET INC"]},
                                "nvda": {"cusips": [], "issuerKeys": ["NVIDIA CORP"]}}, "notCovered": {"samsung": "韓國掛牌"}}
        tr = {c: code for code, t in self.cfg["tracked"].items() for c in t["cusips"]}
        self.doc = F.build_manager(Pipeline().berkshire(), {"id": "berkshire", "cik": "0001067983", "name": "B"}, tr)
        self.docs = {"berkshire": self.doc}

    def test_by_company(self):
        b = F.build_by_company(self.docs, self.cfg)
        self.assertEqual(b["period"], "2026-09-30")
        self.assertTrue(b["companies"]["aapl"]["cusipsKnown"])
        self.assertFalse(b["companies"]["nvda"]["cusipsKnown"])
        self.assertEqual(b["companies"]["nvda"]["managers"], [])
        g = b["companies"]["googl"]["managers"][0]
        rows = [h for h in self.doc["quarters"][0]["holdings"] if h["code"] == "googl"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(g["shares"], sum(r["shares"] for r in rows))
        self.assertEqual(g["value"], sum(r["value"] for r in rows))
        self.assertEqual(b["notCovered"], {"samsung": "韓國掛牌"})

    def test_latest(self):
        l = F.build_latest(self.docs, self.cfg)
        m = l["managers"]["berkshire"]
        self.assertEqual((m["period"], m["form"], len(m["top10"])), ("2026-09-30", "13F-HR", 10))
        self.assertEqual(m["top10"][0]["value"], max(h["value"] for h in self.doc["quarters"][0]["holdings"]))

    def test_check_clean_and_unmapped(self):
        err, todo = C.check_docs(self.cfg, self.docs)
        self.assertEqual(err, [])
        self.assertTrue(any("NVIDIA" in t for t in todo) is False)       # 持股裡沒有 NVIDIA
        cfg2 = json.loads(json.dumps(self.cfg)); cfg2["tracked"]["aapl"]["cusips"] = []
        err, todo = C.check_docs(cfg2, self.docs)
        self.assertTrue(any("037833100" in t and "不在" in t for t in todo))

    def test_check_errors(self):
        d = json.loads(json.dumps(self.doc))
        d["quarters"][0]["sumValue"] += 10 ** 9
        d["quarters"][0]["rawRows"] = 88
        cfg2 = json.loads(json.dumps(self.cfg)); cfg2["tracked"]["aapl"]["issuerKeys"] = ["ORANGE INC"]
        err, _ = C.check_docs(cfg2, {"berkshire": d})
        self.assertEqual(len(err), 3)
        self.assertTrue(all(e.startswith("✗") for e in err))

    def test_key_match_boundary(self):
        self.assertTrue(C.key_match("AXT INC", "AXT INC"))
        self.assertFalse(C.key_match("MAXT INC", "AXT INC"))


if __name__ == "__main__":
    unittest.main()
