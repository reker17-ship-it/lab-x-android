const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.env.WIEHL_PLAYWRIGHT || 'playwright');
const assets = path.resolve('app/src/main/assets');
const out = path.resolve('store-assets');
const server = http.createServer((req,res)=>{
  const url = new URL(req.url,'http://127.0.0.1');
  const files = {'/':'index.html','/index.html':'index.html','/online.js':'online.js','/peerjs.min.js':'peerjs.min.js'};
  const name=files[url.pathname];
  if(!name){res.writeHead(404);res.end();return;}
  res.writeHead(200,{'Content-Type':name.endsWith('.html')?'text/html; charset=utf-8':'application/javascript; charset=utf-8'});
  res.end(fs.readFileSync(path.join(assets,name)));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser=await chromium.launch({headless:true});
    const context=await browser.newContext({viewport:{width:412,height:915},deviceScaleFactor:2,isMobile:true,hasTouch:true,reducedMotion:'reduce'});
    const page=await context.newPage();
    const errors=[];
    page.on('pageerror',err=>errors.push(String(err)));
    await page.addInitScript(()=>{Math.random=()=>0;});
    await page.goto('http://127.0.0.1:'+server.address().port+'/');
    await page.locator('#board .tile').last().waitFor();
    assert.equal(await page.locator('#board .tile').count(),24);
    await page.getByRole('button',{name:'Datenschutz',exact:true}).click();
    assert.equal(await page.locator('#privacy-info').evaluate(d=>d.open),true);
    await page.locator('#privacy-info').getByRole('button',{name:'Schließen',exact:true}).click();
    await page.getByRole('button',{name:'Online spielen (Test)',exact:true}).click();
    assert.equal(await page.locator('#online-dialog').evaluate(d=>d.open),true);
    await page.locator('#online-close').click();
    fs.mkdirSync(out,{recursive:true});
    await page.screenshot({path:path.join(out,'Browser-Vorschau-1.png')});
    await page.getByRole('button',{name:'Würfeln',exact:true}).click();
    await page.waitForFunction(()=>state.phase==='buy');
    assert.equal(await page.evaluate(()=>state.players[0].pos),2);
    await page.screenshot({path:path.join(out,'Browser-Vorschau-2.png')});
    await page.getByRole('button',{name:'Kaufen · 7 M',exact:true}).click();
    assert.equal(await page.evaluate(()=>state.deeds[2].owner),0);
    assert.equal(await page.evaluate(()=>state.players[0].money),23);
    await page.getByRole('button',{name:'Zug beenden',exact:true}).click();
    await page.getByRole('button',{name:'Würfeln',exact:true}).click();
    await page.waitForFunction(()=>state.phase==='end');
    assert.equal(await page.evaluate(()=>state.players[0].money),25);
    assert.equal(await page.evaluate(()=>state.players[1].money),28);
    await page.getByRole('button',{name:'Zug beenden',exact:true}).click();
    await page.reload();
    assert.equal(await page.evaluate(()=>state.round),2);
    assert.equal(await page.evaluate(()=>state.deeds[2].owner),0);
    for(let i=0;i<80;i++){
      const phase=await page.evaluate(()=>state.phase);
      if(phase==='finished')break;
      if(phase==='ready'){
        await page.getByRole('button',{name:'Würfeln',exact:true}).click();
        await page.waitForFunction(()=>state.phase!=='ready');
      }else if(phase==='buy'||phase==='upgrade'){
        await page.getByRole('button',{name:'Passen',exact:true}).click();
      }else if(phase==='end'){
        await page.getByRole('button',{name:'Zug beenden',exact:true}).click();
      }else throw new Error('Unexpected game phase: '+phase);
    }
    assert.equal(await page.evaluate(()=>state.phase),'finished');
    assert.equal(await page.evaluate(()=>state.round),12);
    await page.screenshot({path:path.join(out,'Browser-Vorschau-3.png')});
    assert.deepEqual(errors,[]);
    console.log('PASS: 24 board tiles, privacy dialog, online setup dialog, purchase, rent, persistence, complete 12-round game.');
  }finally{
    if(browser)await browser.close();
    server.close();
  }
})().catch(err=>{console.error(err);process.exitCode=1;});
