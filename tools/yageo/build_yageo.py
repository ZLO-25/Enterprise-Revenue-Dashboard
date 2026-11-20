"""國巨 2327：work_y/fs.json（parse.py）＋ work_y/rd.json（rd.py）＋ 第四季新聞稿 EPS → work_y/yageo_q.json
EPS 與股數一律換成今天的股數基準（股票股利、面額變更；現金減資公司不追溯，這裡也不調）。"""
import json, re, html, os
fs = json.load(open('work_y/fs.json'))
rd = json.load(open('work_y/rd.json'))
# 股數基準事件：除權（換股後新股上市）日、比例。來源：重大訊息明細（見 SOURCES.md）
# 股數基準事件（來源：重大訊息明細，見 SOURCES.md）
# kind b＝股票股利／面額變更（IAS 33 追溯調整：公布日 rd 之後才發生的要除）
# kind c＝現金減資（公司不追溯；EPS 的加權股數從減資基準日／變更登記日起改變，那一季是混合的）
# (EPS 生效日, 股本生效日, 種類, 比例, 說明)
# kind b＝股票股利／面額變更（IAS 33 追溯調整：公布日 rd 之後才發生的才要除）
# kind c＝現金減資（公司不追溯；EPS 生效日＝公司加權股數開始改變的日子，依當季 EPS 判斷，見 SOURCES.md）
EVENTS = [("2013-08-09", "2013-08-09", "c", 1543715867 / 2205308382, "2013 年現金減資約 30%（每仟股換發約 700 股，2013-08-09 完成變更登記，新股 2013-09-18 上市）"),
          ("2014-10-09", "2014-09-05", "c", 0.30256942478, "2014 年現金減資約 70%（每仟股換發約 302.569 股，2014-09-05 完成變更登記；3Q14 EPS 的加權股數仍以減資前股數為主，新股 2014-10-09 上市）"),
          ("2016-07-12", "2016-06-28", "c", 0.80045445859, "2016 年現金減資約 20%（每仟股換發約 800.454 股，2016-06-28 主管機關核准、2016-07-12 完成變更登記）"),
          ("2017-07-06", "2017-07-06", "c", 0.69878452861, "2017 年現金減資約 30%（每仟股換發約 698.785 股，2017-07-06 完成變更登記，新股 2017-08-18 上市）"),
          ("2018-07-09", "2018-07-09", "b", 1.198116669, "2018 年盈餘轉增資，每股配發股票股利 1.98116669 元（每仟股 198.116669 股），除權交易日 2018-07-09"),
          ("2022-10-20", "2022-09-15", "c", 0.79592497057, "2022 年現金減資約 20%（每仟股換發約 795.925 股，2022-09-15 完成變更登記；3Q22 EPS 仍以減資前股數計算，新股約 2022-10-20 上市）"),
          ("2024-08-15", "2024-08-15", "b", 1.194836497, "2024 年盈餘轉增資，每仟股無償配發 194.836497 股（因股本變動由 200 股調整），除權交易日 2024-08-15"),
          ("2025-08-25", "2025-08-25", "b", 4.0, "股票面額由 10 元變更為 2.5 元，每 1 股換發 4 股，新股 2025-08-25 上市")]
def factor(rd_date, qend):  # EPS 要除的倍數
    f = 1.0
    for ex, sh, kind, r, _ in EVENTS:
        if (kind == "b" and rd_date < ex) or (kind == "c" and qend < ex): f *= r
    return f
def shfactor(qend):  # 期末股數換成今天的基準
    f = 1.0
    for ex, sh, kind, r, _ in EVENTS:
        if qend < sh: f *= r
    return f
QEND = {1: '03-31', 2: '06-30', 3: '09-30', 4: '12-31'}
# 第四季單季 EPS：公司「第四季（暨全年度）營運成果」重大訊息
Q4PR = {}
for f in sorted(os.listdir('raw/2327/mops')):
    if not f.startswith('det_'): continue
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', open('raw/2327/mops/' + f, 'rb').read().decode('utf-8', 'replace'))))
    if not re.search(r'第\s*(4|四)\s*季', t[:3000] + t): continue
    m = re.search(r'單季每股稅後盈餘(?:為)?\s*NT\$\s*([\d.]+)\s*元', t)
    y = re.search(r'主旨 (?:公告本公司|國巨公司公布)\s*(\d{3,4})\s*年', t)
    if m and y:
        yy = int(y[1]); yy = yy + 1911 if yy < 1911 else yy
        Q4PR[yy] = (float(m[1]), f)
