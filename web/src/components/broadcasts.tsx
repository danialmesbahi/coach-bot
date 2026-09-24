"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { BellRing, Check, LoaderCircle, RotateCcw, Send, UsersRound, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Lang, Session } from "@/lib/types";
import { SelectMenu } from "@/components/select-menu";

type Product = { id:number; title:string; archived?:boolean };
type Campaign = { id:number; message:string; status:string; created_at:string; total:number; sent:number; failed:number; paused:number };
type Data = { products:Product[]; campaigns:Campaign[] };
type Recipient = {id:number;name:string|null;first_name:string|null;last_name:string|null;username:string|null};
type Preview = {count:number;recipients:Recipient[];next_cursor:number|null};
type PurchaseState = "all"|"never"|"purchased"|"active"|"expired";
type Audience = {
  purchase_state:PurchaseState; product_ids:number[]; age_min:number|null; age_max:number|null;
  gender:string|null; joined_within_days:number|null; last_purchase_within_days:number|null;
  orders_min:number|null; orders_max:number|null; spent_min:number|null; spent_max:number|null; search:string;
  height_min:number|null; height_max:number|null; weight_min:number|null; weight_max:number|null;
  profile_keyword:string; has_phone:boolean|null; has_photo:boolean|null; profile_updated_within_days:number|null;
  payment_method:string|null; order_status:string|null; message_state:"all"|"chatted"|"never"; last_message_within_days:number|null;
};
const initial:Audience = {
  purchase_state:"all",product_ids:[],age_min:null,age_max:null,gender:null,joined_within_days:null,
  last_purchase_within_days:null,orders_min:null,orders_max:null,spent_min:null,spent_max:null,search:"",
  height_min:null,height_max:null,weight_min:null,weight_max:null,profile_keyword:"",has_phone:null,has_photo:null,
  profile_updated_within_days:null,payment_method:null,order_status:null,message_state:"all",last_message_within_days:null,
};
const numberValue = (value:string) => value === "" ? null : Number(value);

