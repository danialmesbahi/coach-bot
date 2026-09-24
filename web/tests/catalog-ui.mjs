// API fixtures only: creates no real products or Telegram channel memberships.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||undefined});
const errors=[];
try {
  for(const lang of ['fa','en']) for(const width of [375,390,820,844,1024,1440]) {
    const page=await browser.newPage({viewport:{width,height:width===844?390:width===1024?768:900},hasTouch:width<=1024,isMobile:width<=1024,reducedMotion:'reduce'});
    page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(({lang,width})=>{localStorage.setItem('sensi-lang',lang);localStorage.setItem('sensi-theme',width===820?'light':'dark');Object.defineProperty(navigator,'standalone',{value:true});},{lang,width});
    let saved,saveFails=true,archiveRequests=0;
    const product={id:1,version:1,title:'Training program',description:'Personal coaching for three months',price_irr:900000,duration_days:90,delivery_mode:'manual',form_fields:['name','phone','notes'],questions:[],response_text:'',content_url:'',asset_id:null,channel_id:null,active:true,sort_order:0};
    await page.route('**/api/**',async route=>{
      const request=route.request(),path=new URL(request.url()).pathname;
      if(path==='/api/events')return route.fulfill({status:200,contentType:'text/event-stream',body:': fixture\n\n'});
      if(path==='/api/catalog/1'&&request.method()==='POST'){saved=request.postDataJSON();return route.fulfill(saveFails?{status:400,json:{error:'invalid_product',field:'duration_days'}}:{json:{ok:true}});}
      if(path.endsWith('/archive')){archiveRequests++;return route.fulfill({json:{ok:true}});}
      await route.fulfill({json:path==='/api/session'?{role:'leader',staffId:1,displayName:'Coach',username:'coach',csrf:'fixture',permissions:[]}:{items:[product],channels:[{chat_id:-100123,title:'Private members'}],total:1,page:1,pageSize:20}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8091'}/catalog`);
    await page.locator('.catalog-card').waitFor();
    const arrows=await page.locator('.catalog-page .pager button').evaluateAll(buttons=>buttons.map(button=>{
      const svg=button.querySelector('svg'),icon=svg.getBoundingClientRect(),box=button.getBoundingClientRect();
      return {right:svg.classList.contains('lucide-arrow-right'),scale:new DOMMatrix(getComputedStyle(svg).transform).a,side:Math.sign(icon.x+icon.width/2-box.x-box.width/2)};
    }));
    assert.deepEqual(arrows,[
      {right:true,scale:lang==='fa'?1:-1,side:lang==='fa'?1:-1},
      {right:false,scale:lang==='fa'?1:-1,side:lang==='fa'?-1:1},
    ],`pagination arrow direction and label placement (${lang}, ${width})`);
    await page.locator('.catalog-card').click();
    const dialog=page.locator('.catalog-dialog');
    await dialog.waitFor();
    if(width>1024){
      await page.mouse.click(4,4);
      await dialog.waitFor({state:'hidden'});
      await page.locator('.catalog-card').click();
      await dialog.waitFor();
      await dialog.locator('header h2').click();
      assert.ok(await dialog.isVisible(),'inside click must not close editor');
    }else{
      await page.touchscreen.tap(4,4);
      assert.ok(await dialog.isVisible(),'phone/tablet PWA outside tap must not close editor');
      await dialog.locator('header h2').tap();
      assert.ok(await dialog.isVisible(),'touching editor content must not dismiss it');
    }
    assert.ok(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+1),'editor overflows horizontally');
    assert.equal(await dialog.locator('.catalog-beta').count(),1,'only the private-channel mode is marked beta');
    assert.equal(await dialog.locator('.catalog-beta').innerText(),lang==='fa'?'بتا':'Beta');
    assert.equal(await dialog.locator('.catalog-section-nav').count(),0,'unnecessary section tabs remain');
    assert.equal(await dialog.locator('details.catalog-placement').count(),0,'position hidden in disclosure');
    await dialog.getByRole('button',{name:lang==='fa'?'محل نمایش دوره':'Display position',exact:true}).click();
    await page.getByRole('option',{name:lang==='fa'?'انتهای ویترین':'End of storefront',exact:true}).click();
    await dialog.getByRole('button',{name:lang==='fa'?'پنهان / پیش‌نویس':'Hidden / draft',exact:true}).click();
    await dialog.getByRole('button',{name:lang==='fa'?'نمایش و فروش':'Visible for sale',exact:true}).click();
    await dialog.getByRole('button',{name:lang==='fa'?'واحد مدت':'Duration unit',exact:true}).click();
    for(const label of lang==='fa'?['روز','هفته','ماه','سال','دائمی','یک‌بار مصرف']:['Days','Weeks','Months','Years','Lifetime','One-time'])assert.equal(await page.getByRole('option',{name:label,exact:true}).count(),1);
    await page.getByRole('option',{name:lang==='fa'?'هفته':'Weeks',exact:true}).click();
    await dialog.getByLabel(lang==='fa'?'مدت اعتبار':'Duration',{exact:true}).fill('2');
    await dialog.getByRole('button',{name:lang==='fa'?'حذف از فروشگاه':'Archive product',exact:true}).click();
    const confirmation=page.getByRole('alertdialog');
    assert.ok(await confirmation.evaluate(el=>el.matches(':modal')),'confirmation is not a top-layer modal');
    assert.ok(await confirmation.evaluate(el=>{const r=el.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}),'archive confirmation outside viewport');
    if(width===390&&lang==='fa')await page.screenshot({path:'../artifacts/catalog-confirm-mobile.png'});
    await confirmation.getByRole('button',{name:lang==='fa'?'انصراف':'Cancel',exact:true}).click();
    assert.equal(archiveRequests,0,'cancel archived the course');
    assert.ok(await dialog.isVisible(),'cancel closed the editor');
    await dialog.getByRole('button',{name:lang==='fa'?'حذف از فروشگاه':'Archive product',exact:true}).click();
    await page.keyboard.press('Escape');
    assert.ok(await dialog.isVisible(),'Escape propagated to editor');
    await page.locator('.catalog-modes button').nth(2).click();
    if(width===390&&lang==='fa'){await dialog.locator('.catalog-modes').scrollIntoViewIfNeeded();await dialog.screenshot({path:'../artifacts/catalog-beta-mobile.png'});}
    await dialog.getByRole('button',{name:lang==='fa'?'کانال متصل':'Connected channel',exact:true}).click();
    await page.getByRole('option',{name:'Private members'}).click();
    const fields=await dialog.locator('.catalog-fields').first().boundingBox();
    assert.ok(fields?.width>0);
    await page.locator('.catalog-modes button').nth(1).click();
    await dialog.locator('.delivery-links button').last().click();
    await dialog.locator('input[type=url]').fill('https://example.com/course');
    await dialog.locator('footer button').last().click();
    await dialog.locator('.staff-feedback.error').waitFor();
    assert.ok(await dialog.evaluate(el=>{
      const footer=el.querySelector('form>footer').getBoundingClientRect(),error=el.querySelector('.staff-feedback.error').getBoundingClientRect();
      return error.bottom<=footer.top+1&&footer.bottom<=innerHeight+1;
    }),'feedback overlaps action bar');
    if(width===390&&lang==='fa')await page.screenshot({path:'../artifacts/catalog-error-mobile.png'});
    saveFails=false;
    await dialog.locator('footer button').last().click();
    await dialog.waitFor({state:'hidden'});
    assert.equal(saved.delivery_mode,'content');assert.equal(saved.duration_days,14);assert.equal(saved.duration_unit,'weeks');assert.equal(saved.content_url,'https://example.com/course');assert.equal(saved.before_id,null);assert.equal(saved.active,true);
    if(width===390&&lang==='fa')await page.screenshot({path:'../artifacts/catalog-mobile.png',fullPage:true});
    if(width===1440&&lang==='en'){await page.locator('.catalog-card').click();await page.screenshot({path:'../artifacts/catalog-editor.png'});}
    if(width===390){
      await page.locator('.catalog-card').click();
      await dialog.locator('.catalog-visibility').scrollIntoViewIfNeeded();
      await page.screenshot({path:`../artifacts/catalog-visibility-${lang}.png`});
      await dialog.getByRole('button',{name:lang==='fa'?'حذف از فروشگاه':'Archive product',exact:true}).click();
      await page.getByRole('alertdialog').getByRole('button',{name:lang==='fa'?'تأیید حذف':'Confirm archive',exact:true}).click();
      await dialog.waitFor({state:'hidden'});
      assert.equal(archiveRequests,1,'archive must require explicit confirmation');
    }
    await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: product editor without section tabs, six duration units, visible archive confirmation, delivery modes, channel menu and save at 375/390/820/1024/1440 in FA/EN and light/dark (mock API)');
} finally {await browser.close();}
