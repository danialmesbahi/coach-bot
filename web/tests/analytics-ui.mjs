// Deterministic API fixtures; no real activity, payments or accounts are created.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||undefined});
const errors=[];
try {
  for(const lang of ['fa','en']) for(const width of [375,820,844,1440]) {
    const page=await browser.newPage({viewport:{width,height:width===844?390:900},reducedMotion:'reduce'});
    page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(({lang,width})=>{localStorage.setItem('sensi-lang',lang);localStorage.setItem('sensi-theme',width===820?'light':'dark');},{lang,width});
    const now=new Date().toISOString();let lastQuery,requests=0,empty=false,role='leader',fail=false;
    const activity={replies:15,deliveries:3,unseen:2,clients:7,notes:4,order_actions:9};
    await page.route('**/api/**',async route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/events')return route.fulfill({status:200,contentType:'text/event-stream',body:': fixture\n\n'});
      if(url.pathname==='/api/session')return route.fulfill({json:{role,staffId:1,displayName:'Coach',username:'coach',csrf:'fixture',permissions:['analytics.self']}});
      if(url.pathname==='/api/analytics'){
        requests++;lastQuery=url.searchParams;
        if(fail)return route.fulfill({status:503,json:{error:'unavailable'}});
        if(lastQuery.get('section')==='activity')return route.fulfill({json:{items:[{id:1,source:'message',created_at:now,actor_name:'Admin 2',actor_role:'staff',action:'reply_sent',target:'thread',target_id:9,category:'messages'},{id:2,source:'audit',created_at:now,actor_name:'Coach',actor_role:'leader',action:'product_saved',target:'product',target_id:1,category:'team'},{id:3,source:'audit',created_at:now,actor_name:'Coach',actor_role:'leader',action:'staff_login',target:'staff',target_id:1,category:'login'}].filter(r=>lastQuery.get('category')==='all'||r.category===lastQuery.get('category')),page:1,has_more:false}});
        const personal=lastQuery.get('scope')==='personal';
        return route.fulfill({json:{scope:personal?'personal':'platform',days:30,from:now,to:now,generated_at:now,activity,
          logs:{items:[{id:1,source:'audit',created_at:now,actor_name:'Coach',action:'staff_login'}],page:1,has_more:false},
          ...(!personal?{sales:{revenue:12000000,revenue_change:15,conversion:80,new_users:18,buyers:12,repeat_buyers:3,invoices:15,converted:12,delivered:8},
          operations:{delivery_hours:24,delivery_sample:8,backlog:3,unread_chats:2,failed_delivery:0,oldest_hours:36},
          trend:Array.from({length:30},(_,i)=>({day:`2026-09-${String(i+1).padStart(2,'0')}`,payments:i%5,revenue:i%5*1000000})),
          products:[{product_id:1,title:'Training program',revenue:12000000,payments:12}],team:[{id:1,display_name:'Coach',role:'leader',replies:15,deliveries:3,notes:4}],
          collectors:empty?[]:[{source:'web',last_seen:now,started_at:now,dropped:0},{source:'bot',last_seen:'2020-01-01T00:00:00Z',started_at:now,dropped:4}],telemetry:empty?[]:[{source:'web',event:'request',dimension:'orders',outcome:'ok',count:200,mean_ms:30,slow:0},{source:'web',event:'request',dimension:'orders',outcome:'server_error',count:2,mean_ms:6000,slow:2},{source:'web',event:'client',dimension:'messages',outcome:'server_error',count:3,mean_ms:0,slow:0},{source:'bot',event:'step',dimension:'weight',outcome:'waiting',count:3,mean_ms:0,slow:0}]}:{})}});
      }
      return route.fulfill({json:{ok:true}});
    });
    await page.goto(`${process.env.TEST_BASE_URL||'http://127.0.0.1:8091'}/analytics`);
    await page.locator('.insight-kpi').first().waitFor();
    assert.equal(await page.locator('.page-progress').count(),0,'shell must not stay in a loading state');
    assert.ok(requests<=2,'at most the Strict Mode development replay; no render-triggered request loop');
    await page.locator('.insights-periods button[aria-pressed=true]').click();
    assert.equal(await page.locator('.insight-kpi').count(),3,'reselecting the current period must preserve the metrics');
    const overflow=()=>page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
    assert.equal(await overflow(),false,`overflow ${lang} ${width}`);
    if(width===375&&lang==='fa')await page.screenshot({path:'../artifacts/analytics-mobile.png',fullPage:true});
    if(width===1440&&lang==='en')await page.screenshot({path:'../artifacts/analytics-desktop.png',fullPage:true});
    await page.locator('.insights-tabs button').nth(1).click();
    await page.locator('.insights-collectors').waitFor();
    assert.equal(await overflow(),false);
    assert.equal(await page.locator('.insights-collectors .stale').count(),1,'stale collector must not look healthy');
    assert.equal(await page.locator('.insights-health-grid details').count(),0,'no technical accordion');
    assert.equal(await page.locator('.insights-diagnostics').first().locator('li').count(),2);
    assert.match(await page.locator('.insights-diagnostics').last().innerText(),/89[.,]1|۸۹٫۱/,'mean combines outcomes weighted by request count');
    if(width===375||width===1440)await page.screenshot({path:`../artifacts/health-${lang}-${width}.png`,fullPage:true});
    empty=true;
    await page.getByRole('button',{name:lang==='fa'?'به‌روزرسانی':'Refresh',exact:true}).click();
    await page.getByText(lang==='fa'?'هنوز گزارشی دریافت نشده':'No report received yet',{exact:true}).first().waitFor();
    assert.equal(await page.locator('.insights-collectors .fresh').count(),0,'no data is unknown, not green');
    assert.ok(await page.getByText(lang==='fa'?'خطایی ثبت نشده':'No recorded errors',{exact:true}).isVisible());
    assert.equal(await overflow(),false);
    empty=false;
    await page.locator('.insights-tabs button').last().click();
    await page.getByText(lang==='fa'?'ارسال پیام':'Message sent',{exact:true}).waitFor();
    assert.ok(await page.getByText(lang==='fa'?'ذخیره محصول':'Product saved',{exact:true}).isVisible());
    if(width===375||width===1440)await page.screenshot({path:`../artifacts/activity-${lang}-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:lang==='fa'?'نوع فعالیت':'Activity type',exact:true}).click();
    await page.getByRole('option',{name:lang==='fa'?'ورودها':'Sign-ins',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.activity-report').getAttribute('aria-busy')==='false');
    await page.getByText(lang==='fa'?'ورود به پنل':'Signed in',{exact:true}).waitFor();
    assert.equal(await page.getByText(lang==='fa'?'ارسال پیام':'Message sent',{exact:true}).count(),0);
    assert.equal(lastQuery.get('category'),'login');
    await page.getByRole('button',{name:lang==='fa'?'محدوده آمار':'Scope',exact:true}).click();
    await page.getByRole('option',{name:lang==='fa'?'عملکرد من':'My performance',exact:true}).click();
    await page.locator('.insights-personal').waitFor();
    assert.equal(await page.locator('.insights-tabs button').count(),2);
    assert.equal(await page.locator('.insights-chart').count(),0);
    assert.equal(await overflow(),false);
    if(width===375){
      role='staff';await page.reload();
      await page.locator('.insights-personal').waitFor();
      assert.equal(await page.locator('.insights-tabs button').count(),2);
      assert.equal(await page.getByRole('button',{name:lang==='fa'?'محدوده آمار':'Scope',exact:true}).count(),0);
      fail=true;await page.getByRole('button',{name:lang==='fa'?'به‌روزرسانی':'Refresh',exact:true}).click();
      await page.locator('.insights-error').waitFor();
      fail=false;await page.getByRole('button',{name:lang==='fa'?'تلاش مجدد':'Retry',exact:true}).click();
      await page.locator('.insights-error').waitFor({state:'hidden'});
    }
    await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: analytics FA/EN 375/820/844 landscape/1440, light/dark, role isolation, weighted response time, stale/empty/error/retry states, activity filter, no horizontal overflow (mock API)');
} finally {await browser.close();}
