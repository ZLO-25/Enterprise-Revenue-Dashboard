import json,urllib.request,urllib.parse,time
UA="Enterprise-Revenue-Dashboard research contact@example.com"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=30) as r: return r.read()
    except Exception as e: return ("ERR %s"%e).encode()
C={"berkshire":"0001067983","himalaya":"0001709323","hh":"0001759760","dailyjournal":"0000783412","akre":"0001112520","fundsmith":"0001569205","markel":"0001096343","baillie":"0001088875","pershing":"0001336528"}
out=[]
for k,c in C.items():
    b=get(f"https://data.sec.gov/submissions/CIK{c}.json")
    try:
        d=json.loads(b); r=d["filings"]["recent"]
        f=[(r["filingDate"][i],r["form"][i],r["reportDate"][i],r["accessionNumber"][i],r["primaryDocument"][i]) for i in range(len(r["form"])) if r["form"][i].startswith("13F")][:6]
        out.append(f"{k} {c} {d['name']} ->\n  "+"\n  ".join(map(str,f)))
    except Exception as e: out.append(f"{k} {c} FAIL {b[:200]}")
    time.sleep(0.3)
for q in ["himalaya capital","h&h international","akre capital","fundsmith","baillie gifford","pershing square capital","daily journal","markel"]:
    b=get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="+urllib.parse.quote(q)+"&type=13F-HR&dateb=&owner=include&count=20&output=atom").decode("utf8","replace")
    import re
    out.append("SEARCH "+q+": "+"; ".join(re.findall(r"<title>([^<]+)</title>",b)[:8])+" | "+" ".join(re.findall(r"CIK=(\d+)",b)[:8]))
# sample infotable for berkshire latest
open("probe.txt","w").write("\n".join(out))
