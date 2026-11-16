import re, html, os, json
cn = {'一':1,'二':2,'三':3,'四':4}
out = {}; ann = []
for f in sorted(os.listdir('raw/6187/mops')):
    if not f.startswith('t05st01'): continue
    b = open('raw/6187/mops/' + f, 'rb').read().decode('utf-8', 'replace')
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', b)).replace('\xa0', ' '))
    for m in re.finditer(r'6187 萬潤 (\d{3})/(\d\d)/(\d\d) (\d\d:\d\d:\d\d) (.*?)(?= 6187 萬潤 \d{3}/| try \{)', t):
        d = f"{int(m[1])+1911}-{m[2]}-{m[3]}"; s = m[5].strip()
        ann.append((d, m[4], s))
for d, tm, s in ann:
    if '董事會通過' not in s or not ('財務報' in s or '財報' in s) or '酬勞' in s: continue
    if '更正' in s: print('CORR', d, s)
    q = None
    m = re.search(r'第([一二三四1-4])季', s)
    if m: q = cn.get(m[1], None) or int(m[1])
    else: q = 4
    # year: roc digits in 一○二 or 102
    ym = re.search(r'([一二三四五六七八九○〇零0-9]{3})年', s)
    m2 = re.search(r'([1-4])季', s)
    if m2: q = int(m2[1])
    if not ym: print('NOYEAR', d, s); continue
    yy = ym[1]
    digits = {'○':0,'〇':0,'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    y = int(''.join(str(digits.get(c, c)) for c in yy)) + 1911
    eps = re.search(r'(每股[^0-9]*?)(-?[\d.]+)元', s)
    key = f"{q}Q{y%100:02d}"
    if key in out: print('DUP', key, d, s, '| first', out[key]); continue
    out[key] = {'rd': d, 'tm': tm, 'eps': eps[2] if eps else None, 'loss': ('淨損' in s or '虧損' in s), 's': s}
json.dump({'rd': out, 'ann': ann}, open('work/rd.json', 'w'), ensure_ascii=False, indent=0)
for k, v in sorted(out.items(), key=lambda kv: kv[1]['rd']): print(k, v['rd'], v['eps'], v['s'][:70])
