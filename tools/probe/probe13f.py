import json,urllib.request,time,os,re
UA="Enterprise-Revenue-Dashboard research contact@example.com"
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=60) as r: return r.read()
os.makedirs("fx",exist_ok=True)
S=[("berkshire","1067983","0001193125-26-463399"),("berkshire_prev","1067983","0001193125-26-352200"),("pershing_nt","1336528","0001172661-26-005462"),("himalaya_amend","1709323","0002043585-26-000012"),("himalaya_q4","1709323","0002043585-26-000011"),("dj_amend","783412","0001437749-25-030873")]
log=[]
for name,cik,acc in S:
    base=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-','')}/"
    idx=json.loads(get(base+"index.json"))
    files=[i["name"] for i in idx["directory"]["item"]]
    log.append(f"{name}: {files}")
    for f in files:
        if f.endswith(".xml"):
            open(f"fx/{name}__{f}","wb").write(get(base+f)); time.sleep(0.2)
open("probe.txt","w").write("\n".join(log))
