import re,os,json
pat = re.compile(r"seq_no\.value='(\d+)';document\.t05st01_fm\.spoke_time\.value='(\d+)';document\.t05st01_fm\.spoke_date\.value='(\d+)'")
want = [
 (r'第4季營運成果|第四季暨全年度營運成果|第四季度營運成果', None),
 (r'盈餘轉增資發行新股|除權息基準日|股票股利除權基準日|調整配股率|股利分派', None),
 (r'股票面額|每股面額', None),
 (r'訂定減資基準日|更正公告本公司換股作業計劃|現金減資完成實收資本額變更登記|訂定換股作業計劃', None),
 (r'Pulse Electronics Corporation 交割|基美|KEMET Corp|完成收購法國施耐德|完成對芝浦|股份轉換案，擬發行新股|公開收購茂達電子股份有限公司普通股之公開收購期間屆滿$|宣布在台購地擴產', None),
]
out=[]
for f in sorted(os.listdir('raw/2327/mops')):
    if not f.startswith('t05st01'): continue
    b=open('raw/2327/mops/'+f,'rb').read().decode('utf-8','replace')
    for row in re.findall(r"<tr class='(?:odd|even)'>(.*?)</tr>", b, re.S):
        subj = re.sub(r'\s+','',re.sub(r'<[^>]+>','',row.split('<pre')[1] if '<pre' in row else '').replace('&nbsp;',''))
        m = pat.search(row)
        if not m or '子公司' in subj: continue
        if any(re.search(p, subj) for p,_ in want):
            seq,tm,d = m.groups()
            out.append(f"post 2327/mops/det_{d}_{tm}_{seq}.html https://mopsov.twse.com.tw/mops/web/ajax_t05st01 firstin=true&b_date=&e_date=&TYPEK=sii&year=&month=all&type=&co_id=2327&spoke_date={d}&spoke_time={tm}&seq_no={seq}&MEETING_STEP=&MODEL=&ITEM=&e_month=all&step=2&off=1")
            print(d, subj[:60])
open('work_y/det_want.txt','w').write('\n'.join(out)+'\n'); print(len(out))
