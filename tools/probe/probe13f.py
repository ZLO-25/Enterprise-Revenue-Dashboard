import json,urllib.request,urllib.parse,time,re
UA="Enterprise-Revenue-Dashboard research contact@example.com"
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=60) as r: return r.read()
out=[]
for q in ["pershing square inc","pershing square"]:
    b=get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="+urllib.parse.quote(q)+"&owner=include&count=40&output=atom").decode("utf8","replace")
    out.append("SEARCH "+q+": "+" | ".join(re.findall(r"<title>([^<]+)</title>",b)[:30])+" || "+" ".join(re.findall(r"CIK=(\d+)",b)[:30]))
    out.append(b[:3000])
b=get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum=028-25746&owner=include&count=10&output=atom").decode("utf8","replace")
out.append("FILENUM: "+b[:3000])
open("probe.txt","w").write("\n".join(out))
