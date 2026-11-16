"""讀 want.txt 每一行：<種類> <參數...>，把原始回應存到 raw/。只存原文，不解析、不改數字。
種類：
  fs  <公司代號> <起年> <起季> <迄年> <迄季>   MOPS 舊版 t164sb01（IFRS 合併財報 HTML）
  url <檔名> <網址>                             任意 GET
  post <檔名> <網址> <form 字串>                任意 POST（application/x-www-form-urlencoded）
"""
import os, sys, time, urllib.request, urllib.parse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
os.makedirs("raw", exist_ok=True)


def fetch(url, data=None, name=None):
    path = os.path.join("raw", name)
    if os.path.exists(path) and os.path.getsize(path) > 3000:
        return
    for i in range(4):
        try:
            req = urllib.request.Request(url, data=data.encode() if data else None, headers={"User-Agent": UA, "Referer": "https://mopsov.twse.com.tw/mops/web/index"})
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(b)
            print("OK", name, len(b), url, flush=True)
            time.sleep(2.5)
            return
        except Exception as e:  # noqa
            print("ERR", name, i, e, url, flush=True)
            time.sleep(8 * (i + 1))
    open(path + ".err", "w").write("failed " + url)


for line in open("want.txt", encoding="utf-8"):
    p = line.split()
    if not p or p[0].startswith("#"):
        continue
    if p[0] == "fs":
        co, y0, s0, y1, s1 = p[1], *map(int, p[2:6])
        y, s = y0, s0
        while (y, s) <= (y1, s1):
            fetch(f"https://mopsov.twse.com.tw/server-java/t164sb01?step=1&CO_ID={co}&SYEAR={y}&SSEASON={s}&REPORT_ID=C", name=f"{co}/fs/{y}Q{s}.html")
            s += 1
            if s == 5:
                y, s = y + 1, 1
    elif p[0] == "url":
        fetch(p[2], name=p[1])
    elif p[0] == "post":
        fetch(p[2], data=p[3], name=p[1])
