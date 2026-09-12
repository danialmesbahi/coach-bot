// Isolated browser test: all API calls are fixtures, never real staff mutations.
// PLAYWRIGHT_MODULE points to the locally installed Playwright module when needed.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||undefined});
const errors=[];
try {
  for(const width of [390,820,1440]) for(const lang of ['fa','en']) {
    const page=await browser.newPage({viewport:{width,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(lang=>localStorage.setItem('sensi-lang',lang),lang);
    await page.route('**/api/**', async route=>{
      const path=new URL(route.request().url()).pathname;
      const session={role:'platform',telegramId:1001,staffId:1,displayName:'Test owner',username:'test_owner',csrf:'fixture',permissions:['orders.read','orders.review','orders.deliver','chats.read','chats.reply','sales.read','sales.manage','customers.read','payments.review']};
      const fixtures={
        '/api/session':session,
        '/api/dashboard':{role:'platform',counts:{active:0,unread:0},sales:{period:'all',orders:0,revenue:0,trend:[]},salesOpen:true,buyers:0,users:0},
        '/api/staff/team':{items:[{id:2,telegram_id:1002,username:'test_support',display_name:'Support teammate',role:'staff',permissions:['chats.read'],status:'active',session_version:1}],total:1,permissions:{'chats.read':['خواندن پیام‌ها','Read conversations'],'chats.reply':['پاسخ به پیام‌ها','Reply to clients']},templates:{support:['chats.read','chats.reply']}},
        '/api/staff/audit':{items:[],next:null},
      };
      if(path==='/api/events')return route.fulfill({status:200,contentType:'text/event-stream',body:': test\n\n'});
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixtures[path]??{ok:true})});
    });
    await page.goto(process.env.TEST_BASE_URL || 'http://127.0.0.1:8090/');
    await page.getByRole('button',{name:/Profile and team|پروفایل و مدیریت تیم/}).click();
    const dialog=page.locator('.staff-dialog');
    await dialog.waitFor({state:'visible'});
    await page.getByRole('button',{name:/Members|اعضای تیم/,exact:true}).click();
    await page.getByText('Support teammate',{exact:true}).waitFor();
    await page.getByRole('button',{name:/Add member|افزودن همکار/,exact:true}).click();
    await page.locator('.staff-editor').waitFor();
    assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,`dialog overflow ${width}/${lang}`);
    assert.equal(await page.locator('.staff-body').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,`body overflow ${width}/${lang}`);
    assert.equal(await page.locator('.staff-permissions input').count(),2);
    await page.keyboard.press('Escape');
    await dialog.waitFor({state:'hidden'});
    await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: staff workspace, invite form, permissions and modal close at 390/820/1440 px in FA/EN (mock API)');
} finally { await browser.close(); }
