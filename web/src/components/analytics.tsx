"use client";

import { useEffect, useState } from "react";
import { Activity, ChartNoAxesCombined, Clock3, ArrowUpRight, AlertTriangle, CheckCircle2, Download, Info, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Lang, Session, View } from "@/lib/types";
import { ActivityLog } from "./activity-log";
import { SelectMenu } from "./select-menu";

type Counts = Record<string,number|null>;
type Telemetry = {source:string;event:string;dimension:string;outcome:string;count:number;mean_ms:number;slow:number};
type Log = {id:number;created_at:string;actor_name:string|null;action:string;target:string;source:string};
export type AnalyticsData = {
  scope:"personal"|"platform";days:number;from:string;to:string;generated_at:string;
  activity:Counts;logs:{items:Log[];page:number;has_more:boolean};sales?:Counts;operations?:Counts;
  trend?:{day:string;revenue:number;payments:number}[];products?:{product_id:number;title:string;revenue:number;payments:number}[];
  team?:{id:number;display_name:string;role:string;replies:number;deliveries:number;notes:number}[];
  telemetry?:Telemetry[];collectors?:{source:string;started_at:string;last_seen:string;dropped:number}[];
};

const names:Record<string,[string,string]>={
  name:["نام","Name"],phone:["تلفن","Phone"],age:["سن","Age"],gender:["جنسیت","Gender"],height:["قد","Height"],weight:["وزن","Weight"],
  goal:["هدف","Goal"],training_history:["سابقه تمرین","Training history"],allergy:["حساسیت غذایی","Allergies"],restriction:["محدودیت غذایی","Diet restrictions"],
  supplements:["مکمل‌ها","Supplements"],notes:["توضیحات","Notes"],body_photo:["عکس‌های بدن","Body photos"],custom_question:["سؤال سفارشی","Custom question"],
  confirm:["مرور سفارش","Review"],payment_method:["روش پرداخت","Payment method"],receipt:["رسید","Receipt"],submitting:["ثبت سفارش","Submit order"],
  password_login:["ورود با رمز","Password login"],thread_detail:["بازکردن چت","Open chat"],reply_message:["ارسال پیام","Send message"],
  customer_detail:["پرونده شاگرد","Client profile"],order_action:["عملیات سفارش","Order action"],upload_plan:["ارسال برنامه","Send program"],
  purchase:["خرید در بات","Bot checkout"],other:["سایر تعاملات بات","Other bot interactions"],verify:["تأیید درگاه","Payment verification"],
  dashboard:["نمای کلی","Overview"],customers:["شاگردها","Clients"],orders:["کارها","Tasks"],messages:["پیام‌ها","Messages"],catalog:["محصولات","Products"],analytics:["آنالیز","Analytics"],
  session:["بررسی ورود","Session check"],logout:["خروج از پنل","Sign out"],staff_profile:["پروفایل همکار","Staff profile"],staff_password:["تغییر رمز","Password change"],staff_team:["مدیریت همکاران","Team management"],staff_audit:["گزارش فعالیت","Activity log"],
  collaboration:["یادداشت‌های تیم","Team notes"],followups:["پیگیری‌ها","Follow-ups"],followup_seen:["خواندن پیگیری","Read follow-up"],sales_gate:["باز و بسته کردن فروش","Sales availability"],sales:["گزارش فروش","Sales report"],
  catalog_save:["ذخیره دوره","Save product"],catalog_archive:["حذف دوره از فروش","Archive product"],catalog_asset:["آپلود محتوای دوره","Upload content"],catalog_asset_preview:["نمایش محتوای دوره","Preview content"],catalog_channel:["اتصال کانال","Connect channel"],catalog_reorder:["چیدمان دوره‌ها","Reorder products"],
  order_detail:["جزئیات سفارش","Order details"],order_body_photo:["عکس‌های سفارش","Order photos"],order_receipt:["رسید پرداخت","Payment receipt"],customer_body_photo:["عکس‌های شاگرد","Client photos"],customer_avatar:["تصویر پروفایل","Profile photo"],threads:["فهرست گفت‌وگوها","Conversations"],support_message_media:["فایل‌های گفت‌وگو","Chat attachments"],
};

