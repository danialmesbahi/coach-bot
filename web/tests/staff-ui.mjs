// Isolated browser test: all API calls are fixtures, never real staff mutations.
// PLAYWRIGHT_MODULE points to the locally installed Playwright module when needed.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||undefined});
const errors=[];
try {
  for(const lang of ['fa','en']) {
    const page=await browser.newPage({viewport:{width:390,height:844}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(lang=>localStorage.setItem('sensi-lang',lang),lang);
    let attempts=0;
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/api/auth/password'){
        attempts++;
        assert.deepEqual(route.request().postDataJSON(),{username:'example',password:'Example1!'});
        assert.equal(route.request().headers()['x-login-request'],'1');
      }
      await route.fulfill({status:401,contentType:'application/json',body:'{"error":"unauthorized"}'});
    });
    await page.goto(process.env.TEST_BASE_URL || 'http://127.0.0.1:8090/');
    await page.locator('input[autocomplete=username]').fill('example');
    await page.locator('input[autocomplete=current-password]').fill('Example1!');
    const passwordControl=page.locator('.password-control');
    await page.getByRole('button',{name:/نمایش رمز|Show password/}).click();
    assert.equal(await passwordControl.locator('input').getAttribute('type'),'text');
    await passwordControl.locator('input').focus();
    assert.notEqual(await passwordControl.evaluate(el=>getComputedStyle(el).boxShadow),'none');
    await page.getByRole('button',{name:/^ورود$|^Sign in$/}).click();
    await page.locator('.login-card').getByRole('alert').waitFor();
    assert.equal(attempts,1);
    assert.equal(await page.locator('a[href*="t.me"],script[src*="telegram"]').count(),0);
    assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth<=innerWidth+1),true);
    await page.close();
  }
  for(const width of [390,820,1440]) for(const lang of ['fa','en']) {
    const page=await browser.newPage({viewport:{width,height:900}});
    let logoutAttempts=0;
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(lang=>localStorage.setItem('sensi-lang',lang),lang);
    await page.route('**/api/**', async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/api/logout')logoutAttempts++;
      const session={role:'platform',telegramId:1001,staffId:1,displayName:'Test owner',username:'test_owner',csrf:'fixture',permissions:['orders.read','orders.review','orders.deliver','chats.read','chats.reply','sales.read','sales.manage','customers.read','payments.review']};
      const fixtures={
        '/api/session':session,
        '/api/dashboard':{role:'platform',counts:{active:0,unread:0},sales:{period:'all',orders:0,revenue:0,trend:[]},salesOpen:true,buyers:0,users:0},
        '/api/staff/team':{items:[{id:2,telegram_id:1002,username:'test_support',display_name:'Support teammate',role:'staff',permissions:['chats.read'],status:'active',session_version:1}],total:25,permissions:{'chats.read':['خواندن پیام‌ها','Read conversations'],'chats.reply':['پاسخ به پیام‌ها','Reply to clients']},templates:{support:['chats.read','chats.reply']}},
        '/api/staff/audit':{items:[{id:1,actor_name:'Test owner',actor_role:'platform',action:'staff_permissions',target_type:'staff',target_id:2,target_name:'Support teammate',created_at:'2026-09-13T10:00:00Z'}],next:null},
      };
      if(path==='/api/events')return route.fulfill({status:200,contentType:'text/event-stream',body:': test\n\n'});
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixtures[path]??{ok:true})});
    });
    await page.goto(process.env.TEST_BASE_URL || 'http://127.0.0.1:8090/');
    await page.getByRole('button',{name:/Secure logout|خروج امن/,exact:true}).click();
    await page.getByRole('alertdialog').waitFor();
    assert.equal(logoutAttempts,0,'dashboard logout must wait for explicit confirmation');
    await page.getByRole('button',{name:/Stay signed in|ماندن/,exact:true}).click();
    assert.equal(logoutAttempts,0);
    await page.getByRole('button',{name:/Profile and team|پروفایل و مدیریت تیم/}).click();
    const dialog=page.locator('.staff-dialog');
    await dialog.waitFor({state:'visible'});
    const dialogHeight=await dialog.evaluate(el=>el.getBoundingClientRect().height);
    await page.getByRole('button',{name:/Members|اعضای تیم/,exact:true}).click();
    await page.getByText('Support teammate',{exact:true}).waitFor();
    assert.equal(await dialog.evaluate(el=>el.getBoundingClientRect().height),dialogHeight,'tab switch must not resize the dialog');
    assert.equal(await page.locator('.staff-pager').count(),1);
    await page.getByRole('button',{name:/Add member|افزودن همکار/,exact:true}).click();
    await page.locator('.staff-editor').waitFor();
    assert.equal(await page.locator('.staff-pager').count(),0,'pager must not remain active behind member editor');
    assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,`dialog overflow ${width}/${lang}`);
    assert.equal(await page.locator('.staff-body').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,`body overflow ${width}/${lang}`);
    assert.equal(await page.locator('.staff-permissions input').count(),2);
    const menu=page.locator('.staff-editor .select-menu');
    const editorHeight=await page.locator('.staff-editor').evaluate(el=>el.getBoundingClientRect().height);
    await menu.getByRole('button',{name:/Account level|سطح حساب/}).click();
    const options=menu.getByRole('listbox');
    await options.waitFor({state:'visible'});
    assert.equal(await options.getByRole('option').count(),3);
    assert.equal(await page.locator('.staff-editor').evaluate(el=>el.getBoundingClientRect().height),editorHeight,'role menu must float without shifting the form');
    assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    if(process.env.SAVE_SCREENSHOTS==='1'&&width===390)await page.screenshot({path:`../artifacts/staff-password-${lang}.png`});
    await page.keyboard.press('Escape');
    assert.equal(await dialog.isVisible(),true,'Escape closes menu, not entire dialog');
    await page.getByRole('button',{name:/Cancel|لغو/,exact:true}).click();
    await page.getByRole('button',{name:/Reset password|تعیین رمز جدید/,exact:true}).click();
    assert.equal(await page.locator('.staff-editor input[type=password]').count(),1);
    await page.getByRole('button',{name:/Cancel|لغو/,exact:true}).click();
    await page.getByRole('button',{name:/Activity log|گزارش فعالیت/,exact:true}).click();
    await page.getByText('Support teammate',{exact:true}).waitFor();
    await page.getByRole('button',{name:/My profile|پروفایل من/,exact:true}).click();
    const passwordInput=page.locator('.password-control input').last();
    await passwordInput.focus();
    assert.match(await passwordInput.locator('..').evaluate(el=>getComputedStyle(el).boxShadow),/rgb|rgba/,'password focus belongs to the whole control');
    await page.getByRole('button',{name:/Sign out|خروج از حساب/,exact:true}).click();
    await page.getByRole('alertdialog').waitFor();
    await page.getByRole('button',{name:/Stay signed in|ماندن/,exact:true}).click();
    assert.equal(await page.getByRole('alertdialog').count(),0);
    if(width===390){
      await page.locator('input[autocomplete=current-password]').fill('Current1!');
      await page.locator('input[autocomplete=new-password]').fill('weak');
      await page.getByRole('button',{name:/Save password|ذخیره رمز/}).click();
      await page.locator('.field-error').waitFor();
      await page.locator('input[autocomplete=new-password]').fill('Changed1!');
      await page.getByRole('button',{name:/Save password|ذخیره رمز/}).click();
      await page.locator('.staff-feedback.success').waitFor();
    }
    await page.keyboard.press('Escape');
    await dialog.waitFor({state:'hidden'});
    await page.close();
  }
  {
    const page=await browser.newPage({viewport:{width:390,height:844}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>localStorage.setItem('sensi-lang','en'));
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      const session={role:'platform',telegramId:1001,staffId:1,displayName:'Test owner',username:'test_owner',csrf:'fixture',permissions:['customers.read','chats.read','chats.reply']};
      const fixtures={
        '/api/session':session,
        '/api/threads':{items:[{user_id:9,name:'Test client',username:'client',message_count:1,unread_count:0,last_content_text:'Hello'}],total:1,page:1,pageSize:25,counts:{all:1,unread_threads:0,unread_messages:0}},
        '/api/threads/9':{user:{id:9,telegram_id:9009,name:'Test client',username:'client'},items:[{id:1,direction:'customer',content_text:'Hello',content_type:'text',created_at:'2026-09-13T10:00:00Z'}]},
        '/api/customers/9':{user:{id:9,telegram_id:9009,name:'Test client',username:'client',created_at:'2026-09-13T10:00:00Z',photo_count:0},orders:[],history:[],messages:[]},
        '/api/collaboration/thread/9':{assignment:{staff_id:null,version:1},notes:[{id:1,author_name:'Support teammate',body:'Call tomorrow',created_at:'2026-09-13T10:00:00Z'}],members:[]},
      };
      if(path==='/api/events')return route.fulfill({status:200,contentType:'text/event-stream',body:': test\n\n'});
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixtures[path]??{ok:true})});
    });
    await page.goto(`${process.env.TEST_BASE_URL || 'http://127.0.0.1:8090'}/messages`);
    await page.getByRole('button',{name:'Open conversation: Test client'}).click();
    await page.getByRole('button',{name:'Open Test client profile'}).click();
    await page.locator('.customer-profile').waitFor();
    const profileNotes=page.locator('.profile-dialog .drawer-inner>header .collaboration-panel summary');
    assert.match(await profileNotes.getAttribute('aria-label'),/team notes/i);
    await profileNotes.click();
    await page.locator('.profile-dialog .collaboration-assignment').waitFor();
    await page.getByText('Call tomorrow',{exact:true}).waitFor();
    await page.locator('.profile-dialog .drawer-mobile-back').click();
    await page.locator('.chat-shell').waitFor();
    const chatNotes=page.locator('.chat-dialog .drawer-inner>header .collaboration-panel summary');
    await chatNotes.click();
    await page.getByText('Call tomorrow',{exact:true}).waitFor();
    await chatNotes.click();
    await page.setViewportSize({width:1440,height:900});
    const [notesBox,closeBox]=await Promise.all([chatNotes.boundingBox(),page.locator('.chat-dialog .drawer-desktop-close').boundingBox()]);
    assert.ok(notesBox&&closeBox&&notesBox.x+notesBox.width<=closeBox.x||closeBox&&notesBox&&closeBox.x+closeBox.width<=notesBox.x,'team notes must not overlap the drawer close button');
    await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: staff workspace, confirmed logout, chat-to-profile navigation and shared notes at 390/820/1440 px in FA/EN (mock API)');
} finally { await browser.close(); }
