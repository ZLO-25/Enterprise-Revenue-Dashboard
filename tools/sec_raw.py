import json, os, re, time, gzip, urllib.request, urllib.error
from html.parser import HTMLParser
UA = "Enterprise-Revenue-Dashboard research contact@example.com"
def get(url, raw=False):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
                time.sleep(0.15)
                return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(3 * (i + 1))
        except Exception as e:
            print("err", url, e); time.sleep(3 * (i + 1))
    return None
class T(HTMLParser):
    def __init__(s):
        super().__init__(); s.out=[]; s.cell=[]; s.row=[]; s.intable=0; s.skip=0
    def handle_starttag(s, t, a):
        if t in ("script","style"): s.skip+=1
        if t=="table": s.intable+=1
        if t in ("tr",): s.row=[]
        if t in ("td","th"): s.cell=[]
        if t in ("br","p","div") and not s.intable: s.out.append("\n")
    def handle_endtag(s, t):
        if t in ("script","style"): s.skip-=1
        if t in ("td","th"):
            c=" ".join("".join(s.cell).split())
            if c: s.row.append(c)
            s.cell=[]
        if t=="tr":
            if s.row: s.out.append("\n" + " | ".join(s.row))
            s.row=[]
        if t=="table": s.intable-=1; s.out.append("\n")
    def handle_data(s, d):
        if s.skip: return
        if s.intable: s.cell.append(d)
        else: s.out.append(d)
def text(html):
    p=T(); p.feed(html.decode("utf-8","replace")); t="".join(p.out)
    t=re.sub(r"[ \t\xa0]+"," ",t); t=re.sub(r"\n\s*\n+","\n",t); return t
EXTRA_SAMEDAY=os.environ.get("SAMEDAY","1")=="1"
want=[l.split() for l in open("want.txt") if l.strip() and not l.startswith("#")]
for code, cik in want:
    d=f"raw/{code}"; os.makedirs(d+"/pr", exist_ok=True)
    cf=get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    if cf: json.dump(cf, open(d+"/companyfacts.json","w"))
    sub=get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    rows=[]
    def add(f):
        keys=list(f.keys())
        for i in range(len(f["accessionNumber"])):
            rows.append({k:f[k][i] for k in keys})
    add(sub["filings"]["recent"])
    for x in sub["filings"].get("files",[]):
        f=get("https://data.sec.gov/submissions/"+x["name"]);
        if f: add(f)
    keep=[r for r in rows if r["form"] in ("10-Q","10-K","10-Q/A","10-K/A","8-K","8-K/A","S-1","424B4","10-KT")]
    json.dump(keep, open(d+"/filings.json","w"), indent=0)
    for r in keep:
        q_days={x["filingDate"] for x in keep if x["form"] in ("10-Q","10-K")}
        if not r["form"].startswith("8-K") or not ("2.02" in (r.get("items") or "") or (r["filingDate"] in q_days and EXTRA_SAMEDAY)): continue
        acc=r["accessionNumber"].replace("-","")
        fn=f"{d}/pr/{r['filingDate']}_{acc}.txt"
        if os.path.exists(fn): continue
        idx=get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json")
        if not idx: continue
        items=[i["name"] for i in idx["directory"]["item"]]
        ex=[n for n in items if re.search(r"ex.?99.?0?1", n, re.I) and n.lower().endswith((".htm",".html",".txt"))]
        if not ex: ex=[n for n in items if re.search(r"99", n) and n.lower().endswith((".htm",".html")) and "index" not in n]
        if not ex: ex=[n for n in items if re.search(r"earning|release|pressrel", n, re.I) and n.lower().endswith((".htm",".html")) and "index" not in n]
        if not ex: print("no ex99", code, acc, items); continue
        b=get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{ex[0]}", raw=True)
        if b: open(fn,"w").write(f"SOURCE https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{ex[0]}\n"+text(b))
    print(code, "done", len(keep))