def g(f, k, i=0):
    v = fs.get(f, {}).get(k)
    return v[i] if v and len(v) > i and v[i] is not None else None
M = lambda x: None if x is None else round(x / 1000, 3)
Q, A, unav, log = [], {}, [], []
for y in range(2013, 2027):
    for q in range(1, 5):
        f = f'{y}Q{q}'
        if f not in fs: continue
        lab = f'{q}Q{y % 100:02d}'
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
        r = {'q': lab}
        rev, gp, op, ni = isv('rev'), isv('gp'), isv('opInc'), isv('ni')
        r['rev'] = M(rev); r['gp'] = M(gp); r['gm'] = round(gp / rev * 100, 1); r['opInc'] = M(op); r['om'] = round(op / rev * 100, 1); r['ni'] = M(ni)
        x = rd.get(lab)
        r_rd = x['rd'] if x else None
        if q == 4:
            calc = round(g(f, 'eps') - g(f'{y}Q3', 'eps', 2), 2)
            pr = Q4PR.get(y)
            if pr:
                e0 = pr[0]
                if abs(pr[0] - calc) > 0.015: log.append(f'{lab} Q4 EPS 新聞稿 {pr[0]} vs 全年−前三季 {calc}')
            else:
                e0 = calc; log.append(f'{lab} Q4 EPS 無新聞稿，用全年−前三季 {calc}')
        else:
            e0 = g(f, 'eps')
        qe = f'{y}-{QEND[q]}'
        fac = factor(r_rd, qe) if r_rd else None
        r['eps'] = round(e0 / fac, 4) if fac else None
        r['epsOrig'] = e0
        ocf = cfv('ocf'); cap = cfv('capex')
        r['ocf'] = M(ocf); r['capex'] = M(-cap) if cap is not None and cap <= 0 else None
        if r['capex'] is None: unav.append(f'待確認：{lab} 資本支出（capex）：累計金額相減為負，不填')
        r['fcf'] = round(r['ocf'] - r['capex'], 3) if r['capex'] is not None else None
        r['dps'] = None
        r['rd'] = r_rd; r['rdB'] = 'p' if r_rd else None
        par = 2.5 if f >= '2025Q3' else 10.0
        st, ts = g(f, 'stock'), g(f, 'treasSh')
        r['shOut'] = round((st * 1000 / par - (ts or 0)) * shfactor(qe) / 1e6, 3) if st else None
        r['dilSh'] = None
        r['cash'] = M(g(f, 'cash'))
        dparts = [g(f, k) or 0 for k in ('stb', 'cp', 'cltd', 'bond', 'ltb')]
        r['debt'] = M(sum(dparts))
        bb = cfv('buyback', absent0=True); r['buyback'] = M(-bb) if bb is not None else None
        r['equity'] = M(g(f, 'equity')); r['pretax'] = M(isv('pretax')); r['tax'] = M(isv('tax'))
        Q.append(r)
        if q == 4:
            A[str(y)] = {'rev': M(g(f, 'rev')), 'gp': M(g(f, 'gp')), 'opInc': M(g(f, 'opInc')), 'ni': M(g(f, 'ni')),
                         'eps': round(g(f, 'eps') / factor(r_rd, qe), 4), 'ocf': M(g(f, 'ocf')), 'capex': M(-g(f, 'capex')),
                         'note': f'取自 {y} 年度合併財務報告（公開資訊觀測站 t164sb01）；EPS 原始值 {g(f, "eps")} 元' + (f'，已除以 {factor(r_rd, qe):.6g} 換成今天的股數基準' if factor(r_rd, qe) != 1 else '')}
json.dump({'Q': Q, 'A': A, 'unav': unav, 'log': log, 'q4pr': Q4PR, 'events': EVENTS}, open('work_y/yageo_q.json', 'w'), ensure_ascii=False)
print('\n'.join(log)); print(len(Q), Q[0]['q'], Q[-1]['q'], unav)
for r in Q[-5:] + Q[:2]: print(r)
