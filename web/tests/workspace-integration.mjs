// Cross-workspace flows with isolated API/SSE fixtures; no real account changes.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||undefined});
const errors=[];
try {
  for(const lang of ['en','fa']) for(const width of [375,820,1440]) {
    const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(lang=>{
      localStorage.setItem('sensi-lang',lang);
      Object.defineProperty(navigator,'standalone',{value:true});
      window.EventSource=class extends EventTarget { constructor(){super();window.testEvents=this;setTimeout(()=>this.onopen?.(),0);} close(){} };
    },lang);
    let incoming=false, badgeReads=0, detailReads=0, pendingNote,orderFilter;
    const data={assignment:{staff_id:null,version:1},notes:[],members:[{id:1,display_name:'Coach'}]};
    const date='2026-09-15T10:00:00Z';
    await page.route('**/api/**',async route=>{
      const req=route.request(),path=new URL(req.url()).pathname;
      let result={ok:true};
      if(path==='/api/session')result={role:'leader',staffId:1,csrf:'fixture',permissions:[],displayName:'Coach'};
      if(path==='/api/followups'){
        badgeReads++;
        result={items:[{target_type:'thread',target_id:9,user_id:9,name:'Client',note_body:'Review this conversation',updated_at:date}],total:1,page:1,pageSize:20,counts:{unread_messages:0},followupCounts:{all:1,unseen:1,seen:0}};
      }
      if(path==='/api/threads/9'){
        detailReads++;
        result={user:{id:9,name:'Client'},items:[...Array.from({length:30},(_,i)=>({id:i+1,content_type:'text',content_text:`Initial message ${i+1}`,direction:'customer',created_at:date})),...(incoming?[{id:100,content_type:'text',content_text:'Live message from another workspace',direction:'customer',created_at:date}]:[])]};
      }
      if(path==='/api/orders'){
        orderFilter=new URL(req.url()).searchParams.get('status');
        result={items:[{id:7,customer_id:9,name:'Client',product_title:'Ready PDF',status:'paid',delivery_mode:'content',amount:100000,paid_at:date,created_at:date}],total:1,page:1,pageSize:20,counts:{actionable:1,automatic:1,new_orders:0,designing:0,needs_info:0,receipts:0}};
      }
      if(path==='/api/orders/7')result={id:7,customer_id:9,name:'Client',product_title:'Ready PDF',status:'paid',amount:100000,paid_at:date,created_at:date,form_snapshot:{},product_snapshot:{delivery_mode:'content'}};
      if(path==='/api/collaboration/order/7')result=data;
      if(path==='/api/collaboration/thread/9'){
        if(req.method()==='POST'){
          const body=req.postDataJSON();
          if(body.action==='assign')data.assignment={staff_id:body.staff_id,version:2};
          else {
            await new Promise(resolve=>{pendingNote=resolve;});
            data.notes.push({id:1,author_name:'Coach',body:body.text,created_at:date});
          }
        }
        result=data;
      }
      await route.fulfill({json:result});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8091'}/followups`);
    assert.ok(await page.locator('.mobile-nav>button').count()<=5);
    if(width===375){
      await page.locator('.mobile-nav').getByRole('button',{name:lang==='fa'?'بیشتر':'More',exact:true}).click();
      await page.locator('.workspace-menu').waitFor({state:'visible'});
      assert.equal(await page.locator('.workspace-menu').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
      await page.keyboard.press('Escape');
    }
    await page.locator('.followup-card').click();
    const notes=page.locator('.chat-notes-dock details');
    await notes.locator('textarea').waitFor({state:'visible'});
    await notes.locator('textarea').fill('Keep my draft');
    await notes.getByRole('button',{name:lang==='fa'?'مسئول پیگیری':'Assignee',exact:true}).click();
    await notes.getByRole('option',{name:'Coach',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.collaboration-assignment button')?.disabled===false);
    assert.equal(await notes.locator('textarea').inputValue(),'Keep my draft','assignment must preserve note draft');
    await notes.locator('button[type=submit]').click();
    await notes.locator('textarea').fill('A second draft while saving');
    while(!pendingNote)await new Promise(resolve=>setTimeout(resolve,10));
    pendingNote();
    await notes.getByText('Keep my draft',{exact:true}).waitFor();
    assert.equal(await notes.locator('textarea').inputValue(),'A second draft while saving','late POST must not erase newer input');
    await notes.locator('summary').click();
    await page.locator('.chat-list').evaluate(el=>{el.scrollTop=100;el.dispatchEvent(new Event('scroll',{bubbles:true}));});
    const readingPosition=await page.locator('.chat-list').evaluate(el=>el.scrollTop);
    // One burst, not one request per event; open thread must update from Follow-ups.
    badgeReads=detailReads=0;incoming=true;
    await page.evaluate(()=>{
      for(let i=0;i<100;i++)window.testEvents.dispatchEvent(new MessageEvent('update',{data:JSON.stringify({table:'staff_assignments',id:i})}));
      window.testEvents.dispatchEvent(new MessageEvent('update',{data:JSON.stringify({table:'support_messages',userId:'9',id:2,action:'insert',direction:'customer'})}));
    });
    await page.getByText('Live message from another workspace',{exact:true}).waitFor();
    assert.ok(badgeReads<=2,`burst made ${badgeReads} followup requests`);
    assert.equal(detailReads,1,'only one detail refresh per burst');
    assert.equal(await page.locator('.chat-list').evaluate(el=>el.scrollTop),readingPosition,'incoming message must not interrupt reading older messages');
    assert.equal(await page.locator('.chat-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    if(width===375)await page.screenshot({path:`../artifacts/workspace-chat-${lang}.png`});
    await page.locator('.chat-dialog').evaluate(el=>el.close());
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8091'}/orders`);
    await page.locator('.task-list-toolbar').getByRole('button',{name:/Automatic delivery|تحویل خودکار/}).click();
    await page.waitForFunction(()=>document.querySelector('.content-pane').getAttribute('aria-busy')==='false');
    assert.equal(orderFilter,'automatic');
    await page.locator('.task-card').click();
    await page.locator('.order-steps').waitFor();
    assert.equal(await page.locator('.order-steps li').count(),2,'automatic order must not show design steps');
    assert.equal(await page.locator('.order-brief,.order-actions').count(),0,'no empty brief or manual actions for instant content');
    assert.equal(await page.locator('.order-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    if(width===375||width===820)await page.screenshot({path:`../artifacts/workspace-order-${lang}-${width}.png`});
    await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: cross-page live chat, 100-event batching, draft preservation, mobile navigation, automatic order workflow, FA/EN at 375/820/1440');
} finally {await browser.close();}
