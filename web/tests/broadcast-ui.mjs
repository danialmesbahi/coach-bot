// API fixtures only: no real Telegram broadcast is sent.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
try {
  for(const lang of ['fa','en'])for(const width of [390,820,1280]) {
    const page=await browser.newPage({viewport:{width,height:850},reducedMotion:'reduce'});
    await page.addInitScript(value=>localStorage.setItem('sensi-lang',value),lang);
    const previews=[];
    const campaigns=[];
    let sendAttempts=0;
    await page.route('**/api/**',route=>{
      const request=route.request(),path=new URL(request.url()).pathname;
      if(path==='/api/events')return route.fulfill({contentType:'text/event-stream',body:': fixture\n\n'});
      if(path==='/api/session')return route.fulfill({json:{role:'leader',staffId:1,displayName:'Coach',csrf:'fixture',permissions:[]}});
      if(path==='/api/broadcasts/preview') {const body=request.postDataJSON();previews.push(body);return route.fulfill({json:body.audience.search==='nobody'?{count:0,recipients:[],next_cursor:null}:body.after_id?{count:2,recipients:[{id:21,name:'New client',username:'new'}],next_cursor:null}:{count:2,recipients:[{id:42,name:'Sajjad',username:'sajjad',has_paid_order:false}],next_cursor:42}});}
      if(path==='/api/broadcasts'&&request.method()==='POST'){
        if(++sendAttempts===1)return route.fulfill({status:409,json:{error:'audience_changed'}});
        campaigns.unshift({id:42,message:request.postDataJSON().message,status:'queued',created_at:new Date().toISOString(),total:2,sent:0,failed:0,paused:0});
        return route.fulfill({json:{ok:true,id:42,count:2}});
      }
      if(path==='/api/broadcasts')return route.fulfill({json:{products:[{id:2,title:'Course A'},{id:3,title:'Course B'}],campaigns}});
      return route.fulfill({json:{}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8092'}/broadcasts`);
    await page.locator('.broadcast-page').waitFor();
    assert.equal(await page.locator('.page-progress').count(),0,'indefinite global progress bar');
    assert.equal(await page.locator('.content-pane').getAttribute('aria-busy'),'false');
    assert.equal(await page.locator('.broadcast-mobile-actions').isVisible(),width<=820,'mobile send action should follow recipient filters');
    await page.locator('#broadcast-message').fill('A test announcement');
    await page.getByRole('button',{name:lang==='fa'?'ارتباط کاربر با دوره‌ها':'Course relationship'}).click();
    await page.getByRole('option',{name:lang==='fa'?'دورهٔ فعال':'Active course'}).click();
    await page.getByRole('checkbox',{name:'Course A'}).click();
    await page.locator('.broadcast-advanced').first().locator('summary').click();
    const advanced=page.locator('.broadcast-advanced').first();
    assert.ok(await advanced.evaluate(element=>parseFloat(getComputedStyle(element).paddingInlineStart)>=12),'expanded filters need a clear inset');
    assert.equal(await advanced.locator('.broadcast-filter-grid').first().evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').length),1,'long filter labels must not compete for narrow columns');
    assert.equal(await advanced.getByRole('spinbutton',{name:lang==='fa'?'سن (سال) از':'Age (years) From'}).count(),1);
    await page.getByRole('button',{name:lang==='fa'?'جنسیت':'Gender'}).click();
    await page.getByRole('option',{name:lang==='fa'?'زن':'Female'}).click();
    await page.getByText('Sajjad',{exact:true}).waitFor();
    const latest=previews.at(-1).audience;
    assert.equal(latest.purchase_state,'active');
    assert.deepEqual(latest.product_ids,[2]);
    assert.equal(latest.gender,'زن');
    assert.ok(previews.length<=2,'filter changes should debounce preview requests');
    assert.equal(await page.locator('.broadcast-recipient').count(),1);
    await page.getByRole('button',{name:lang==='fa'?'نمایش بیشتر':'Show more'}).click();
    await page.getByText('New client',{exact:true}).waitFor();
    assert.equal(await page.locator('.broadcast-recipient').count(),2);
    await page.locator('#broadcast-message').fill('Revised announcement');
    assert.equal(await page.getByRole('button',{name:lang==='fa'?'بررسی و ارسال':'Review & send'}).isEnabled(),true,'editing the message must not invalidate the audience preview');
    await page.locator('.broadcast-range').filter({hasText:lang==='fa'?'قد (سانتی‌متر)':'Height (cm)'}).locator('input').first().fill('170');
    await page.getByLabel(lang==='fa'?'هدف یا متن پروفایل':'Goal or profile text').fill('strength');
    await page.getByText('Sajjad',{exact:true}).waitFor();
    await page.waitForFunction(()=>/matching clients|مطابق فیلترها/.test(document.querySelector('.broadcast-recipients-heading small')?.textContent||''));
    assert.equal(previews.at(-1).audience.height_min,170);
    assert.equal(previews.at(-1).audience.profile_keyword,'strength');
    assert.equal(await page.locator('img[src*="/media/customers/"]').count(),0,'broadcast preview must not trigger avatar downloads');
    await page.locator('h1').click();
    await page.screenshot({path:`../artifacts/broadcast-preview-${lang}-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:lang==='fa'?'بررسی و ارسال':'Review & send'}).click();
    await page.getByRole('button',{name:lang==='fa'?'تأیید ارسال':'Confirm send'}).click();
    await page.getByRole('alert').filter({hasText:lang==='fa'?'مخاطبان تغییر کرده‌اند':'Recipients changed'}).waitFor();
    await page.waitForFunction(()=>document.querySelector('.broadcast-summary')?.textContent?.includes('2')||document.querySelector('.broadcast-summary')?.textContent?.includes('۲'));
    await page.getByRole('button',{name:lang==='fa'?'بررسی و ارسال':'Review & send'}).click();
    await page.getByRole('button',{name:lang==='fa'?'تأیید ارسال':'Confirm send'}).click();
    await page.locator('.broadcast-history article').first().waitFor();
    assert.equal(await page.getByRole('checkbox',{name:'Course A'}).getAttribute('aria-checked'),'true','sending must preserve product filter');
    assert.equal(await page.getByRole('button',{name:lang==='fa'?'جنسیت':'Gender'}).getAttribute('aria-expanded'),'false');
    assert.equal(await page.locator('.broadcast-progress').first().getAttribute('max'),'2');
    assert.equal(await page.locator('.broadcast-progress').first().getAttribute('value'),'0');
    const positions=await page.evaluate(()=>{const box=selector=>{const rect=document.querySelector(selector).getBoundingClientRect();return {top:rect.top,bottom:rect.bottom};};return {compose:box('.broadcast-compose'),audience:box('.broadcast-audience'),history:box('.broadcast-history')};});
    assert.ok(width<=820?positions.compose.bottom<positions.audience.top&&positions.audience.bottom<positions.history.top:Math.abs(positions.history.top-positions.compose.bottom-18)<2,'broadcast section order');
    campaigns[0].sent=2;campaigns[0].status='completed';
    if(lang==='fa'&&width===390){
      await page.waitForFunction(()=>document.querySelector('.broadcast-progress')?.getAttribute('value')==='2',null,{timeout:15000});
      assert.match(await page.locator('.broadcast-history article').first().innerText(),/پایان‌یافته/);
    }
    await page.locator('.broadcast-search input').fill('nobody');
    await page.getByText(lang==='fa'?'کسی با این فیلترها پیدا نشد. فیلترها را کمتر کن.':'No clients match. Try broader filters.').waitFor();
    assert.equal(await page.locator('.broadcast-recipient').count(),0);
    assert.ok(previews.at(-1).audience.search==='nobody');
    await page.screenshot({path:`../artifacts/broadcast-${lang}-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:lang==='fa'?'ارتباط کاربر با دوره‌ها':'Course relationship'}).click();
    await page.getByRole('option',{name:lang==='fa'?'بدون خرید':'Never purchased'}).click();
    assert.equal(await page.locator('.broadcast-products').count(),0);
    assert.equal(await page.getByRole('button',{name:lang==='fa'?'بررسی و ارسال':'Review & send'}).isDisabled(),true);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'broadcast page overflows');
    await page.close();
  }
  console.log('PASS: responsive broadcast flow, retained filters, queued/completed progress, debounced preview (mock API)');
} finally {await browser.close();}
