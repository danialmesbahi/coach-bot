// API fixtures only: creates no real products or Telegram channel memberships.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||undefined});
const errors=[];
try {
  for(const lang of ['fa','en']) for(const width of [390,820,1440]) {
    const page=await browser.newPage({viewport:{width,height:900}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(lang=>localStorage.setItem('sensi-lang',lang),lang);
    let saved;
    const product={id:1,version:1,title:'Training program',description:'Personal coaching for three months',price_irr:900000,duration_days:90,delivery_mode:'manual',form_fields:['name','phone','notes'],questions:[],response_text:'',content_url:'',asset_id:null,channel_id:null,active:true,sort_order:0};
    await page.route('**/api/**',async route=>{
      const request=route.request(),path=new URL(request.url()).pathname;
      if(path==='/api/events')return route.fulfill({status:200,contentType:'text/event-stream',body:': fixture\n\n'});
      if(path==='/api/catalog/1'&&request.method()==='POST'){saved=request.postDataJSON();return route.fulfill({json:{ok:true}});}
      await route.fulfill({json:path==='/api/session'?{role:'leader',staffId:1,displayName:'Coach',username:'coach',csrf:'fixture',permissions:[]}:{items:[product],channels:[{chat_id:-100123,title:'Private members'}],total:1,page:1,pageSize:20}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8091'}/catalog`);
    await page.locator('.catalog-card').click();
    const dialog=page.locator('.catalog-dialog');
    await dialog.waitFor();
    assert.ok(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+1),'editor overflows horizontally');
    await page.locator('.catalog-modes button').nth(2).click();
    await dialog.getByRole('button',{name:lang==='fa'?'کانال متصل':'Connected channel',exact:true}).click();
    await page.getByRole('option',{name:'Private members'}).click();
    const fields=await dialog.locator('.catalog-fields').first().boundingBox();
    assert.ok(fields?.width>0);
    await page.locator('.catalog-modes button').nth(1).click();
    await dialog.locator('input[type=url]').fill('https://example.com/course');
    await dialog.locator('footer button').last().click();
    await dialog.waitFor({state:'hidden'});
    assert.equal(saved.delivery_mode,'content');assert.equal(saved.duration_days,90);assert.equal(saved.content_url,'https://example.com/course');
    if(width===390&&lang==='fa')await page.screenshot({path:'../artifacts/catalog-mobile.png',fullPage:true});
    if(width===1440&&lang==='en'){await page.locator('.catalog-card').click();await page.screenshot({path:'../artifacts/catalog-editor.png'});}
    await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: product editor, delivery modes, channel menu, save and no horizontal overflow at 390/820/1440 in FA/EN (mock API)');
} finally {await browser.close();}
