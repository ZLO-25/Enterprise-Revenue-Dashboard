import re, html, json, sys, os
LAB = {
 'rev': ['營業收入合計'], 'cogs': ['營業成本合計'], 'gp': ['營業毛利（毛損）淨額'], 'opex': ['營業費用合計'],
 'opInc': ['營業利益（損失）'], 'nonop': ['營業外收入及支出合計'], 'pretax': ['繼續營業單位稅前淨利（淨損）', '稅前淨利（淨損）'],
 'tax': ['所得稅費用（利益）合計', '所得稅費用（利益）'], 'niAll': ['本期淨利（淨損）'], 'ni': ['母公司業主（淨利／損）', '母公司業主（淨利∕損）'],
 'nci': ['非控制權益（淨利／損）', '非控制權益（淨利∕損）'], 'eps': ['基本每股盈餘合計'], 'dilEps': ['稀釋每股盈餘合計'],
 'ocf': ['營業活動之淨現金流入（流出）'], 'capex': ['取得不動產、廠房及設備'],
 'cash': ['現金及約當現金合計', '現金及約當現金總額', '現金及約當現金'], 'equity': ['歸屬於母公司業主之權益合計'], 'stock': ['普通股股本', '普通股股本合計'],
 'stb': ['短期借款合計', '短期借款'], 'cltd': ['一年或一營業週期內到期長期負債合計', '一年或一營業週期內到期長期負債'],
 'bond': ['應付公司債合計', '應付公司債'], 'ltb': ['長期借款合計', '長期借款'], 'bondCur': ['一年或一營業週期內到期或執行賣回權公司債'],
 'treas': ['庫藏股票', '庫藏股票合計'], 'treasSh': ['母公司暨子公司所持有之母公司庫藏股股數（單位：股）'], 'buyback': ['庫藏股票買回成本'],
}

def cell_text(c):
    m = re.search(r'<span class="zh">(.*?)</span>', c, re.S)
    t = m.group(1) if m else c
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    return t.replace('　', '').strip()

def num(c):
    raw = html.unescape(re.sub(r'<[^>]+>', ' ', c))
    neg_attr = 'sign="-"' in c
    t = raw.strip()
    if not t: return None
    neg = t.startswith('(') or t.startswith('-') or neg_attr
    t = t.replace('(', '').replace(')', '').replace(',', '').replace('-', '').strip()
    if not re.fullmatch(r'[\d.]+', t): return None
    v = float(t)
    return -v if neg else v

def parse(path):
    b = open(path, 'rb').read().decode('big5', 'replace')
    out = {}
    sec = None
    for row in re.findall(r'<tr[^>]*>(.*?)(?=<tr|</table)', b, re.S):
        if '現金流量表' in row and '<th' in row: sec = 'cf'
        elif '綜合損益表' in row and '<th' in row: sec = 'is'
        elif '權益變動表' in row and '<th' in row: sec = 'eq'
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
        if len(cells) < 2: continue
        if re.fullmatch(r'\s*[A-Z0-9]{4,6}\s*', re.sub(r'<[^>]+>', '', cells[0]) or 'x') or re.sub(r'<[^>]+>', '', cells[0]).strip() == '':
            lab, rest = cell_text(cells[1]), cells[2:]
        else:
            lab, rest = cell_text(cells[0]), cells[1:]
        vals = [num(c) for c in rest]
        for k, names in LAB.items():
            if lab in names and k not in out and vals and vals[0] is not None:
                if k in ('ocf', 'capex', 'buyback') and sec != 'cf': continue
                out[k] = vals
    return out

if __name__ == '__main__':
    d = {}
    for f in sorted(os.listdir(sys.argv[1])):
        d[f[:-5]] = parse(os.path.join(sys.argv[1], f))
    json.dump(d, open(sys.argv[2], 'w'), ensure_ascii=False, indent=0)
    for k, v in d.items():
        print(k, {x: v[x][0] if x in v else None for x in ['rev', 'gp', 'opInc', 'ni', 'eps', 'ocf', 'capex', 'cash', 'equity', 'stock']})
