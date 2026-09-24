// Isolated UI fixture: never submits a real order or sends Telegram files.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
try {
  for(const lang of ['fa','en'])for(const width of [390,1280]) {
    const page=await browser.newPage({viewport:{width,height:850},reducedMotion:'reduce'});
    await page.addInitScript(value=>{localStorage.setItem('sensi-lang',value);window.EventSource=class extends EventTarget{close(){}};},lang);
    let submitted;
    await page.route('**/api/**',route=>{
      const request=route.request(),path=new URL(request.url()).pathname;
      if(path==='/api/orders/7/plan'&&request.method()==='POST'){submitted=request.postDataBuffer()?.toString('latin1');return route.fulfill({json:{ok:true}});}
      if(request.method()==='POST')throw Error('Unexpected mutation in fixture');
      if(path==='/api/session')return route.fulfill({json:{role:'leader',staffId:1,displayName:'Coach',csrf:'fixture',permissions:[]}});
      if(path==='/api/orders')return route.fulfill({json:{items:[{id:7,customer_id:9,name:'Client',product_title:'Custom plan',status:'ready',delivery_mode:'manual',amount:100000,paid_at:'2026-09-15T10:00:00Z',created_at:'2026-09-15T10:00:00Z'}],total:1,page:1,pageSize:20,counts:{actionable:1,automatic:0,new_orders:0,designing:1,needs_info:0,receipts:0}}});
      if(path==='/api/orders/7')return route.fulfill({json:{id:7,customer_id:9,name:'Client',product_title:'Custom plan',status:'ready',amount:100000,paid_at:'2026-09-15T10:00:00Z',created_at:'2026-09-15T10:00:00Z',form_snapshot:{},product_snapshot:{delivery_mode:'manual'}}});
      if(path==='/api/collaboration/order/7')return route.fulfill({json:{assignment:{staff_id:null,version:1},notes:[],members:[]}});
      return route.fulfill({json:{}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://localhost:8092'}/orders`);
    await page.locator('.task-card').click();
    const form=page.locator('.delivery-bundle');
    await form.waitFor();
    assert.equal(await form.locator('.delivery-bundle-fields > .delivery-field + .delivery-files-heading + .delivery-file-picker').count(),1,'manual bundle must show message then files');
    assert.equal(await form.locator('.delivery-bundle-fields > .delivery-links').count(),1,'manual bundle must use shared link editor');
    await form.locator('textarea').fill('Delivery note');
    await form.getByRole('button',{name:lang==='fa'?'افزودن لینک':'Add link'}).click();
    await form.locator('input[type=url]').fill('https://example.org/plan');
    await form.locator('input[type=file]').setInputFiles({name:'plan.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4')});
    await form.locator('input[type=file]').setInputFiles({name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('Daily notes')});
    assert.equal(await form.locator('.delivery-selected-files li').count(),2);
    assert.equal(await form.locator('.delivery-file-picker .button.primary').count(),1,'manual and automatic file controls share the same component');
    assert.ok(await form.locator('button[type=submit]').isEnabled());
    assert.ok(await page.locator('.order-dialog').evaluate(element=>element.scrollWidth<=element.clientWidth+1));
    if(width===390)await form.screenshot({path:`../artifacts/manual-delivery-${lang}-390.png`});
    const delivered=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/orders/7/plan');
    await form.locator('button[type=submit]').click();
    await delivered;
    assert.ok(submitted?.includes('plan.pdf')&&submitted?.includes('notes.txt')&&submitted?.includes('Delivery note')&&submitted?.includes('https://example.org/plan'),'multipart bundle omitted a message, file or link');
    await page.close();
  }
  console.log('PASS: manual delivery message/files/links parity and mobile width (mock API)');
} finally {await browser.close();}
