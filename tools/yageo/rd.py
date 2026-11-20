"""國巨 2327：從重大訊息主旨找每一季第一次公開財報（含 EPS）的日期 rd。
取「營運成果」與「合併財務報告業經提報董事會通過」兩種公告中最早的一則。"""
import re, json
cn = {'一': 1, '二': 2, '三': 3, '四': 4}
ann = json.load(open('work_y/ann.json'))
out = {}
for d, tm, s in ann:
    if '子公司' in s or '受邀' in s or '召開日期' in s or '修正' in s or '更正' in s: continue
    if not ('營運成果' in s or ('合併財務報告' in s and '董事會通過' in s)): continue
    m = re.search(r'(\d{3,4})\s*年(?:度)?\s*第\s*([一二三四1-4])\s*季', s)
    if not m: print('SKIP', d, s); continue
    y = int(m[1]); y = y + 1911 if y < 1911 else y
    q = cn.get(m[2]) or int(m[2])
    key = f'{q}Q{y % 100:02d}'
    kind = '營運成果' if '營運成果' in s else '董事會通過'
    if key not in out or d < out[key]['rd']:
        out[key] = {'rd': d, 'tm': tm, 'kind': kind, 's': s}
json.dump(out, open('work_y/rd.json', 'w'), ensure_ascii=False, indent=0)
for k, v in sorted(out.items(), key=lambda kv: kv[1]['rd']): print(k, v['rd'], v['kind'], v['s'][:50])
