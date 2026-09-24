// Private API fixtures: no real uploads, payments, edits or Telegram messages.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
try {
  for(const lang of ['fa','en'])for(const width of [375,820,844,1440]){
    const page=await browser.newPage({viewport:{width,height:width===844?390:900},reducedMotion:'reduce'});
    const fixture=await page.evaluate(async(portrait)=>{
      const canvas=document.createElement('canvas');canvas.width=portrait?2160:3840;canvas.height=portrait?3840:2160;document.body.append(canvas);
      const ctx=canvas.getContext('2d');ctx.fillStyle='#64748b';ctx.fillRect(0,0,160,100);
      ctx.fillStyle='#fff';ctx.font='20px sans-serif';ctx.fillText('Course',40,55);
      const png=canvas.toDataURL().split(',')[1];
      const stream=canvas.captureStream(10),recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8'}),chunks=[];
      recorder.ondataavailable=e=>chunks.push(e.data);
      const stopped=new Promise(resolve=>recorder.onstop=resolve);
      recorder.start();
      for(let frame=0;frame<8;frame++){
        await new Promise(resolve=>setTimeout(resolve,100));ctx.fillRect(frame*5,0,4,4);stream.getVideoTracks()[0].requestFrame();
      }
      recorder.stop();await stopped;
      stream.getTracks().forEach(track=>track.stop());
      return {png,video:Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer()))};
    },width<820);
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(lang=>{localStorage.setItem('sensi-lang',lang);},lang);
    let items=[1,2].map(id=>({id,version:1,title:`Course ${id}`,description:'',price_irr:1000,duration_days:30,duration_unit:'months',delivery_mode:'content',asset_ids:[80],assets:[{id:80,filename:'existing-photo.png',byte_size:200}],asset_id:80,channel_id:null,form_fields:[],questions:[],response_text:'Welcome',content_url:'',active:true,sort_order:id}));
    let uploads=0,saved,move,previewRequests=0;
    await page.route('**/api/**',async route=>{
      const req=route.request(),path=new URL(req.url()).pathname;
      if(path==='/api/events')return route.fulfill({contentType:'text/event-stream',body:': fixture\n\n'});
      if(path==='/api/session')return route.fulfill({json:{role:'leader',staffId:1,displayName:'Coach',csrf:'fixture',permissions:[]}});
      if(path.endsWith('/preview')){previewRequests++;return route.fulfill({contentType:'image/png',body:Buffer.from(fixture.png,'base64')});}
      if(path==='/api/catalog-order'){
        move=req.postDataJSON();items=[items[1],items[0]];
        return route.fulfill({json:{ok:true}});
      }
      if(path==='/api/catalog-assets')return route.fulfill({json:{id:++uploads+100,filename:['large.pdf','photo.png','gallery.webm'][uploads-1],byte_size:uploads===1?12*1024*1024:100}});
      if(path==='/api/catalog/1'&&req.method()==='POST'){saved=req.postDataJSON();return route.fulfill({json:{ok:true}});}
      return route.fulfill({json:{items,channels:[],total:2,page:1,pageSize:20,next_id:null,download_base_configured:false}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8092'}/catalog`);
    await page.getByRole('button',{name:lang==='fa'?'چیدمان دوره‌ها':'Arrange products'}).click();
    assert.equal(await page.locator(".catalog-arrange-toggle").getAttribute("aria-pressed"),"true");
    const handles=page.locator('.catalog-drag');
    const a=await handles.nth(0).boundingBox(),b=await handles.nth(1).boundingBox();
    await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();
    const row=await page.locator('[data-order-index="1"]').boundingBox();
    await page.mouse.move(b.x+b.width/2,row.y+row.height-8,{steps:8});
    assert.ok(await page.locator('.catalog-insert-line.at-end').isVisible(),'show insertion gap below the last row');
    assert.equal(await page.locator('.drop-target').count(),0,'never indicate replacement of a product');
    await page.mouse.up();
    await page.waitForFunction(()=>document.querySelector('.catalog-sort>div>span')?.textContent.startsWith('Course 2'));
    assert.equal(move?.id,1);assert.equal(move?.before_id,null);
    assert.ok(await page.locator('.catalog-sort').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
    if(width===375||width===1440)await page.screenshot({path:`../artifacts/catalog-order-${lang}-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:lang==='fa'?'پایان چیدمان':'Done arranging'}).click();
    assert.equal(await page.locator(".catalog-arrange-toggle").getAttribute("aria-pressed"),"false");
    await page.locator('.catalog-card').filter({has:page.getByRole('heading',{name:'Course 1',exact:true})}).click();
    const dialog=page.locator('.catalog-dialog');
    assert.equal(await dialog.locator('.delivery-bundle-automatic .upload-title').count(),1,'automatic content should use the manual delivery panel pattern');
    if(width===375||width===1440){await dialog.locator('.delivery-bundle-automatic').scrollIntoViewIfNeeded();await dialog.screenshot({path:`../artifacts/catalog-delivery-form-${lang}-${width}.png`});}
    assert.equal(await dialog.locator('.delivery-bundle-fields > .delivery-field + .delivery-files-heading + .delivery-file-picker').count(),1,'ready-made bundle must show message then files');
    assert.equal(await dialog.locator('.delivery-bundle-fields > .delivery-links').count(),1,'ready-made bundle must use shared link editor');
    assert.equal(await dialog.getByLabel(/Custom questions|سؤال‌های اختصاصی/).count(),0);
    await dialog.getByRole('button',{name:lang==='fa'?'واحد مدت':'Duration unit',exact:true}).click();
    await page.getByRole('option',{name:lang==='fa'?'یک‌بار مصرف':'One-time',exact:true}).click();
    assert.equal(await dialog.getByLabel(lang==='fa'?'مدت اعتبار':'Duration',{exact:true}).count(),0);
    await dialog.locator('input[type=file]').setInputFiles([
      {name:'large.pdf',mimeType:'application/pdf',buffer:Buffer.concat([Buffer.from('%PDF-1.4\n'),Buffer.alloc(12*1024*1024)])},
      {name:'photo.png',mimeType:'image/png',buffer:Buffer.from(fixture.png,'base64')},
      {name:'gallery.webm',mimeType:'video/webm',buffer:Buffer.from(fixture.video)},
    ]);
    await dialog.locator('.catalog-assets li').nth(3).waitFor();
    assert.equal(uploads,3);
    await dialog.locator('.catalog-assets').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>[...document.querySelectorAll('.catalog-assets img')].every(img=>img.naturalWidth>0));
    await page.waitForFunction(()=>document.querySelector('.catalog-assets video')?.videoWidth>0).catch(async error=>{
      console.log('Video preview state',await dialog.locator('.catalog-assets').innerHTML(),fixture.video.length);
      throw error;
    });
    assert.ok(previewRequests>=1,'persisted image did not use private preview endpoint');
    assert.ok(await dialog.locator('.catalog-assets img').nth(1).getAttribute('src').then(src=>src.startsWith('blob:')),'new image was downloaded again');
    await dialog.locator('.catalog-asset-preview').nth(2).click();
    await page.getByRole('button',{name:lang==='fa'?'بزرگ‌نمایی':'Zoom in',exact:true}).click();
    assert.ok(await page.locator('.catalog-media-dialog img').getAttribute('style').then(style=>style.includes('1.25')));
    await page.keyboard.press('Escape');
    await page.locator('.catalog-media-dialog').waitFor({state:'detached'});
    assert.equal(await page.locator('.catalog-media-dialog').count(),0);
    assert.ok(await dialog.isVisible(),'closing preview closed the product editor');
    await dialog.locator('.catalog-asset-preview').nth(3).click();
    await page.waitForFunction(()=>document.querySelector('.catalog-media-dialog video')?.videoWidth>0);
    assert.ok(await page.locator('.catalog-media-dialog').evaluate(dialog=>{
      const stage=dialog.querySelector('.media-viewer__stage'),video=stage.querySelector('video');
      const s=stage.getBoundingClientRect(),v=video.getBoundingClientRect();
      return v.left>=s.left-1&&v.right<=s.right+1&&v.top>=s.top-1&&v.bottom<=s.bottom+1&&
        s.bottom<=innerHeight&&s.right<=innerWidth&&stage.scrollHeight<=stage.clientHeight+1&&stage.scrollWidth<=stage.clientWidth+1&&
        dialog.scrollHeight<=dialog.clientHeight+1&&dialog.scrollWidth<=dialog.clientWidth+1;
    }),'4K video overflows its preview viewport');
    if(width===375)await page.locator('.catalog-media-dialog').screenshot({path:`../artifacts/catalog-video-4k-${lang}.png`});
    await page.locator('.catalog-media-dialog').getByRole('button',{name:lang==='fa'?'بستن':'Close',exact:true}).click();
    await page.locator('.catalog-media-dialog').waitFor({state:'detached'});
    assert.equal(await dialog.locator('.staff-feedback').count(),0,'public domain warning blocks small one-time content');
    assert.ok(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+1));
    await dialog.locator('.catalog-assets').screenshot({path:`../artifacts/catalog-files-${lang}-${width}.png`});
    await dialog.getByRole('button',{name:lang==='fa'?'ذخیره دوره':'Save product',exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    assert.deepEqual(saved.asset_ids,[80,101,102,103]);assert.equal(saved.duration_days,-1);assert.equal(saved.duration_unit,'once');
    assert.deepEqual(saved.questions,[]);
    assert.deepEqual(errors,[]);
    await page.close();
  }
  console.log('PASS: reorder, no custom questions, one-time without domain, uploads, 4K portrait/landscape containment, image zoom, Escape, save at 375/820/844/1440 FA/EN (mock API)');
}finally{await browser.close();}
