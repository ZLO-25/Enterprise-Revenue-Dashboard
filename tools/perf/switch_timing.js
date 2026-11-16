// 使用者體感：從「點下去」到「新頁面畫面穩定」；可選側邊欄展開、CPU 倍率、裝置寬度
const { chromium } = require('playwright');
const B=process.env.B||'http://127.0.0.1:8791/';
const seq=(process.env.SEQ||'nvda,amd,tsmc,msft,amd').split(',');
const CPU=+(process.env.CPU||1), W=+(process.env.W||1440), SB=process.env.SB==='1', NET=process.env.NET||'';
(async()=>{
  const br=await chromium.launch();
  const ctx=await br.newContext({viewport:{width:W,height:W<600?800:900}});
  const page=await ctx.newPage();
  const cdp=await ctx.newCDPSession(page);
  if(CPU>1) await cdp.send('Emulation.setCPUThrottlingRate',{rate:CPU});
  if(NET){const [lat,down]=NET.split('/').map(Number); await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:lat,downloadThroughput:down*125000,uploadThroughput:down*125000/4});}
  await page.addInitScript((SB)=>{
    try{ if(SB) localStorage.setItem('erd.sidebar.open','1'); }catch(e){}
    window.__lt=[];window.__cls=[];window.__paints=[];
    try{new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__lt.push([Math.round(e.startTime),Math.round(e.duration)]))).observe({type:'longtask',buffered:true});
    new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)window.__cls.push([Math.round(e.startTime),+e.value.toFixed(3),(e.sources||[]).slice(0,3).map(s=>{const n=s.node;return n?(n.id?'#'+n.id:(n.className&&n.className.toString().split(' ')[0])||n.nodeName):'?'}).join(',')])})).observe({type:'layout-shift',buffered:true});
    new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__lcp=Math.round(e.startTime))).observe({type:'largest-contentful-paint',buffered:true});}catch(e){}
    // 最後一次「畫面還在變」的時間：用 rAF 觀察 canvas 動畫結束很難，改記錄 Chart 動畫完成
  },SB);
  let first=true;
  console.log(`CPU ${CPU}x  width ${W}  sidebar ${SB?'open':'closed'}  net ${NET||'local'}`);
  console.log('page   | click→respEnd  →DCL  →load | FCP   LCP | longtask sum/max | CLS total  (when: value: who)');
  for(const c of seq){
    let t0;
    if(first){t0=Date.now();await page.goto(B+(c==='home'?'':c+'/'),{waitUntil:'load'});first=false;}
    else{ t0=Date.now(); await Promise.all([page.waitForNavigation({waitUntil:'load'}), page.evaluate(c=>{const a=c==='home'?document.querySelector('#sb-panel a[data-view=main]'):[...document.querySelectorAll('#sb-panel a.sb-item')].find(a=>a.getAttribute('href').endsWith(c+'/'));a.click();},c)]); }
    await page.waitForTimeout(1800);
    const r=await page.evaluate(()=>{const n=performance.getEntriesByType('navigation')[0];const fcp=(performance.getEntriesByName('first-contentful-paint')[0]||{}).startTime;
      return {re:n.responseEnd,dcl:n.domContentLoadedEventEnd,load:n.loadEventEnd,fcp,lcp:window.__lcp,lt:window.__lt,cls:window.__cls,navT:n.transferSize};});
    const f=x=>String(Math.round(x||0)).padStart(5);
    const lts=r.lt.reduce((s,x)=>s+x[1],0), ltm=Math.max(0,...r.lt.map(x=>x[1]));
    console.log(c.padEnd(6),'|',f(r.re),'     ',f(r.dcl),f(r.load),'|',f(r.fcp),f(r.lcp),'|',f(lts)+'/'+f(ltm),'|',r.cls.reduce((s,x)=>s+x[1],0).toFixed(3),' ',r.cls.filter(x=>x[1]>0.01).map(x=>x[0]+'ms:'+x[1]+':'+x[2]).join(' ; '));
  }
  await br.close();
})();