export default function Broadcasts({session,lang}:{session:Session;lang:Lang}) {
  const fa=lang==="fa", dialog=useRef<HTMLDialogElement>(null);
  const [data,setData]=useState<Data>(), [loadingData,setLoadingData]=useState(true);
  const [message,setMessage]=useState(""), [audience,setAudience]=useState<Audience>(initial);
  const [productSearch,setProductSearch]=useState(""), [count,setCount]=useState<number|null>(null);
  const [recipients,setRecipients]=useState<Recipient[]>([]),[previewing,setPreviewing]=useState(true),[retry,setRetry]=useState(0);
  const [nextCursor,setNextCursor]=useState<number|null>(null),[loadingMore,setLoadingMore]=useState(false);
  const moreRequest=useRef<AbortController|null>(null);
  const [busy,setBusy]=useState(false), [error,setError]=useState(""), [previewError,setPreviewError]=useState(""), [notice,setNotice]=useState("");
  const ready=Boolean(data);
  const load=useCallback(()=>{
    void api<Data>("/api/broadcasts",session.csrf).then(result=>{setData(result);})
      .catch(()=>setError(fa?"دریافت اطلاعات ممکن نشد. دوباره تلاش کن.":"Could not load broadcasts. Please retry."))
      .finally(()=>setLoadingData(false));
  },[session.csrf,fa]);
  useEffect(()=>{load();},[load]);
  useEffect(()=>{
    if(!data?.campaigns.some(item=>item.status==="queued"))return;
    const timer=setInterval(load,10000);
    return()=>clearInterval(timer);
  },[data,load]);
  useEffect(()=>{
    if(!ready)return;
    const controller=new AbortController();
    const timer=window.setTimeout(()=>{
      setPreviewing(true);setPreviewError("");
      void api<Preview>("/api/broadcasts/preview",session.csrf,{method:"POST",body:JSON.stringify({audience}),signal:controller.signal})
        .then(result=>{setCount(result.count);setRecipients(result.recipients);setNextCursor(result.next_cursor);setPreviewError("");})
        .catch(err=>{if(!controller.signal.aborted){setCount(null);setRecipients([]);setPreviewError(err instanceof ApiError&&err.code==="rate_limited"?(fa?"درخواست‌های پیش‌نمایش زیاد شد؛ یک دقیقه بعد دوباره امتحان کن.":"Too many previews. Try again in a minute."):(fa?"نمایش مخاطبان ممکن نشد؛ فیلترها یا اتصال را بررسی کن.":"Could not preview recipients. Check filters or connection."));}})
        .finally(()=>{if(!controller.signal.aborted)setPreviewing(false);});
    },700);
    return()=>{window.clearTimeout(timer);controller.abort();moreRequest.current?.abort();};
  },[audience,ready,fa,retry,session.csrf]);
  const change=(next:Audience)=>{moreRequest.current?.abort();setAudience(next);setCount(null);setRecipients([]);setNextCursor(null);setLoadingMore(false);setPreviewing(true);setPreviewError("");setNotice("");};
  const loadMore=async()=>{
    if(!nextCursor||loadingMore||previewing)return;
    const controller=new AbortController();moreRequest.current=controller;setLoadingMore(true);
    try {
      const result=await api<Preview>("/api/broadcasts/preview",session.csrf,{method:"POST",body:JSON.stringify({audience,after_id:nextCursor}),signal:controller.signal});
      if(!controller.signal.aborted){setCount(result.count);setRecipients(current=>[...current,...result.recipients]);setNextCursor(result.next_cursor);setPreviewError("");}
    } catch(err) {
      if(!controller.signal.aborted)setPreviewError(err instanceof ApiError&&err.code==="rate_limited"?(fa?"درخواست‌های پیش‌نمایش زیاد شد؛ یک دقیقه بعد دوباره امتحان کن.":"Too many previews. Try again in a minute."):(fa?"دریافت مخاطبان بیشتر ممکن نشد.":"Could not load more recipients."));
    } finally {if(!controller.signal.aborted)setLoadingMore(false);}
  };
  const setNumber=(key:keyof Audience,value:string)=>change({...audience,[key]:numberValue(value)});
  const send=async()=>{
    if(count===null||count<1||busy)return;
    setBusy(true);setError("");
    try {
      const result=await api<{id:number;count:number}>("/api/broadcasts",session.csrf,{method:"POST",body:JSON.stringify({message,audience,expected_count:count})});
      setData(current=>current?{...current,campaigns:[{id:result.id,message,status:"queued",created_at:new Date().toISOString(),total:result.count,sent:0,failed:0,paused:0},...current.campaigns].slice(0,20)}:current);
      dialog.current?.close();setMessage("");
      setNotice(fa?"پیام به فهرست ارسال‌های اخیر اضافه شد.":"Added to recent broadcasts.");
      load();
    } catch(err) {
      dialog.current?.close();setCount(null);setRetry(value=>value+1);
      const code=err instanceof ApiError?err.code:"";
      setError(code==="broadcast_in_progress"?(fa?"ارسال دیگری در جریان است. پس از پایان آن دوباره تلاش کن.":"Another broadcast is in progress. Try again when it finishes."):code==="audience_changed"?(fa?"مخاطبان تغییر کرده‌اند. فهرست را تازه کن و دوباره تأیید کن.":"Recipients changed. Refresh the list and confirm again."):(fa?"ارسال آغاز نشد. دوباره تلاش کن؛ اگر ادامه داشت، گزارش خطا را بررسی می‌کنیم.":"Broadcast was not queued. Try again; check diagnostics if it persists."));
    } finally {setBusy(false);}
  };
  const selected=Object.entries(audience).filter(([key,value])=>key==="product_ids"?(value as number[]).length>0:key==="purchase_state"||key==="message_state"?value!=="all":key==="search"||key==="profile_keyword"?Boolean(value):value!==null).length;
  const products=data?.products.filter(product=>product.title.toLocaleLowerCase().includes(productSearch.toLocaleLowerCase()))??[];
  const amount=(value:number|null)=>value??"";
  const triState=(value:boolean|null)=>value===null?"":String(value);
  const queued=data?.campaigns.some(item=>item.status==="queued")??false;
  const range=(keyMin:keyof Audience,keyMax:keyof Audience,label:string,min:number,max:number,step=1)=>(
    <div className="broadcast-range"><span>{label}</span><div>
      <label>{fa?"از":"From"}<input aria-label={`${label} ${fa?"از":"From"}`} type="number" min={min} max={max} step={step} inputMode="numeric" value={amount(audience[keyMin] as number|null)} onChange={e=>setNumber(keyMin,e.target.value)} placeholder={fa?"بدون حد":"Any"}/></label>
      <label>{fa?"تا":"To"}<input aria-label={`${label} ${fa?"تا":"To"}`} type="number" min={min} max={max} step={step} inputMode="numeric" value={amount(audience[keyMax] as number|null)} onChange={e=>setNumber(keyMax,e.target.value)} placeholder={fa?"بدون حد":"Any"}/></label>
    </div></div>
  );
  const reviewButton=<button className="button primary" type="button" disabled={busy||queued||previewing||!message.trim()||count===null||count<1} onClick={()=>dialog.current?.showModal()}><Send/>{fa?"بررسی و ارسال":"Review & send"}</button>;
  return <div className="broadcast-page" dir={fa?"rtl":"ltr"}>
    <header className="section-heading"><div><p className="eyebrow">{fa?"ارتباط با کاربران":"USER COMMUNICATION"}</p><h1>{fa?"پیام همگانی":"Broadcasts"}</h1><p>{fa?"پیام را بنویس، مخاطبان را انتخاب کن و پیش از ارسال فهرست را بررسی کن.":"Write your message, choose recipients, then review the list before sending."}</p></div><BellRing aria-hidden="true"/></header>
    <div className="broadcast-layout"><div className="broadcast-primary"><section className="glass broadcast-panel broadcast-compose">
      <div className="broadcast-step"><span>01</span><div><h2>{fa?"پیام":"Message"}</h2><p>{fa?"همین متن برای تمام مخاطبان انتخاب‌شده ارسال می‌شود.":"The same text will be sent to every matched client."}</p></div></div>
      <label htmlFor="broadcast-message">{fa?"متن ارسالی به تلگرام":"Telegram message"}</label>
      <textarea id="broadcast-message" rows={8} maxLength={4000} required disabled={busy} value={message} onChange={e=>setMessage(e.target.value)} placeholder={fa?"پیامت را اینجا بنویس…":"Write your message…"}/>
      <small>{message.length.toLocaleString(fa?"fa-IR":"en")} / 4000</small>
      <div className="broadcast-summary"><UsersRound/><span>{previewing?(fa?"در حال بررسی مخاطبان…":"Checking audience…"):count===null?(fa?"مخاطبان هنوز تأیید نشده‌اند":"Audience not verified yet"):`${count.toLocaleString(fa?"fa-IR":"en")} ${fa?"مخاطب آمادهٔ ارسال":"recipients ready"}`}</span></div>
      <div className="broadcast-actions">{error&&<p className="staff-feedback error" role="alert">{error}</p>}{notice&&<p className="staff-feedback success" role="status">{notice}</p>}
        {reviewButton}
        {queued&&<p className="broadcast-note">{fa?"یک پیام همگانی در حال ارسال است. پس از پایان آن می‌توانی پیام بعدی را بفرستی.":"Another broadcast is sending. Wait until it finishes before starting the next one."}</p>}
      </div>
    </section>
    <section className="broadcast-history"><h2>{fa?"ارسال‌های اخیر":"Recent broadcasts"}</h2>{data?.campaigns.length?data.campaigns.map(item=>{
      const processed=Math.min(item.total,item.sent+item.failed);
      const status=item.status==="queued"?(fa?"در حال ارسال":"Sending"):item.status==="paused"?(fa?"نیازمند بررسی":"Needs review"):(fa?"پایان‌یافته":"Completed");
      return <article className="glass" key={item.id}>
        <div className="broadcast-history-head"><strong title={item.message}>{item.message}</strong><span className={`broadcast-status is-${item.status}`}>{status}</span></div>
        <time>{new Date(item.created_at).toLocaleString(fa?"fa-IR":"en")}</time>
        <div className="broadcast-progress-copy"><span>{item.sent.toLocaleString(fa?"fa-IR":"en")} {fa?"ارسال‌شده از":"sent of"} {item.total.toLocaleString(fa?"fa-IR":"en")} {fa?"مخاطب":"recipients"}</span>{item.total>0&&<span>{Math.round(processed/item.total*100).toLocaleString(fa?"fa-IR":"en")}%</span>}</div>
        <progress className="broadcast-progress" max={Math.max(item.total,1)} value={processed} aria-label={`${status}: ${item.sent} ${fa?"ارسال‌شده از":"sent of"} ${item.total}`}/>
        {(item.failed>0||item.paused>0)&&<p>{item.failed>0?`${item.failed.toLocaleString(fa?"fa-IR":"en")} ${fa?"ناموفق":"failed"}`:""}{item.failed>0&&item.paused>0?" · ":""}{item.paused>0?`${item.paused.toLocaleString(fa?"fa-IR":"en")} ${fa?"نیازمند بررسی":"paused"}`:""}</p>}
      </article>;
    }):<p>{fa?"هنوز پیامی ارسال نشده است.":"No broadcasts yet."}</p>}</section>
    </div><section className="glass broadcast-panel broadcast-audience">
      <div className="broadcast-panel-heading"><div className="broadcast-step"><span>02</span><div><h2>{fa?"مخاطبان":"Audience"}</h2><p>{fa?"فیلترها با هم ترکیب می‌شوند؛ نتیجه را پیش از ارسال بررسی کن.":"Filters combine; review the result before sending."}</p></div></div><button type="button" className="button secondary" disabled={busy||selected===0} onClick={()=>change(initial)}><RotateCcw/>{fa?"پاک‌کردن":"Clear"}{selected>0&&<b>{selected}</b>}</button></div>
      {loadingData ? <p role="status">{fa?"در حال دریافت دوره‌ها…":"Loading products…"}</p> : !data ? <button type="button" className="button secondary" onClick={load}>{fa?"تلاش دوباره":"Retry"}</button> : <fieldset className="broadcast-filter-fields" disabled={busy}>
        <label className="broadcast-search">{fa?"جست‌وجوی کاربر":"Find a user"}<input type="search" value={audience.search} maxLength={80} onChange={e=>change({...audience,search:e.target.value})} placeholder={fa?"نام، @شناسه، کد، تلفن یا آیدی تلگرام":"Name, @handle, code, phone or Telegram ID"}/></label>
        <div className="broadcast-filter-group"><h3>{fa?"وضعیت خرید":"Purchase status"}</h3><SelectMenu label={fa?"ارتباط کاربر با دوره‌ها":"Course relationship"} value={audience.purchase_state} options={[
          ["all",fa?"همهٔ کاربران":"All users"],["never",fa?"بدون خرید":"Never purchased"],
          ["purchased",fa?"دارای خرید":"Purchased"],["active",fa?"دورهٔ فعال":"Active course"],
          ["expired",fa?"دورهٔ پایان‌یافته، بدون تمدید":"Expired, not renewed"],
        ]} onChange={value=>{
          const state=value as PurchaseState;
          change(state==="never"?{...audience,purchase_state:state,product_ids:[],last_purchase_within_days:null,orders_min:null,orders_max:null,spent_min:null,spent_max:null,payment_method:null}:{...audience,purchase_state:state});
        }}/>
        {audience.purchase_state==="expired"&&<p className="broadcast-note">{fa?"فقط دوره‌های زمان‌دار که تمام شده‌اند؛ شاگردی که همان دوره را تمدید کرده شامل نمی‌شود.":"Only ended, time-limited courses; renewed clients are excluded."}</p>}
        </div>
        {audience.purchase_state!=="never"&&<div className="broadcast-filter-group"><h3>{fa?"دوره‌ها":"Products"}</h3><p>{fa?"اختیاری؛ با انتخاب چند دوره، داشتن حداقل یکی کافی است.":"Optional. Selecting several products matches any one of them."}</p>
          {data.products.length>8&&<input type="search" value={productSearch} onChange={e=>setProductSearch(e.target.value)} placeholder={fa?"پیدا کردن دوره…":"Find a product…"} aria-label={fa?"جست‌وجوی دوره":"Search products"}/>}
          <div className={`broadcast-products${products.length>8?" is-scrollable":""}`}>{products.map(product=>{const checked=audience.product_ids.includes(product.id);return <button type="button" role="checkbox" aria-checked={checked} className={`broadcast-check${checked?" selected":""}`} key={product.id} onClick={()=>change({...audience,product_ids:checked?audience.product_ids.filter(id=>id!==product.id):[...audience.product_ids,product.id]})}><i aria-hidden="true">{checked&&<Check/>}</i><span>{product.title}{product.archived&&<small> · {fa?"بایگانی‌شده":"Archived"}</small>}</span></button>;})}{!products.length&&<small>{fa?"دوره‌ای پیدا نشد.":"No matching products."}</small>}</div>
        </div>}
        <details className="broadcast-filter-group broadcast-advanced"><summary>{fa?"مشخصات و پروفایل":"Profile & demographics"}</summary>
          {range("age_min","age_max",fa?"سن (سال)":"Age (years)",10,100)}
          {range("height_min","height_max",fa?"قد (سانتی‌متر)":"Height (cm)",100,230)}
          {range("weight_min","weight_max",fa?"وزن (کیلوگرم)":"Weight (kg)",25,300)}
          <div className="broadcast-filter-grid"><SelectMenu label={fa?"جنسیت":"Gender"} value={audience.gender??""} options={[["",fa?"همه":"Any"],["مرد",fa?"مرد":"Male"],["زن",fa?"زن":"Female"]]} onChange={value=>change({...audience,gender:value||null})}/>
            <label>{fa?"عضویت در روزهای اخیر":"Joined within days"}<input type="number" min={1} max={3650} inputMode="numeric" value={amount(audience.joined_within_days)} onChange={e=>setNumber("joined_within_days",e.target.value)} placeholder={fa?"هر زمان":"Any time"}/></label></div>
          <label>{fa?"هدف یا متن پروفایل":"Goal or profile text"}<input type="search" maxLength={80} value={audience.profile_keyword} onChange={e=>change({...audience,profile_keyword:e.target.value})} placeholder={fa?"هدف، سابقه، آلرژی، محدودیت غذایی، مکمل…":"Goal, training, allergy, diet, supplements…"}/></label>
          <div className="broadcast-filter-grid"><SelectMenu label={fa?"شماره تماس":"Phone number"} value={triState(audience.has_phone)} options={[["",fa?"همه":"Any"],["true",fa?"ثبت‌شده":"Available"],["false",fa?"ثبت‌نشده":"Missing"]]} onChange={value=>change({...audience,has_phone:value===""?null:value==="true"})}/><SelectMenu label={fa?"عکس بدن":"Body photo"} value={triState(audience.has_photo)} options={[["",fa?"همه":"Any"],["true",fa?"دارد":"Available"],["false",fa?"ندارد":"Missing"]]} onChange={value=>change({...audience,has_photo:value===""?null:value==="true"})}/></div>
          <label>{fa?"آخرین به‌روزرسانی پروفایل در چند روز اخیر":"Profile updated within days"}<input type="number" min={1} max={3650} inputMode="numeric" value={amount(audience.profile_updated_within_days)} onChange={e=>setNumber("profile_updated_within_days",e.target.value)} placeholder={fa?"هر زمان":"Any time"}/></label>
          <p className="broadcast-note">{fa?"شاگردی که سن یا جنسیتش ثبت نشده، هنگام اعمال همان فیلتر در نتیجه نمی‌آید.":"Clients missing age or gender are excluded when that filter is applied."}</p>
        </details>
        {audience.purchase_state!=="never"&&<details className="broadcast-filter-group broadcast-advanced"><summary>{fa?"سابقهٔ خرید":"Purchase history"}</summary>
          {range("orders_min","orders_max",fa?"تعداد سفارش پرداخت‌شده":"Paid orders",0,100000)}
          {range("spent_min","spent_max",fa?"جمع پرداخت‌ها (تومان)":"Total paid (Toman)",0,1_000_000_000_000)}
          <label>{fa?"آخرین خرید در روزهای اخیر":"Last purchase within days"}<input type="number" min={1} max={3650} inputMode="numeric" value={amount(audience.last_purchase_within_days)} onChange={e=>setNumber("last_purchase_within_days",e.target.value)} placeholder={fa?"هر زمان":"Any time"}/></label>
        </details>}
        <details className="broadcast-filter-group broadcast-advanced"><summary>{fa?"سفارش و پرداخت":"Orders & payments"}</summary><div className="broadcast-filter-grid"><SelectMenu label={fa?"روش پرداخت موفق":"Successful payment method"} value={audience.payment_method??""} options={[["",fa?"همه":"Any"],["zarinpal",fa?"زرین‌پال":"Zarinpal"],["card_to_card",fa?"کارت‌به‌کارت":"Bank transfer"]]} onChange={value=>change({...audience,payment_method:value||null,purchase_state:value&&audience.purchase_state==="never"?"all":audience.purchase_state})}/><SelectMenu label={fa?"وضعیت سفارش":"Order status"} value={audience.order_status??""} options={[["",fa?"همه":"Any"],["awaiting_payment",fa?"در انتظار پرداخت":"Awaiting payment"],["awaiting_receipt",fa?"در انتظار رسید":"Awaiting receipt"],["payment_rejected",fa?"پرداخت ردشده":"Payment rejected"],["paid",fa?"پرداخت‌شده":"Paid"],["needs_info",fa?"نیازمند اطلاعات":"Needs information"],["in_progress",fa?"در طراحی":"In progress"],["ready",fa?"آماده":"Ready"],["delivered",fa?"تحویل‌شده":"Delivered"],["cancelled",fa?"لغوشده":"Cancelled"]]} onChange={value=>change({...audience,order_status:value||null})}/></div></details>
        <details className="broadcast-filter-group broadcast-advanced"><summary>{fa?"تعامل و گفت‌وگو":"Engagement & chat"}</summary><div className="broadcast-filter-grid"><SelectMenu label={fa?"سابقهٔ گفت‌وگو":"Chat history"} value={audience.message_state} options={[["all",fa?"همه":"Any"],["chatted",fa?"گفت‌وگو داشته":"Has chatted"],["never",fa?"بدون گفت‌وگو":"No chat yet"]]} onChange={value=>change({...audience,message_state:value as Audience["message_state"],last_message_within_days:value==="never"?null:audience.last_message_within_days})}/><label>{fa?"گفت‌وگو در روزهای اخیر":"Chatted within days"}<input type="number" min={1} max={3650} disabled={audience.message_state==="never"} inputMode="numeric" value={amount(audience.last_message_within_days)} onChange={e=>setNumber("last_message_within_days",e.target.value)} placeholder={fa?"هر زمان":"Any time"}/></label></div></details>
        <p className="broadcast-note">{fa?"پیام به حساب‌های ثبت‌شدهٔ بات می‌رسد؛ حتی اگر صاحب آن حساب عضو تیم هم باشد.":"Messages go to registered bot users, including users who also belong to the team."}</p>
      </fieldset>}
      <section className="broadcast-recipients" aria-live="polite"><div className="broadcast-recipients-heading"><div><strong>{fa?"پیش‌نمایش مخاطبان":"Recipient preview"}</strong><small>{previewing?(fa?"در حال بررسی فیلترها…":"Checking filters…"):count===null?(fa?"فهرست در دسترس نیست":"List unavailable"):`${count.toLocaleString(fa?"fa-IR":"en")} ${fa?"نفر مطابق فیلترها":"matching clients"}`}</small></div><button className="icon-button" type="button" disabled={previewing||busy} aria-label={fa?"تازه‌کردن فهرست مخاطبان":"Refresh recipients"} onClick={()=>{setCount(null);setPreviewing(true);setRetry(value=>value+1);}}><RotateCcw/></button></div>
        {count===0&&<p className="broadcast-empty">{fa?"کسی با این فیلترها پیدا نشد. فیلترها را کمتر کن.":"No clients match. Try broader filters."}</p>}
        {previewError&&<p className="staff-feedback error" role="alert">{previewError}</p>}
        {recipients.length>0&&<div className="broadcast-recipient-list">{recipients.map(person=>{const name=person.name||[person.first_name,person.last_name].filter(Boolean).join(" ")||person.username||`U${String(person.id).padStart(7,"0")}`;return <div className="broadcast-recipient" key={person.id}><span className="broadcast-avatar">{name.trim().slice(0,1).toUpperCase()}</span><span><strong dir="auto">{name}</strong><small dir="ltr">{person.username?`@${person.username.replace(/^@/,"")}`:`U${String(person.id).padStart(7,"0")}`}</small></span></div>;})}</div>}
        {count!==null&&count>recipients.length&&<div className="broadcast-more"><small>{fa?`نمایش ${recipients.length.toLocaleString("fa-IR")} نفر از ${count.toLocaleString("fa-IR")}`:`Showing ${recipients.length} of ${count}`}</small>{nextCursor&&<button className="button secondary" type="button" disabled={loadingMore||previewing} onClick={()=>void loadMore()}>{loadingMore?<LoaderCircle className="spin"/>:null}{fa?"نمایش بیشتر":"Show more"}</button>}</div>}
      </section>
      <div className="broadcast-mobile-actions">{error&&<p className="staff-feedback error" role="alert">{error}</p>}{notice&&<p className="staff-feedback success" role="status">{notice}</p>}{reviewButton}{queued&&<p className="broadcast-note">{fa?"ارسال فعلی را در بخش بعدی دنبال کن؛ پس از پایان می‌توانی پیام بعدی را بفرستی.":"Track this broadcast below. You can start another when it finishes."}</p>}</div>
    </section>
    </div>
    <dialog ref={dialog} className="staff-confirm" role="alertdialog" aria-labelledby="broadcast-confirm-title"><i><BellRing/></i><h3 id="broadcast-confirm-title">{fa?"ارسال همگانی آغاز شود؟":"Start this broadcast?"}</h3><p>{fa?`این پیام برای ${count?.toLocaleString("fa-IR")} نفر در صف قرار می‌گیرد. این کار پس از شروع قابل بازگشت نیست.`:`This message will be queued for ${count?.toLocaleString("en")} people and cannot be undone.`}</p><blockquote className="broadcast-confirm-message" dir="auto">{message}</blockquote><div><button className="button secondary" type="button" onClick={()=>dialog.current?.close()}><X/>{fa?"انصراف":"Cancel"}</button><button className="button primary" type="button" disabled={busy} onClick={()=>void send()}>{busy?<LoaderCircle className="spin"/>:<Check/>}{fa?"تأیید ارسال":"Confirm send"}</button></div></dialog>
  </div>;
}
