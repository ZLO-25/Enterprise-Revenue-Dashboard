import json, sys
sys.path.insert(0, '/home/claude/work')
d = json.load(open('work/fs.json'))
def g(k, f, i=0):
    v = d.get(f, {}).get(k)
    return v[i] if v and len(v) > i else None
Q = []
years = sorted({k[:4] for k in d})
for y in years:
    for q in range(1, 5):
        f = f'{y}Q{q}'
        if f not in d: continue
        r = {'q': f'{q}Q{y[2:]}', 'f': f}
        for k in ['rev', 'gp', 'opInc', 'ni', 'pretax', 'tax', 'cogs', 'opex', 'nonop', 'nci', 'niAll']:
            v = g(k, f)
            if q == 4:
                prev = [g(k, f'{y}Q{j}') for j in (1, 2, 3)]
                v = None if v is None or None in prev else v - sum(prev)
            r[k] = v
        # EPS
        e = g('eps', f)
        if q == 4:
            # 9M cumulative EPS = Q3 file index 2 (cumulative column)
            e9 = g('eps', f'{y}Q3', 2)
            r['eps_annual'] = e; r['eps9m'] = e9
            e = None if e is None or e9 is None else round(e - e9, 2)
        r['eps'] = e
        for k in ['ocf', 'capex']:
            v = g(k, f); p = g(k, f'{y}Q{q-1}') if q > 1 else 0
            r[k] = None if v is None or p is None else v - p
        for k in ['cash', 'equity', 'stock', 'stb', 'cltd', 'bond', 'ltb', 'bondCur']:
            r[k] = g(k, f)
        Q.append(r)
json.dump(Q, open('work/q.json', 'w'), ensure_ascii=False, indent=0)
for r in Q:
    gm = r['gp'] / r['rev'] * 100 if r['rev'] else None
    om = r['opInc'] / r['rev'] * 100 if r['rev'] else None
    print(r['q'], r['rev'], f"{gm:.1f}" if gm else None, f"{om:.1f}" if om else None, r['ni'], r['eps'], r['ocf'], r['capex'], r.get('eps_annual'), r.get('eps9m'))