export default function Analytics({session,lang,navigate}:{session:Session;lang:Lang;navigate:(view:View)=>void}) {
  const fa=lang==="fa",manager=session.role!=="staff";
  const [days,setDays]=useState("30"),[scope,setScope]=useState(manager?"platform":"personal");
  const [tab,setTab]=useState("overview"),[refresh,setRefresh]=useState(0);
  const [data,setData]=useState<AnalyticsData>(),[busy,setBusy]=useState(true),[error,setError]=useState("");
  const [series,setSeries]=useState<"payments"|"revenue">("payments");
  const text=(key:string)=>names[key]?.[fa?0:1]??key.replaceAll('_',' ');
  const number=(v:number|null|undefined)=>v==null?"—":new Intl.NumberFormat(fa?"fa-IR":"en",{maximumFractionDigits:1}).format(v);
  const date=(value:string,time=false)=>new Intl.DateTimeFormat(fa?"fa-IR":"en-GB",{timeZone:"Asia/Tehran",month:"short",day:"numeric",...(time?{hour:"2-digit",minute:"2-digit"} as const:{})}).format(new Date(value));
  useEffect(()=>{
    const controller=new AbortController();let active=true;
    const load=async()=>{
      setBusy(true);setError("");
      try{const next=await api<AnalyticsData>(`/api/analytics?days=${days}&scope=${scope}`,session.csrf,{signal:controller.signal});if(active)setData(next);}
      catch(e){if(active&&!controller.signal.aborted)setError(e instanceof ApiError&&e.status===403?(fa?"دسترسی به این بخش مجاز نیست.":"You do not have access."):(fa?"دریافت آمار انجام نشد؛ دوباره تلاش کن.":"Could not load metrics. Try again."));}
      finally{if(active)setBusy(false);}
    };
    void load();return()=>{active=false;controller.abort();};
  },[days,scope,refresh,session.csrf,fa]);
  useEffect(()=>{
    const timer=setInterval(()=>{if(document.visibilityState==="visible")setRefresh(n=>n+1);},60_000);
    return()=>clearInterval(timer);
  },[]);
  const select=(key:"days"|"scope",value:string)=>{if(value===(key==="days"?days:scope))return;setData(undefined);if(key==="days")setDays(value);else{setScope(value);setTab("overview");}};
  const exportData=()=>{
    if(!data)return;
    const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=`sensi-kpi-${data.scope}-${days}d.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  const card=(label:string,value:number|null|undefined,unit="",hint="",delta?:number|null)=><article className="insight-kpi glass"><span>{label}</span><strong>{number(value)} <small>{unit}</small></strong>{delta!=null&&<b className="insight-delta">{delta>0?"+":""}{number(delta)}% <small>{fa?"نسبت به بازه قبل":"vs. previous period"}</small></b>}{hint&&<p>{hint}</p>}</article>;
  const platform=data?.scope==="platform",ops=data?.operations;
  const requests=(data?.telemetry??[]).filter(r=>r.event==="request");
  const total=requests.reduce((sum,r)=>sum+Number(r.count),0),failures=requests.filter(r=>r.outcome==="server_error").reduce((sum,r)=>sum+Number(r.count),0);
  const steps=Object.values((data?.telemetry??[]).filter(r=>r.event==="step").reduce<Record<string,{name:string;advanced:number;waiting:number}>>((all,r)=>{
    const item=all[r.dimension]??={name:r.dimension,advanced:0,waiting:0};if(r.outcome==="advanced"||r.outcome==="waiting")item[r.outcome]+=Number(r.count);return all;
  },{})).sort((a,b)=>b.waiting-a.waiting);
  const sourceName=(source:string)=>({bot:fa?"بات تلگرام":"Telegram bot",web:fa?"وب‌اپ":"Web app",payment:fa?"درگاه پرداخت":"Payments"}[source]??source);
  const issues=(data?.telemetry??[]).filter(r=>["server_error","client_error","blocked"].includes(r.outcome)).sort((a,b)=>Number(b.count)-Number(a.count));
  const slowAreas=Object.values(requests.filter(r=>r.source!=="payment").reduce<Record<string,{source:string;dimension:string;count:number;slow:number;elapsed:number}>>((all,r)=>{
    const key=r.source+":"+r.dimension,item=all[key]??={source:r.source,dimension:r.dimension,count:0,slow:0,elapsed:0};
    item.count+=Number(r.count);item.slow+=Number(r.slow);item.elapsed+=Number(r.mean_ms||0)*Number(r.count);return all;
  },{})).filter(r=>r.slow>0).sort((a,b)=>b.slow-a.slow);
  const roles={platform:fa?"توسعه‌دهنده":"Developer",leader:fa?"مربی":"Coach",staff:fa?"همکار":"Staff"};
  const trend=data?.trend??[],max=Math.max(1,...trend.map(r=>Number(r[series])));
  return <section className="insights-page" aria-busy={busy}>
    <header className="insights-header"><div><ChartNoAxesCombined/><h1>{fa?"گزارش‌ها":"Reports"}</h1></div><div className="insights-actions"><button className="icon-button" aria-label={fa?"به‌روزرسانی":"Refresh"} disabled={busy} onClick={()=>setRefresh(n=>n+1)}>{busy?<LoaderCircle className="spin"/>:<RefreshCw/>}</button><button className="icon-button" disabled={!data} aria-label={fa?"دریافت گزارش JSON":"Download JSON report"} onClick={exportData}><Download/></button></div></header>
    <div className="insights-controls"><div className="insights-periods" role="group" aria-label={fa?"بازه زمانی":"Time range"}>{["7","30","90"].map(d=><button key={d} aria-pressed={days===d} onClick={()=>select("days",d)}>{number(Number(d))} {fa?"روز":"days"}</button>)}</div>{manager?<SelectMenu label={fa?"محدوده آمار":"Scope"} value={scope} options={[["platform",fa?"کل پلتفرم":"Whole platform"],["personal",fa?"عملکرد من":"My performance"]]} onChange={v=>select("scope",v)}/>:<span className="insights-scope"><ShieldCheck/>{fa?"فقط عملکرد خودت":"Your own performance"}</span>}</div>
    <nav className="insights-tabs" aria-label={fa?"بخش‌های آنالیز":"Analytics sections"}>{[["overview",scope==="platform"?(fa?"فروش":"Sales"):(fa?"عملکرد من":"My performance")],...(scope==="platform"?[["experience",fa?"بات و سایت":"Bot & website"]]:[]),["activity",scope==="platform"?(fa?"فعالیت تیم":"Team activity"):(fa?"فعالیت من":"My activity")]].map(([key,label])=><button key={key} aria-current={tab===key?"page":undefined} onClick={()=>setTab(key)}>{key==="overview"?<ChartNoAxesCombined/>:key==="experience"?<Activity/>:<Clock3/>}<span>{label}</span></button>)}</nav>
    <p className="insights-intro">{tab==="overview"?(scope==="platform"?(fa?"فروش، خریدها و کارهای منتظر رسیدگی در بازه انتخاب‌شده.":"Sales, purchases and pending work for the selected period."):(fa?"پاسخ‌ها، برنامه‌های تحویل‌شده و پیگیری‌های حساب خودت.":"Your replies, delivered programs and follow-ups.")):tab==="experience"?(fa?"خطاها، کندی درخواست‌ها و مراحل خرید کاربران را اینجا بررسی کن.":"Review errors, slow requests and customer checkout steps."):scope==="platform"?(fa?"چه کسی چه کاری انجام داده؟ گزارش رویدادها کنار خلاصه کار تیم.":"Who did what? Events alongside each teammate’s contribution."):(fa?"رویدادهای حساب خودت، به ترتیب جدیدترین.":"Your own account activity, newest first.")}</p>
    {error&&<div className="insights-error" role="alert">{error}<button className="button secondary" onClick={()=>setRefresh(n=>n+1)}>{fa?"تلاش مجدد":"Retry"}</button></div>}
    {!data&&!error&&<div className="insights-loading"><LoaderCircle className="spin"/>{fa?"در حال محاسبه شاخص‌ها…":"Calculating metrics…"}</div>}
    {data&&<><div className="insights-fresh"><Clock3/><span>{date(data.from)} — {date(data.to)} · {fa?"به‌روزرسانی":"Updated"} {date(data.generated_at,true)}</span></div>
    {tab==="overview"&&<>{platform?<>
      <section className="insights-work insight-panel glass"><header><div><h2>{fa?"همین حالا نیاز به رسیدگی":"Needs attention now"}</h2><p>{fa?"وضعیت فعلی، مستقل از بازه گزارش":"Current workload, independent of the report period"}</p></div></header><div>
        <button className="insights-queue" onClick={()=>navigate("orders")}><span>{fa?"سفارش باز":"Open orders"}</span><b>{number(ops?.backlog)}</b><ArrowUpRight/></button>
        <button className="insights-queue" onClick={()=>navigate("messages")}><span>{fa?"گفت‌وگوی خوانده‌نشده":"Unread conversations"}</span><b>{number(ops?.unread_chats)}</b><ArrowUpRight/></button>
        <button className="insights-queue" onClick={()=>navigate("orders")}><span>{fa?"مشکل تحویل خودکار":"Automatic delivery issues"}</span><b>{number(ops?.failed_delivery)}</b><ArrowUpRight/></button>
      </div>{Number(ops?.backlog)>0&&<p>{fa?"قدیمی‌ترین سفارش باز: ":"Oldest open order: "}{number(ops?.oldest_hours)} {fa?"ساعت":"hours"}</p>}</section>
      <div className="insights-kpis">{card(fa?"فروش پرداخت‌شده":"Paid revenue",data.sales?.revenue,fa?"تومان":"Toman","",data.sales?.revenue_change)}{card(fa?"درصد سفارش‌های پرداخت‌شده":"Orders paid (%)",data.sales?.conversion,"%",fa?"از فاکتورهای ایجادشده در همین بازه؛ خریدهای تازه هنوز فرصت پرداخت دارند.":"Invoices created in this period; recent invoices may still convert.")}{card(fa?"زمان معمول آماده‌سازی برنامه":"Typical program turnaround",ops?.delivery_hours,fa?"ساعت":"hours",`${fa?"میانه پرداخت تا تحویل؛ تعداد برنامه":"Median payment to delivery; programs"}: ${number(ops?.delivery_sample)}`)}</div>
      <div className="insights-summary">{[[fa?"کاربر جدید":"New users",data.sales?.new_users],[fa?"خریدار":"Buyers",data.sales?.buyers],[fa?"خریدار تکراری":"Repeat buyers",data.sales?.repeat_buyers]].map(([label,value])=><div key={String(label)}><span>{label}</span><b>{number(value as number|null)}</b></div>)}</div>
      <div className="insights-grid"><article className="insight-panel glass insights-trend"><header><h2>{fa?"روند خرید":"Purchase trend"}</h2><div className="insights-switch">{(["payments","revenue"] as const).map(key=><button key={key} aria-pressed={series===key} onClick={()=>setSeries(key)}>{key==="payments"?(fa?"پرداخت":"Payments"):(fa?"تومان":"Toman")}</button>)}</div></header><div className="insights-chart" dir="ltr"><span>{number(max)}</span><svg viewBox="0 0 640 180" role="img" aria-label={fa?"روند روزانه؛ مقادیر در جدول زیر موجود است":"Daily trend; values available in the table below"}><path d="M0 170H640 M0 90H640 M0 10H640" className="insights-gridlines"/><polyline points={trend.map((r,i)=>`${i*636/Math.max(1,trend.length-1)+2},${170-Number(r[series])/max*156}`).join(' ')} /></svg><div>{trend.length>0&&[trend[0],trend[Math.floor(trend.length/2)],trend[trend.length-1]].map((r,i)=><span key={i}>{date(`${r.day}T12:00:00+03:30`)}</span>)}</div></div><details><summary>{fa?"مقادیر روزانه و منبع":"Daily values & source"}</summary><p>{fa?"سفارش‌های دارای پرداخت تأییدشده؛ زمان تهران. روز ابتدا و انتهای بازه ممکن است ناقص باشد.":"Verified paid orders, Tehran time. First and last days may be partial."}</p><div className="insights-table"><table><thead><tr><th>{fa?"روز":"Day"}</th><th>{fa?"پرداخت":"Payments"}</th><th>{fa?"تومان":"Toman"}</th></tr></thead><tbody>{trend.map(r=><tr key={r.day}><td>{date(`${r.day}T12:00:00+03:30`)}</td><td>{number(r.payments)}</td><td>{number(r.revenue)}</td></tr>)}</tbody></table></div></details></article>
      <article className="insight-panel glass"><h2>{fa?"از ثبت سفارش تا تحویل":"From order to delivery"}</h2><p>{fa?"از سفارش‌هایی که در این بازه ثبت شده‌اند، چند مورد پرداخت و تحویل شده؟":"Of orders placed in this period, how many were paid and delivered?"}</p>{[[fa?"فاکتور ایجادشده":"Invoices",data.sales?.invoices],[fa?"پرداخت تأییدشده":"Paid",data.sales?.converted],[fa?"تحویل‌شده":"Delivered",data.sales?.delivered]].map(([label,value])=><div className="insights-funnel" key={String(label)}><div><span>{label}</span><strong>{number(value as number|null)}</strong></div><progress max={data.sales?.invoices||1} value={Number(value||0)} aria-label={String(label)}/></div>)}</article>
      <article className="insight-panel glass insights-products"><h2>{fa?"فروش به تفکیک محصول":"Revenue by product"}</h2><div className="insights-table"><table><thead><tr><th>{fa?"محصول":"Product"}</th><th>{fa?"پرداخت":"Paid"}</th><th>{fa?"تومان":"Toman"}</th></tr></thead><tbody>{data.products?.map(p=><tr key={p.product_id}><td>{p.title}</td><td>{number(p.payments)}</td><td>{number(p.revenue)}</td></tr>)}</tbody></table></div>{!data.products?.length&&<p>{fa?"پرداختی در این بازه ثبت نشده.":"No payments in this period."}</p>}<p>{fa?"۱۰ محصول نخست بر اساس فروش؛ نام فعلی محصول نمایش داده می‌شود.":"Top 10 by revenue; current product names are shown."}</p></article></div>
    </>:<><div className="insights-kpis">{card(fa?"پیام‌های ارسال‌شده":"Replies sent",data.activity.replies,"","",data.activity.replies_change)}{card(fa?"برنامه تحویل‌شده":"Programs delivered",data.activity.deliveries)}{card(fa?"پیگیری دیده‌نشده":"Unseen follow-ups",data.activity.unseen)}</div><div className="insight-panel glass insights-personal"><ShieldCheck/><div><h2>{session.displayName}</h2><p>{fa?"این آمار فقط فعالیت‌های ثبت‌شدهٔ حساب خودت است؛ تعداد پیام، معیار کیفیت پاسخ نیست.":"Only your account’s recorded activity. Message volume is not a quality score."}</p><div className="insights-summary"><div>{fa?"شاگرد پاسخ‌گرفته":"Clients replied to"}<b>{number(data.activity.clients)}</b></div><div>{fa?"یادداشت":"Notes"}<b>{number(data.activity.notes)}</b></div><div>{fa?"اقدام روی سفارش":"Order actions"}<b>{number(data.activity.order_actions)}</b></div></div></div></div></>
    }</>}
    {tab==="experience"&&platform&&<>
      <section className="insights-coverage insight-panel glass">
        <header><div><h2>{fa?"داده‌ها چقدر به‌روزند؟":"Are reports up to date?"}</h2><p>{fa?"وضعیت جمع‌آوری آمار؛ نه تضمین آنلاین بودن سرویس.":"Collection status, not a service uptime guarantee."}</p></div></header>
        <div className="insights-collectors">{["bot","web"].map(source=>{
          const collector=data.collectors?.find(c=>c.source===source);
          const fresh=collector&&Date.parse(data.generated_at)-Date.parse(collector.last_seen)<120000;
          return <div key={source}><i className={fresh?"fresh":"stale"}/><div><strong>{sourceName(source)}</strong><span>{!collector?(fa?"هنوز گزارشی دریافت نشده":"No report received yet"):fresh?(fa?"آمار در حال دریافت است":"Reports arriving"):(fa?"دریافت آمار متوقف یا با تأخیر است":"Reports delayed or stopped")}</span><small>{collector?`${fa?"آخرین دریافت":"Last received"}: ${date(collector.last_seen,true)}`:fa?"با شروع فعالیت، وضعیت نمایش داده می‌شود.":"Status appears when reporting starts."}</small>{!!collector?.dropped&&<small>{fa?"رخداد ثبت‌نشده؛ آمار ممکن است ناقص باشد: ":"Dropped events; counts may be incomplete: "}{number(collector.dropped)}</small>}</div></div>;
        })}</div>
      </section>
      <div className="insights-kpis">{card(fa?"درخواست ثبت‌شده":"Recorded requests",total,"",fa?"تعداد تعاملات فنی، نه تعداد کاربران":"Technical interactions, not unique people")}{card(fa?"درخواست با خطای سرور":"Server request failures",failures,"",total?`${number(failures/total*100)}% ${fa?"از درخواست‌ها":"of requests"}`:fa?"هنوز داده‌ای برای ارزیابی نیست":"No requests to evaluate yet")}{card(fa?"پاسخ دیرتر از ۲ ثانیه":"Responses over 2 seconds",requests.reduce((sum,r)=>sum+Number(r.slow),0),"",fa?"کندی لزوماً به معنی ناموفق بودن نیست":"A slow response is not necessarily a failure")}</div>
      <div className="insights-grid insights-health-grid">
        <article className="insight-panel glass"><header><div><h2>{fa?"کجا خطا ثبت شده؟":"Where did errors occur?"}</h2><p>{fa?"۱۰ مورد پرتکرار در بازه انتخاب‌شده":"10 most frequent groups in this period"}</p></div><AlertTriangle/></header>
          {issues.length?<ul className="insights-diagnostics">{issues.slice(0,10).map((r,i)=><li key={i}><div><strong>{text(r.dimension)}</strong><span>{sourceName(r.source)} · {r.event==="client"?(fa?"خطای مرورگر":"Browser error"):r.outcome==="server_error"?(fa?"خطای سرویس":"Service error"):r.outcome==="blocked"?(fa?"محدودیت درخواست":"Rate limited"):(fa?"درخواست ردشده":"Rejected request")}</span></div><b>{number(r.count)}<small>{fa?"رخداد":"events"}</small></b></li>)}</ul>:<div className="insights-empty"><CheckCircle2/><strong>{fa?"خطایی ثبت نشده":"No recorded errors"}</strong><p>{fa?"اگر دریافت آمار متوقف باشد، نبود خطا به معنی سلامت کامل نیست.":"If reporting is interrupted, no errors does not prove everything is healthy."}</p></div>}
          <p>{fa?"خطای سرویس را با تیم توسعه بررسی کن. درخواست ردشده ممکن است فقط ورودی نامعتبر یا نداشتن دسترسی باشد. جزئیات بیشتر در خروجی گزارش است.":"Review service errors with development. Rejected requests can be invalid input or missing permissions. Export includes all groups."}</p>
        </article>
        <article className="insight-panel glass"><header><div><h2>{fa?"کدام بخش کند است؟":"Which areas are slow?"}</h2><p>{fa?"۸ مسیر با بیشترین پاسخ کند":"8 areas with the most slow responses"}</p></div><Clock3/></header>
          {slowAreas.length?<ul className="insights-diagnostics">{slowAreas.slice(0,8).map(r=><li key={r.source+r.dimension}><div><strong>{text(r.dimension)}</strong><span>{sourceName(r.source)} · {fa?"میانگین همه پاسخ‌ها":"Mean of all responses"}: {number(r.elapsed/r.count)} ms</span></div><b>{number(r.slow)}<small>{fa?"پاسخ کند":"slow responses"}</small></b></li>)}</ul>:<div className="insights-empty"><CheckCircle2/><strong>{fa?"کندی ثبت نشده":"No recorded slow responses"}</strong><p>{fa?"در مسیرهای اندازه‌گیری‌شدهٔ بات و وب‌اپ.":"For measured bot and web API requests."}</p></div>}
          <p>{fa?"میانگین، زمان معمول هر کاربر نیست. این گزارش مصرف CPU، قطعی کامل سرور و همه خطاهای شبکه را اندازه نمی‌گیرد.":"Mean time is not each user’s experience. This report does not measure CPU, full outages or all network failures."}</p>
        </article>
      </div>
      <article className="insight-panel glass"><header><div><h2>{fa?"کاربر در فرم خرید چه می‌کند؟":"What happens in the purchase form?"}</h2><p>{fa?"هر عدد یک تعامل است. ماندن در مرحله می‌تواند برای تایپ یا افزودن عکس باشد؛ این آمار ریزش کاربران نیست.":"Counts are interactions. Staying can mean typing or adding photos; these are not abandonment rates."}</p></div></header>
        {steps.length?<div className="insights-steps">{steps.map(s=><div key={s.name}><strong>{text(s.name)}</strong><dl><div><dt>{fa?"تغییر مرحله":"Changed step"}</dt><dd>{number(s.advanced)}</dd></div><div><dt>{fa?"ادامه در همین مرحله":"Stayed on step"}</dt><dd>{number(s.waiting)}</dd></div></dl></div>)}</div>:<p className="insights-empty">{fa?"هنوز تعاملی با فرم خرید در این بازه ثبت نشده.":"No purchase form interactions recorded in this period."}</p>}
      </article>
      <p className="insights-note"><Info/>{fa?"آمار فنی از زمان فعال‌سازی جمع می‌شود و تا ۱۰۰ روز نگهداری می‌شود؛ در زمان قطعی ممکن است ناقص باشد.":"Technical reports start at activation and are retained for 100 days; outages can leave gaps."}</p>
    </>}
    {tab==="activity"&&<><div className={platform?"insights-activity-layout":""}><ActivityLog key={`${scope}-${days}`} session={session} lang={lang} days={days} scope={scope}/>{platform&&<aside className="insight-panel glass insights-team"><h2>{fa?"سهم هر همکار در کار تیم":"Team contributions"}</h2><p>{fa?"در بازه انتخاب‌شده؛ تعداد فعالیت، امتیاز کیفیت نیست. تا ۵۰ حساب فعال به ترتیب نام.":"For this period. Activity counts are not quality scores. Up to 50 active accounts, ordered by name."}</p>
      <ul>{data.team?.map(member=><li key={member.id}><header><strong>{member.display_name}</strong><small>{roles[member.role as keyof typeof roles]??member.role}</small></header><dl>{[[fa?"پاسخ":"Replies",member.replies],[fa?"تحویل":"Delivered",member.deliveries],[fa?"یادداشت":"Notes",member.notes]].map(([label,value])=><div key={String(label)}><dt>{label}</dt><dd>{number(Number(value))}</dd></div>)}</dl></li>)}</ul>{!data.team?.length&&<p>{fa?"حساب فعالی برای نمایش نیست.":"No active team accounts to show."}</p>}
    </aside>}</div></>}
    {tab==="overview"&&<details className="insights-definitions"><summary><Info/>{fa?"تعریف شاخص‌ها و دسترسی":"Metric definitions & access"}</summary><p>{fa?"فروش: جمع مبلغ سفارش‌های پرداخت‌شده در بازه، به تومان و پیش از کسر سهم تیم. تبدیل: نسبت فاکتورهای پرداخت‌شده به تمام فاکتورهای ساخته‌شده در همان بازه. خریدار تکراری: خرید در بازه با حداقل یک پرداخت قدیمی‌تر. تحویل: میانهٔ فاصله پرداخت تا تحویل برنامه اختصاصی؛ محتوای فوری جداست.":"Revenue: paid order amounts in Toman before team share. Conversion: paid invoices divided by invoices created in the same period. Repeat buyer: a buyer with an earlier paid order. Delivery: median payment-to-delivery time for custom programs, excluding instant content."}</p><p>{fa?"مربی و توسعه: آمار کل؛ همکار: فقط آمار حساب خودش با مجوز analytics.self. منابع: سفارش‌ها، پیام‌های ثبت‌شده، لاگ فعالیت و شمارنده‌های تجمیعی. به‌روزرسانی تا هر ۶۰ ثانیه در صفحهٔ فعال؛ اهداف عددی بدون سابقهٔ معتبر تعیین نشده‌اند.":"Coach/development: platform metrics. Staff: own activity with analytics.self permission. Sources: orders, recorded messages, audit trail and aggregated counters. Refreshes every 60 seconds while visible; no unevidenced targets are imposed."}</p></details>}
    </>}
  </section>;
}
