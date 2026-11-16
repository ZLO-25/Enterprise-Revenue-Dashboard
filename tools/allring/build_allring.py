import json, sys
fs = json.load(open('work/fs.json'))
rd = json.load(open('work/rd.json'))['rd']
def g(f, k, i=0):
    v = fs.get(f, {}).get(k)
    return v[i] if v and len(v) > i and v[i] is not None else None
RESTATED = []
for y in range(2013, 2026):
    for q in range(1, 5):
        a, b = fs.get(f'{y}Q{q}'), fs.get(f'{y+1}Q{q}')
        if a and b and 'ocf' in a and 'ocf' in b and len(b['ocf']) > 1 and abs(a['ocf'][0] - b['ocf'][1]) > 0.5:
            RESTATED.append((f'{y}Q{q}', a['ocf'][0], b['ocf'][1])); a['ocf'][0] = b['ocf'][1]
print('restated ocf', RESTATED)
M = lambda x: None if x is None else round(x / 1000, 3)
Q = []; A = {}; unav = []
for y in range(2013, 2027):
    for q in range(1, 5):
        f = f'{y}Q{q}'
        if f not in fs: continue
        lab = f'{q}Q{y%100:02d}'
        r = {'q': lab}
        def isv(k):
            v = g(f, k)
            if q == 4:
                p = [g(f'{y}Q{j}', k) for j in (1, 2, 3)]
                if v is None or None in p: return None
                v = v - sum(p)
            return v
        def cfv(k, absent0=False):
            v = g(f, k); p = g(f'{y}Q{q-1}', k) if q > 1 else 0
            if absent0:
                v = 0 if v is None else v; p = 0 if p is None else p
            return None if v is None or p is None else v - p
        rev, gp, op, ni = isv('rev'), isv('gp'), isv('opInc'), isv('ni')
        r['rev'] = M(rev); r['gp'] = M(gp); r['gm'] = round(gp / rev * 100, 1); r['opInc'] = M(op); r['om'] = round(op / rev * 100, 1); r['ni'] = M(ni)
        if q == 4:
            r['eps'] = round(g(f, 'eps') - g(f'{y}Q3', 'eps', 2), 2)
        else:
            r['eps'] = g(f, 'eps')
        ocf = cfv('ocf'); cap = cfv('capex')
        r['ocf'] = M(ocf); r['capex'] = M(-cap) if cap is not None and cap <= 0 else None
        if r['capex'] is None: unav.append(f'待確認：{lab} 資本支出（capex）與自由現金流（fcf）：取得不動產、廠房及設備的年初累計金額 {-g(f, "capex"):,.0f} 仟元比上一季累計 {-g(f"{y}Q{q-1}", "capex"):,.0f} 仟元還少，相減會是負的資本支出；後一年報告的比較欄也是同樣金額，財報沒有說明原因（可能是科目重分類），所以不填')
        r['fcf'] = round(r['ocf'] - r['capex'], 3) if r['capex'] is not None else None; r['dps'] = None
        x = rd.get(lab)
        r['rd'] = x['rd'] if x else None; r['rdB'] = 'p' if x else None
        st, ts = g(f, 'stock'), g(f, 'treasSh')
        r['shOut'] = round(st / 10 / 1000 - (ts or 0) / 1e6, 3) if st else None
        r['dilSh'] = None; r['cash'] = M(g(f, 'cash')); r['debt'] = None
        bb = cfv('buyback', absent0=True); r['buyback'] = M(-bb) if bb is not None else None
        r['equity'] = M(g(f, 'equity')); r['pretax'] = M(isv('pretax')); r['tax'] = M(isv('tax'))
        Q.append(r)
        if q == 4:
            A[str(y)] = {'rev': M(g(f, 'rev')), 'gp': M(g(f, 'gp')), 'opInc': M(g(f, 'opInc')), 'ni': M(g(f, 'ni')), 'eps': g(f, 'eps'),
                         'ocf': M(g(f, 'ocf')), 'capex': M(-g(f, 'capex')), 'note': f'取自 {y} 年度合併財務報告（公開資訊觀測站 t164sb01）'}
            # cross-check announced annual EPS
            if x and x['eps'] and abs(float(x['eps']) * (-1 if x['loss'] else 1) - g(f, 'eps')) > 0.001: print('ANNUAL EPS MISMATCH', lab, x['eps'], g(f, 'eps'))
        elif x and x['eps']:
            ytd = g(f, 'eps', 0 if q == 1 else 2)
            if abs(float(x['eps']) - ytd) > 0.001: print('YTD EPS MISMATCH', lab, x['eps'], ytd)
json.dump({'Q': Q, 'A': A, 'unav': unav, 'restated': RESTATED}, open('work/allring_q.json', 'w'), ensure_ascii=False)
print(len(Q), Q[0]['q'], Q[-1]['q'])
for r in Q[-6:]: print(r)
