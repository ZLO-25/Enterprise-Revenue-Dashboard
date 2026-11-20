import re,html,os,json
ann=[]
for f in sorted(os.listdir('raw/2327/mops')):
    if not f.startswith('t05st01'): continue
    b=open('raw/2327/mops/'+f,'rb').read().decode('utf-8','replace')
    t=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',b)).replace('\xa0',' '))
    for m in re.finditer(r'2327 國巨\*? (\d{3})/(\d\d)/(\d\d) (\d\d:\d\d:\d\d) (.*?)(?= 2327 國巨\*? \d{3}/| try \{|$)', t):
        ann.append((f"{int(m[1])+1911}-{m[2]}-{m[3]}", m[4], m[5].strip()))
json.dump(ann, open('work_y/ann.json','w'), ensure_ascii=False, indent=0)
print(len(ann))
