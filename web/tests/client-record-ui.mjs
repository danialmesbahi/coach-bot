// Isolated browser fixtures: no real profile edits, uploads or Telegram messages.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
const time='2026-10-03T08:00:00+00:00';
try {
  for(const lang of ['fa','en'])for(const width of [375,820,1440]) {
    const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});
    const errors=[],writes=[],chatWrites=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(lang=>localStorage.setItem('sensi-lang',lang),lang);
    let user={id:1,telegram_id:999,name:'Test Athlete',username:'athlete',created_at:time,updated_at:time,gender:'مرد',age:30,height_cm:180,weight_kg:80,notes:'Current profile',photo_count:0};
    const measures={abdomen:90,waist:85,arm:35,thigh:55,shoulders:45,chest:100};
    const orders=[1,2].map(id=>({id,customer_id:1,user_id:1,product_title:`Course ${id}`,status:id===1?'needs_info':'delivered',amount:1000,created_at:time,updated_at:time,paid_at:time,delivered_at:time,duration_days:30,photo_count:4,form_snapshot:{gender:'مرد',age:30,measurements:measures,notes:`Order ${id}`},product_snapshot:{delivery_mode:'manual'}}));
    let reject=false,refreshFailure=false;
    await page.route('**/api/**',async route=>{
      const request=route.request(),url=new URL(request.url()),path=url.pathname;
      if(path==='/api/events')return route.fulfill({contentType:'text/event-stream',body:': fixture\n\n'});
      if(path==='/api/session')return route.fulfill({json:{role:'leader',staffId:1,displayName:'Coach',csrf:'fixture',permissions:[]}});
      if(path==='/api/customers/1/record') {
        if(request.method()==='POST') {
          const body=request.postDataJSON();writes.push(body);
          if(reject)return route.fulfill({status:400,json:{error:'invalid_age'}});
          if(body.order_id)Object.assign(orders[body.order_id-1].form_snapshot,body.fields);
          else Object.assign(user,body.fields);
          return route.fulfill({json:{ok:true}});
        }
        if(refreshFailure)return route.fulfill({status:503,json:{error:'busy'}});
        return route.fulfill({json:{values:{...user,measurements:measures},files:[{id:1,order_id:1,filename:'response.pdf',source:'information',status:'archived',created_at:time}],revisions:[{id:1,created_at:time,snapshot:{notes:'Previous version',measurements:measures}}]}});
      }
      if(path==='/api/customers/1')return route.fulfill({json:{user,orders,history:[],messages:[]}});
      if(path==='/api/customers/1/files')return route.fulfill({json:{files:[{id:9,filename:'body.png',source:'staff',status:'archived',created_at:time}]}});
      if(path==='/api/threads')return route.fulfill({json:{items:[{user_id:1,name:user.name,last_content_text:'Hello',last_message_at:time,unread_count:0,message_count:1}],total:1,page:1,pageSize:20,counts:{all:1,unread_threads:0,unread_messages:0,assigned:0}}});
      if(path==='/api/threads/1')return route.fulfill({json:{user,items:[{id:1,direction:'customer',content_type:'text',content_text:'Hello',created_at:time}]}});
      if(path==='/api/threads/1/reply'){chatWrites.push(request.postDataJSON());return route.fulfill({json:{ok:true}});}
      if(/^\/api\/orders\/\d+\/information$/.test(path))return route.fulfill({json:{requests:[{id:1,body:'Please send current information',status:'waiting',created_at:time,notification_sent:true}],items:[]}});
      if(/^\/api\/orders\/\d+$/.test(path))return route.fulfill({json:orders[Number(path.split('/').at(-1))-1]});
      if(path.startsWith('/api/collaboration/'))return route.fulfill({json:{assignment:{staff_id:null,version:1},notes:[],members:[]}});
      return route.fulfill({json:{items:[{user_id:1,name:user.name,username:'athlete',orders_count:2,active_courses:1,total_spend:2000}],total:1,page:1,pageSize:20,products:[]}});
    });
    await page.route('**/media/**',route=>route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ1sAAAAASUVORK5CYII=','base64')}));
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:3100'}/customers`);
    await page.locator('.customer-profile-action').click();
    const dialog=page.locator('.profile-dialog'),editor=dialog.locator('.record-editor');
    await editor.getByRole('button',{name:lang==='fa'?'ویرایش':'Edit',exact:true}).click();
    await editor.getByRole('button',{name:lang==='fa'?'انتخاب عکس از پرونده':'Choose photos from record'}).click();
    const picker=page.locator('.record-picker');
    await picker.locator('.record-file-thumb img').waitFor();
    assert.ok(await picker.evaluate(element=>element.scrollWidth<=element.clientWidth+1),'file picker overflow');
    await picker.getByRole('button',{name:lang==='fa'?'انتخاب':'Select',exact:true}).click();
    assert.equal(await editor.locator('.record-photo-selection img').count(),1);
    await editor.getByLabel(lang==='fa'?'توضیحات':'Notes',{exact:true}).fill('Edited current profile');
    await editor.getByRole('button',{name:lang==='fa'?'ذخیره تغییرات':'Save changes'}).click();
    await editor.locator('[role=status]').waitFor();
    assert.equal(writes[0].fields.notes,'Edited current profile');
    assert.deepEqual(writes[0].fields.photo_ids,[9]);
    assert.equal(writes[0].version,time);
    assert.equal(writes[0].order_id,undefined);
    assert.equal(orders[0].form_snapshot.notes,'Order 1','profile edit must not change order history');
    await editor.getByRole('button',{name:lang==='fa'?'ویرایش':'Edit',exact:true}).click();
    reject=true;
    await editor.getByLabel(lang==='fa'?'سن':'Age',{exact:true}).fill('101');
    await editor.getByRole('button',{name:lang==='fa'?'ذخیره تغییرات':'Save changes'}).click();
    await editor.locator('[role=alert]').waitFor();
    assert.equal(await editor.getByLabel(lang==='fa'?'سن':'Age',{exact:true}).inputValue(),'101','failed save must preserve the draft');
    reject=false;
    await editor.getByRole('button',{name:lang==='fa'?'انصراف':'Cancel'}).click();
    await dialog.getByRole('button',{name:lang==='fa'?'مقایسه عکس‌های دو دوره':'Compare two courses’ photos'}).click();
    assert.equal(await dialog.locator('.record-photo-compare .profile-gallery').count(),2);
    await dialog.locator('.record-photo-compare').scrollIntoViewIfNeeded();
    assert.ok(await dialog.evaluate(element=>element.scrollWidth<=element.clientWidth+1),'profile overflow');
    if(width!==820)await dialog.screenshot({path:`../artifacts/client-profile-${lang}-${width}.png`});
    await dialog.locator('.profile-order').first().click();
    await dialog.locator('.order-information').waitFor();
    assert.equal(await dialog.getByRole('button',{name:/Start design|شروع طراحی/}).count(),0,'waiting for information must not offer design');
    const orderEditor=dialog.locator('.record-editor');
    await orderEditor.getByRole('button',{name:lang==='fa'?'ویرایش':'Edit',exact:true}).click();
    await orderEditor.getByLabel(lang==='fa'?'توضیحات':'Notes',{exact:true}).fill('Only this order');
    await orderEditor.getByRole('button',{name:lang==='fa'?'ذخیره تغییرات':'Save changes'}).click();
    await orderEditor.locator('[role=status]').waitFor();
    assert.equal(writes.at(-1).order_id,1);
    assert.equal(user.notes,'Edited current profile');
    await orderEditor.getByRole('button',{name:lang==='fa'?'ویرایش':'Edit',exact:true}).click();
    assert.equal(await orderEditor.getByLabel(lang==='fa'?'توضیحات':'Notes',{exact:true}).inputValue(),'Only this order','nested order did not refresh');
    await orderEditor.getByRole('button',{name:lang==='fa'?'انصراف':'Cancel'}).click();
    assert.ok(await dialog.evaluate(element=>element.scrollWidth<=element.clientWidth+1),'order overflow');
    if(width!==820)await dialog.screenshot({path:`../artifacts/client-order-${lang}-${width}.png`});
    if(await dialog.locator('.drawer-mobile-back').isVisible())await dialog.locator('.drawer-mobile-back').click();
    else await dialog.locator('.profile-back').click();
    await dialog.locator('.customer-profile').waitFor();
    // A successful save remains successful even if the subsequent GET fails.
    await editor.getByRole('button',{name:lang==='fa'?'ویرایش':'Edit',exact:true}).click();
    await editor.getByLabel(lang==='fa'?'توضیحات':'Notes',{exact:true}).fill('Saved before refresh failure');
    refreshFailure=true;
    await editor.getByRole('button',{name:lang==='fa'?'ذخیره تغییرات':'Save changes'}).click();
    await editor.locator('[role=status]').waitFor();
    assert.equal(await editor.locator('[role=alert]').count(),0);
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:3100'}/messages`);
    await page.locator('.conversation-row').first().click();
    await page.locator('.chat-notes-dock').getByRole('button',{name:lang==='fa'?'فایل‌های پرونده':'Record files',exact:true}).click();
    await page.locator('.record-picker').getByRole('button',{name:lang==='fa'?'انتخاب':'Select',exact:true}).click();
    await page.locator('.chat-composer__draft').waitFor();
    assert.equal(chatWrites.length,0,'selection must not send immediately');
    assert.ok(await page.locator('.chat-composer').evaluate(element=>element.scrollWidth<=element.clientWidth+1),'chat composer overflow');
    await page.locator('.chat-composer__send').click();
    await page.locator('.chat-composer__draft').waitFor({state:'hidden'});
    assert.equal(chatWrites[0].record_file_id,9);
    assert.deepEqual(errors,[]);
    await page.close();
  }
  console.log('PASS: profile/order separation, versioned save, error/draft feedback, nested refresh, photo comparison and containment at 375/820/1440 FA/EN (mock API)');
}finally{await browser.close();}
