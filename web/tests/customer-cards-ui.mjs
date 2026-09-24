// Isolated responsive-card check; never reads or changes actual customer records.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||undefined});
try{
  for(const lang of ['fa','en']){
    const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(({lang,theme})=>{localStorage.setItem('sensi-lang',lang);localStorage.setItem('sensi-theme',theme);},{lang,theme:process.env.TEST_THEME_OVERRIDE|| (lang==='fa'?'light':'dark')});
    await page.route('**/media/customers/*/avatar',route=>process.env.TEST_AVATAR_PATH ? route.fulfill({contentType:'image/png',body:readFileSync(process.env.TEST_AVATAR_PATH)}) : route.fulfill({status:404}));
    await page.route('**/api/**',route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/events')return route.fulfill({contentType:'text/event-stream',body:': fixture\n\n'});
      if(url.pathname==='/api/session')return route.fulfill({json:{role:'leader',staffId:1,csrf:'fixture',permissions:[],displayName:'Coach'}});
      if(url.pathname==='/api/customers'){
        const count=url.searchParams.get('q')?2:8;
        return route.fulfill({json:{items:Array.from({length:count},(_,i)=>({user_id:i+1,name:lang==='fa'?`شاگرد نمونه ${i+1}`:`Client ${i+1}`,username:`client_${i+1}`,orders_count:i+1,active_courses:2})),total:count,page:1,pageSize:20,products:[]}});
      }
      if(/^\/api\/(customers|threads)\/\d+$/.test(url.pathname))return route.fulfill({status:500,json:{error:'fixture detail unavailable'}});
      return route.fulfill({json:{ok:true}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8092'}/customers`);
    await page.locator('.customer-card').first().waitFor();
    for(const width of [1440,1024,820,390,375,844]){
      await page.setViewportSize({width,height:width===844?390:900});
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const metrics=await page.evaluate(()=>{
        const grid=document.querySelector('.customer-grid');
        const cards=[...document.querySelectorAll('.customer-card')];
        return {overflow:document.documentElement.scrollWidth>innerWidth+1,columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,
          aligned:cards.every(card=>{const photo=card.querySelector('.customer-photo').getBoundingClientRect();const actions=card.querySelector('.customer-card-actions').getBoundingClientRect();return photo.width>130&&Math.abs(photo.width-photo.height)<2&&actions.bottom<=card.getBoundingClientRect().bottom+1;}),
          readable:cards.every(card=>parseFloat(getComputedStyle(card.querySelector('.customer-identity strong')).fontSize)>=14&&parseFloat(getComputedStyle(card.querySelector('.customer-card-stats small')).fontSize)>=9),
          targets:cards.every(card=>card.querySelectorAll('button').length===3&&card.querySelector('.customer-message').getBoundingClientRect().height>=44)};
      });
      assert.equal(metrics.overflow,false,`${lang}/${width} overflow`);assert.ok(metrics.columns>=2&&metrics.columns<=5);assert.ok(metrics.aligned,`${lang}/${width} photo and footer alignment`);assert.ok(metrics.readable,`${lang}/${width} typography`);assert.ok(metrics.targets,`${lang}/${width} targets`);
      if(width===390){
        const suffix=`${lang}${process.env.TEST_AVATAR_PATH?'-photo':''}${process.env.TEST_THEME_OVERRIDE?'-'+process.env.TEST_THEME_OVERRIDE:''}`;
        await page.screenshot({path:`../artifacts/customer-card-current-${suffix}.png`});
        await page.locator('.customer-card').first().screenshot({path:`../artifacts/customer-card-detail-${suffix}.png`});
      }
    }
    await page.setViewportSize({width:1440,height:900});
    if(process.env.TEST_AVATAR_PATH)await page.screenshot({path:`../artifacts/customer-card-desktop-${lang}-photo${process.env.TEST_THEME_OVERRIDE?'-'+process.env.TEST_THEME_OVERRIDE:''}.png`});
    await page.locator('.customer-profile-action').first().click();
    await page.locator('.profile-dialog[open]').waitFor();
    await page.locator('.profile-dialog .drawer-desktop-close').click();
    await page.locator('.customer-message').first().click();
    await page.locator('.chat-dialog[open]').waitFor();
    await page.locator('.chat-dialog .drawer-desktop-close').click();
    const before=(await page.locator('.customer-card').first().boundingBox()).width;
    await page.locator('.desktop-customer-tools input').fill('Client');
    await page.waitForFunction(()=>document.querySelectorAll('.customer-card').length===2);
    assert.ok(Math.abs((await page.locator('.customer-card').first().boundingBox()).width-before)<1,'filter enlarged cards');
    assert.equal(await page.locator('.sidebar-foot').isVisible(),false,'empty sidebar divider remains');
    assert.deepEqual(errors,[]);await page.close();
  }
  console.log('PASS: readable portrait cards, 2–5 responsive columns, stable filter sizing, profile/chat actions, FA/EN');
}finally{await browser.close();}
