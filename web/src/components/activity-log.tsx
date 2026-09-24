"use client";

import {useEffect,useState} from "react";
import {Activity,ArrowLeft,ArrowRight,LoaderCircle,MessageCircle,RefreshCw} from "lucide-react";
import {api} from "@/lib/api";
import type {Lang,Session} from "@/lib/types";
import {SelectMenu} from "./select-menu";

const actions:Record<string,[string,string]>={
  staff_login:["ورود به پنل","Signed in"],reply_sent:["ارسال پیام","Message sent"],
  staff_profile:["ویرایش نام نمایشی","Display name updated"],staff_password_changed:["تغییر رمز عبور","Password changed"],
  staff_create:["افزودن همکار","Member added"],staff_permissions:["تغییر دسترسی همکار","Permissions updated"],
  staff_disable:["غیرفعال‌کردن حساب","Account disabled"],staff_enable:["فعال‌کردن حساب","Account enabled"],
  staff_reset_password:["بازنشانی رمز همکار","Member password reset"],staff_revoke:["خروج نشست‌های همکار","Member sessions revoked"],
  internal_note:["ثبت یادداشت تیم","Team note added"],assigned:["تغییر مسئول پیگیری","Follow-up assignment updated"],
  product_saved:["ذخیره محصول","Product saved"],product_archived:["بایگانی محصول","Product archived"],products_reordered:["تغییر چیدمان محصولات","Products reordered"],product_reordered:["تغییر چیدمان محصول","Product reordered"],
  product_asset_uploaded:["آپلود فایل دوره","Course file uploaded"],channel_connected:["اتصال کانال خصوصی","Private channel connected"],
  web_sales_gate:["تغییر وضعیت فروش","Sales availability updated"],web_approve_receipt:["تأیید رسید پرداخت","Receipt approved"],
  web_reject_receipt:["رد رسید پرداخت","Receipt rejected"],approve_card_payment:["تأیید رسید پرداخت","Receipt approved"],reject_card_payment:["رد رسید پرداخت","Receipt rejected"],
  web_in_progress:["شروع طراحی برنامه","Program design started"],web_needs_info:["درخواست اطلاعات بیشتر","More information requested"],web_deliver_plan:["تحویل برنامه","Program delivered"],
  delivery_retry_requested:["درخواست تلاش مجدد تحویل","Delivery retry requested"],zarinpal_paid:["تأیید پرداخت زرین‌پال","ZarinPal payment verified"],
};
export const activityName=(action:string,fa:boolean)=>actions[action]?.[fa?0:1]??`${fa?"فعالیت":"Activity"}: ${action.replaceAll("_"," ")}`;
type Entry={id:number;source:string;action:string;actor_name:string|null;actor_role:string|null;target:string;target_id:number;created_at:string};
type Feed={items:Entry[];page:number;has_more:boolean};

