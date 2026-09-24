// Insertion, not replacement. API fixtures only; no real products are modified.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
try {
  for(const touch of [false,true]){
    const page=await browser.newPage({viewport:{width:touch?390:1440,height:1000},hasTouch:touch,isMobile:touch});
    await page.addInitScript(()=>localStorage.setItem('sensi-lang','en'));
    let items=[1,2,3,4].map(id=>({id,version:1,title:`Course ${id}`,price_irr:1000,duration_days:30,delivery_mode:'manual',active:true})),moves=[];
    await page.route('**/api/**',async route=>{
      const req=route.request(),path=new URL(req.url()).pathname;
      if(path==='/api/events')return route.fulfill({contentType:'text/event-stream',body:': fixture\n\n'});
      if(path==='/api/session')return route.fulfill({json:{role:'leader',staffId:1,displayName:'Coach',csrf:'test',permissions:[]}});
      if(path==='/api/catalog-order'){
        const move=req.postDataJSON();moves.push(move);
        const item=items.find(p=>p.id===move.id);items=items.filter(p=>p.id!==move.id);
        const index=items.findIndex(p=>p.id===move.before_id);items.splice(index<0?items.length:index,0,item);
        return route.fulfill({json:{ok:true}});
      }
      return route.fulfill({json:{items,total:4,page:1,pageSize:20,channels:[],next_id:99}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8092'}/catalog`);
    await page.getByRole('button',{name:'Arrange products'}).click();
    const drag=async(from,to,after,expected,cancel=false)=>{
      const handle=page.locator('.catalog-drag').nth(from);
      const origin=await handle.boundingBox(),dest=await page.locator('[data-order-index]').nth(to).boundingBox();
      const x=origin.x+origin.width/2,y=origin.y+origin.height/2,end=dest.y+(after?dest.height-6:6);
      const before=moves.length,cdp=touch?await page.context().newCDPSession(page):null;
      if(touch){
        await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
        await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:end}]});
      }else{
        await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x,end,{steps:8});
      }
      if(expected!=null){
        await page.locator('.catalog-insert-line').waitFor();
        const line=await page.locator('.catalog-insert-line').boundingBox();
        assert.ok(Math.abs(line.y-(after?dest.y+dest.height+3:dest.y-6))<4,'line must lie between rows, not inside a row');
      }
      if(touch)await cdp.send('Input.dispatchTouchEvent',{type:cancel?'touchCancel':'touchEnd',touchPoints:[]});
      else {if(cancel)await page.keyboard.press('Escape');await page.mouse.up();}
      if(expected!=null&&!cancel){
        await page.waitForFunction(expected=>Array.from(document.querySelectorAll('.catalog-sort-row>span')).map(e=>e.textContent.match(/Course (\d+)/)[1]).join(',')===expected,expected);
        assert.equal(moves.length,before+1);
      }else{
        await page.waitForTimeout(200);assert.equal(moves.length,before,'no-op/cancel must not write');
      }
      assert.equal(await page.locator('.catalog-insert-line').count(),0);
      await cdp?.detach();
    };
    await drag(0,2,false,'2,1,3,4');assert.equal(moves.at(-1).before_id,3);
    await drag(3,0,false,'4,2,1,3');assert.equal(moves.at(-1).before_id,2);
    await drag(0,3,true,'2,1,3,4');assert.equal(moves.at(-1).before_id,99,'page end must preserve next-page boundary');
    await drag(1,1,true,null);
    await drag(0,2,false,'ignored',true);
    await page.locator('.catalog-drag').nth(1).focus();await page.keyboard.press('ArrowUp');
    await page.waitForFunction(()=>document.querySelector('.catalog-sort-row>span').textContent.startsWith('Course 1'));
    await page.close();
  }
  console.log('PASS: mouse/touch insertion before/after, first/end, page boundary, no-op, cancel, keyboard');
}finally{await browser.close();}
