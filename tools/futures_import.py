"""把 TradingView MCP 抓到的期貨日 K 加密成匯入檔（給 Claude 用；明文只留在本機暫存，不進 repo）。

用法：python3 tools/futures_import.py <代號 ym|nq> <TradingView 符號> <欄位格式 JSON 檔> [更多 JSON 檔…]
  JSON 檔 = mcp-tv-get-ohlcv（format=columns）的結果，至少要有 t、o、h、l、c、v 六個陣列（可多次分頁，會自動合併去重）。
輸出：data/futures/import/<代號>.tv.enc.json（用 data/futures/import.pub.pem 公鑰加密）。
之後 GitHub Actions（futures-daily）會解開、和 Yahoo 比對後才合併；比對不過就整份不採用並列待確認。
"""
import base64, datetime as dt, json, os, sys, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "data", "futures", "import.pub.pem")


def columns(obj):
    """接受 MCP 原始回應或只有欄位的物件，找出 t/o/h/l/c/v。"""
    if isinstance(obj, dict) and all(k in obj for k in "tohlcv"):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (dict, list)):
                r = columns(v) if isinstance(v, dict) else None
                if r:
                    return r
    raise SystemExit("找不到 t/o/h/l/c/v 欄位")


def combine(objs):
    rows = {}
    for o in objs:
        c = columns(o)
        for t, a, b, l, cl, v in zip(c["t"], c["o"], c["h"], c["l"], c["c"], c["v"]):
            rows[int(t)] = (a, b, l, cl, v)
    ts = sorted(rows)
    return {k: [rows[t][i] for t in ts] for i, k in enumerate("ohlcv")} | {"t": ts}


def encrypt(plain, pem):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(pem)
    k = AESGCM.generate_key(256)
    iv = os.urandom(12)
    ek = pub.encrypt(k, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return {"v": 1, "ek": base64.b64encode(ek).decode(), "iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(AESGCM(k).encrypt(iv, plain, None)).decode()}


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    code, sym, files = sys.argv[1], sys.argv[2], sys.argv[3:]
    if not os.path.exists(PUB):
        sys.exit("還沒有 data/futures/import.pub.pem：先讓 GitHub Actions（futures-daily）跑一次產生金鑰")
    data = combine([json.load(open(f)) for f in files])
    data.update(symbol=sym, fetched=dt.date.today().isoformat())
    out = os.path.join(ROOT, "data", "futures", "import", code + ".tv.enc.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    body = encrypt(zlib.compress(json.dumps(data, separators=(",", ":")).encode(), 9), open(PUB, "rb").read())
    json.dump({"code": code, "symbol": sym, "bars": len(data["t"]), "fetched": data["fetched"], **body}, open(out, "w"))
    first = dt.datetime.fromtimestamp(data["t"][0], dt.timezone.utc).date()
    print(f"已寫入 {os.path.relpath(out, ROOT)}：{len(data['t'])} 根，最早 {first}")


if __name__ == "__main__":
    main()