/** One report for analytics and the team profile: same source, labels and scope rules. */
export function ActivityLog({session,lang,days="30",scope=session.role==="staff"?"personal":"platform",showPeriod=false}:{session:Session;lang:Lang;days?:string;scope?:string;showPeriod?:boolean}){
  const fa=lang==="fa";
  const [period,setPeriod]=useState(days),[category,setCategory]=useState("all"),[page,setPage]=useState(1),[refresh,setRefresh]=useState(0);
  const [data,setData]=useState<Feed>(),[busy,setBusy]=useState(true),[error,setError]=useState(false);
  const effectiveDays=showPeriod?period:days;
  useEffect(()=>{
    const controller=new AbortController();
    const load=async()=>{
      setBusy(true);setError(false);
      try{const value=await api<Feed>(`/api/analytics?section=activity&scope=${scope}&days=${effectiveDays}&category=${category}&page=${page}`,session.csrf,{signal:controller.signal});if(!controller.signal.aborted)setData(value);}
      catch{if(!controller.signal.aborted)setError(true);}
      finally{if(!controller.signal.aborted)setBusy(false);}
    };
    void load();
    return()=>controller.abort();
  },[scope,effectiveDays,category,page,refresh,session.csrf]);
  useEffect(()=>{const timer=setInterval(()=>{if(document.visibilityState==="visible")setRefresh(n=>n+1);},60_000);return()=>clearInterval(timer);},[]);
  const role=(value:string|null)=>({platform:fa?"توسعه‌دهنده":"Developer",leader:fa?"مربی":"Coach",staff:fa?"همکار":"Staff"}[value??""]??(fa?"سیستم / سابقه قدیمی":"System / legacy"));
  const target=(entry:Entry)=>({staff:fa?"حساب همکار":"Team account",order:fa?"سفارش":"Order",thread:fa?"گفت‌وگو":"Conversation",customer:fa?"شاگرد":"Client",product:fa?"محصول":"Product",sales:fa?"فروش":"Sales",catalog:fa?"ویترین":"Storefront"}[entry.target]??entry.target)+(entry.target_id?` #${entry.target_id}`:"");
  return <section className="activity-report" aria-busy={busy}>
    <header><div><h2>{fa?"گزارش فعالیت":"Activity log"}</h2><p>{fa?"چه کسی، چه کاری و چه زمانی انجام داده است؛ بدون نمایش محتوای خصوصی.":"Who did what and when, without private message content."}</p></div><button className="icon-button" disabled={busy} aria-label={fa?"تازه‌سازی گزارش":"Refresh activity"} onClick={()=>setRefresh(n=>n+1)}>{busy?<LoaderCircle className="spin"/>:<RefreshCw/>}</button></header>
    <div className="activity-filters">{showPeriod&&<SelectMenu label={fa?"بازه گزارش":"Report period"} value={period} options={["7","30","90"].map(d=>[d,`${new Intl.NumberFormat(fa?"fa-IR":"en").format(Number(d))} ${fa?"روز اخیر":"days"}`])} onChange={v=>{setPeriod(v);setPage(1);setData(undefined);}}/>}<SelectMenu label={fa?"نوع فعالیت":"Activity type"} value={category} options={[["all",fa?"همه فعالیت‌ها":"All activity"],["login",fa?"ورودها":"Sign-ins"],["orders",fa?"سفارش‌ها":"Orders"],["messages",fa?"پیام‌ها":"Messages"],["notes",fa?"یادداشت و پیگیری":"Notes & follow-ups"],["team",fa?"محصولات و مدیریت":"Products & management"]]} onChange={v=>{setCategory(v);setPage(1);setData(undefined);}}/></div>
    {error?<p role="alert">{fa?"گزارش دریافت نشد؛ دوباره تلاش کن.":"Could not load activity. Please retry."}</p>:!data?<p role="status">{fa?"در حال دریافت گزارش…":"Loading activity…"}</p>:<><ol className="activity-list">{data.items.map(row=><li key={`${row.source}-${row.id}`}><i aria-hidden="true">{row.source==="message"?<MessageCircle/>:<Activity/>}</i><div><strong>{activityName(row.action,fa)}</strong><span>{row.actor_name||(fa?"سیستم / نام ثبت نشده":"System / name not recorded")} · {role(row.actor_role)}</span><small>{target(row)}</small></div><time dateTime={row.created_at}>{new Intl.DateTimeFormat(fa?"fa-IR":"en-GB",{timeZone:"Asia/Tehran",dateStyle:"medium",timeStyle:"short"}).format(new Date(row.created_at))}</time></li>)}</ol>{!data.items.length&&<p className="activity-empty">{fa?"در این بازه و فیلتر، فعالیتی ثبت نشده است.":"No activity in this period with this filter."}</p>}</>}
    <footer><button className="button secondary" disabled={busy||page<=1} onClick={()=>{setPage(p=>p-1);setData(undefined);}}>{fa?<ArrowRight/>:<ArrowLeft/>}{fa?"قبلی":"Previous"}</button><span>{fa?"صفحه":"Page"} {new Intl.NumberFormat(fa?"fa-IR":"en").format(page)}</span><button className="button secondary" disabled={busy||error||!data?.has_more||page>=200} onClick={()=>{setPage(p=>p+1);setData(undefined);}}>{fa?"بعدی":"Next"}{fa?<ArrowLeft/>:<ArrowRight/>}</button></footer>
  </section>;
}
