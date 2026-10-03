"use client";
/* eslint-disable @next/next/no-img-element -- Private catalog media and local upload previews. */

import { FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Archive, Eye, EyeOff, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, GripVertical, Check, FileText, Play, Layers, LoaderCircle, Plus, Radio, Save, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { SelectMenu } from "./select-menu";
import { MediaViewer, type PreviewMedia } from "./media-viewer";
import { DeliveryBundleFields, DeliveryFilePicker } from "./delivery-bundle-fields";
import type { Lang, Session } from "@/lib/types";

type Asset = {id:number;filename:string;byte_size?:number};
type Product = { duration_unit?:string; asset_ids?:number[]; assets?:Asset[]; before_id?:number|null; id?:number; version?:number; title:string; description:string; price_irr:number; duration_days:number; delivery_mode:"manual"|"content"|"channel"; form_fields:string[]; questions:string[]; response_text:string; content_url:string; content_urls?:string[]; channel_id:number|null; asset_id:number|null; filename?:string; active:boolean; sort_order:number };
type Channel = {chat_id:number;title:string;last_error?:string|null};
export type CatalogData = {items:Product[];total:number;page:number;pageSize:number;download_base_configured?:boolean;next_id?:number|null;channels:Channel[]};
const fields:[string,string,string][]=[["name","نام","Name"],["phone","تلفن","Phone"],["age","سن","Age"],["gender","جنسیت","Gender"],["height","قد","Height"],["weight","وزن","Weight"],["goal","هدف","Goal"],["training_history","سابقه تمرین","Training history"],["allergy","حساسیت غذایی","Food allergies"],["restriction","محدودیت غذایی","Diet restrictions"],["supplements","مکمل‌ها","Supplements"],["notes","توضیحات","Notes"],["measurements","اندازه‌های بدن","Body measurements"],["body_photo","عکس‌های بدن","Body photos"]];
const blank:Product={title:"",description:"",price_irr:100000,duration_days:30,duration_unit:"months",asset_ids:[],assets:[],before_id:null,delivery_mode:"manual",form_fields:["name","phone","notes"],questions:[],response_text:"",content_url:"",content_urls:[],channel_id:null,asset_id:null,active:false,sort_order:0};

export function Catalog({data,lang,session,setPage,refresh}:{data:CatalogData;lang:Lang;session:Session;setPage:(p:number)=>void;refresh:()=>void}) {
  const fa=lang==="fa",[editing,setEditing]=useState<Product|null>(null),[notice,setNotice]=useState("");
  const [ordering,setOrdering]=useState(false),[moving,setMoving]=useState(false);
  const move=async(id:number,before_id:number|null)=>{const product=data.items.find(p=>p.id===id);if(!product||moving)return;setMoving(true);setNotice("");try{await api("/api/catalog-order",session.csrf,{method:"POST",body:JSON.stringify({id,before_id,version:product.version})});refresh();setNotice(fa?"ترتیب ذخیره شد.":"Order saved.");}catch{setNotice(fa?"ترتیب تغییر کرده یا اتصال قطع است؛ دوباره تلاش کن.":"Could not reorder. Refresh and retry.");refresh();}finally{setMoving(false);}};
  const mode=(value:Product["delivery_mode"])=>({manual:fa?"برنامه اختصاصی":"Custom program",content:fa?"تحویل فوری":"Instant content",channel:fa?"اشتراک کانال":"Channel membership"}[value]);
  return <div className="catalog-page"><header className="catalog-heading"><div><span className="catalog-eyebrow">{fa?"ویترین تلگرام":"TELEGRAM STOREFRONT"}</span><h1>{fa?"دوره‌ها و محصولات":"Courses & products"}</h1><p>{fa?"از اولین سؤال تا تحویل؛ مسیر هر خرید را اینجا تنظیم کن.":"Shape every purchase, from the first question to delivery."}</p></div><div className="catalog-heading-actions"><button className="button secondary catalog-arrange-toggle" aria-pressed={ordering} aria-controls="catalog-order" disabled={moving} onClick={()=>setOrdering(v=>!v)}>{ordering?<Check/>:<GripVertical/>}{ordering?(fa?"پایان چیدمان":"Done arranging"):(fa?"چیدمان دوره‌ها":"Arrange products")}</button><button className="button" onClick={()=>setEditing({...blank})}><Plus/>{fa?"دوره جدید":"New product"}</button></div></header>{notice&&<p role="status" className="staff-feedback success">{notice}</p>}{ordering&&<ProductOrder start={(data.page-1)*data.pageSize} items={data.items} nextId={data.next_id??null} fa={fa} disabled={moving} onMove={(id,before)=>void move(id,before)}/> }<div className="catalog-grid" hidden={ordering}>{data.items.map(product=><button key={product.id} className="catalog-card glass" onClick={()=>setEditing(product)}><span className="catalog-card-top"><span><Layers/>{mode(product.delivery_mode)}</span><b className={product.active?"published":""}>{product.active?(fa?"در حال فروش":"On sale"):(fa?"پیش‌نویس / متوقف":"Draft / paused")}</b></span><h2>{product.title}</h2><p>{product.description|| (fa?"توضیح دوره را اضافه کن":"Add a product description")}</p><div className="catalog-card-bottom"><strong>{new Intl.NumberFormat(fa?"fa-IR":"en").format(product.price_irr)} <small>{fa?"تومان":"Toman"}</small></strong><span>{durationText(product,fa)}</span></div></button>)}</div>{!data.items.length&&<div className="glass catalog-empty"><Layers/><p>{fa?"اولین دوره‌ات را بساز؛ تا فعالش نکنی در بات نمایش داده نمی‌شود.":"Create your first product. It appears in the bot when you publish it."}</p></div>}<div className="pager"><button className="button secondary" disabled={data.page<=1} onClick={()=>setPage(data.page-1)}><ArrowRight aria-hidden="true"/>{fa?"قبلی":"Previous"}</button><span>{data.page} / {Math.max(1,Math.ceil(data.total/data.pageSize))}</span><button className="button secondary" disabled={data.page*data.pageSize>=data.total} onClick={()=>setPage(data.page+1)}>{fa?"بعدی":"Next"}<ArrowLeft aria-hidden="true"/></button></div>{editing&&<ProductEditor downloadReady={data.download_base_configured!==false} product={editing} products={data.items} channels={data.channels} session={session} lang={lang} onClose={()=>setEditing(null)} onSaved={()=>{setEditing(null);setNotice(fa?"تغییرات ذخیره شد و در فروشگاه ربات اعمال شد.":"Saved. The bot storefront is up to date.");refresh();}}/>}</div>;
}

function ProductEditor({downloadReady,product,products,channels,session,lang,onClose,onSaved}:{downloadReady:boolean;product:Product;products:Product[];channels:Channel[];session:Session;lang:Lang;onClose:()=>void;onSaved:()=>void}) {
  const fa=lang==="fa",dialog=useRef<HTMLDialogElement>(null),backdrop=useRef(false);
  const [draft,setDraft]=useState({...product}),[busy,setBusy]=useState(false),[error,setError]=useState(""),[confirmArchive,setConfirmArchive]=useState(false),[archiveError,setArchiveError]=useState(false);
  const [channelList,setChannelList]=useState(channels),[channelInput,setChannelInput]=useState("");
  const unit=draft.duration_unit??"days";
  const factor=durationFactors[unit]??1;
  const [uploading,setUploading]=useState<{name:string;percent:number}|null>(null);
  const uploadRequest=useRef<XMLHttpRequest|null>(null);
  const localPreviews=useRef(new Map<number,string>());
  const [previewUrls,setPreviewUrls]=useState<Record<number,string>>({});
  const [preview,setPreview]=useState<PreviewMedia|null>(null);
  useEffect(()=>{const urls=localPreviews.current;return()=>{uploadRequest.current?.abort();urls.forEach(url=>URL.revokeObjectURL(url));};},[]);
  const set=<K extends keyof Product>(key:K,value:Product[K])=>setDraft(old=>({...old,[key]:value}));
  useEffect(()=>{dialog.current?.showModal();const body=document.body,y=scrollY,old={position:body.style.position,top:body.style.top,width:body.style.width,overflow:body.style.overflow};Object.assign(body.style,{position:"fixed",top:`-${y}px`,width:"100%",overflow:"hidden"});return()=>{Object.assign(body.style,old);scrollTo({top:y,behavior:"instant"});};},[]);
  useEffect(()=>{if(error)dialog.current?.querySelector<HTMLElement>('[role="alert"]')?.scrollIntoView({block:"center",behavior:"auto"});},[error]);
  const failure=(err:unknown)=>{const code=err instanceof ApiError?err.code:"";const field=err instanceof ApiError?err.field:undefined;if(code==="download_base_required"){setError(fa?"یکی از فایل‌ها از سقف ارسال مستقیم تلگرام (۵۰ مگابایت) بزرگ‌تر است. آپلود حفظ شده؛ مدیر فنی باید تحویل فایل بزرگ از همین سرور را فعال کند. فایل‌های کوچک‌تر به دامنه نیاز ندارند.":"A file exceeds Telegram’s 50 MB direct-upload limit. Your uploads are kept. A technical administrator must enable large-file delivery from this server; smaller files need no domain.");return;}const names:Record<string,string>={title:fa?"نام دوره را وارد کن.":"Enter a product name.",price_irr:fa?"قیمت باید بین ۱٬۰۰۰ و ۱٬۰۰۰٬۰۰۰٬۰۰۰ تومان باشد.":"Price must be between 1,000 and 1,000,000,000 Toman.",duration_days:fa?"مدت باید عدد صحیح و متناسب با واحد انتخاب‌شده باشد.":"Use a whole duration matching the selected unit.",questions:fa?"هر سؤال حداکثر ۲۰۰ نویسه و تعداد سؤال‌ها حداکثر ۱۰ باشد.":"Use up to 10 questions, each no longer than 200 characters.",content_required:fa?"برای تحویل فوری، فایل، لینک یا پیام محتوا را اضافه کن.":"Add a file, link or message for instant delivery.",content_url:fa?"لینک محتوا باید HTTPS و بدون نام کاربری یا رمز باشد.":"Use an HTTPS content link without embedded credentials.",channel_id:fa?"یک کانال تأییدشده انتخاب کن.":"Select a verified channel."};if(field&&names[field]){setError(names[field]);return;}if(code==="rate_limited"||code==="channel_busy"){setError(fa?"درخواست‌های اتصال زیاد است؛ کمی صبر کن و دوباره تلاش کن.":"Too many connection checks. Wait a moment and try again.");return;}setError(code==="product_changed"?(fa?"این دوره توسط همکار دیگری تغییر کرده؛ پنجره را ببند و دوباره باز کن.":"A teammate changed this product. Close and reopen it."):code.includes("channel")?(fa?"بات باید ادمین کانال خصوصی با دسترسی دعوت و حذف اعضا باشد. شناسه کانال را بررسی کن.":"Use a private channel ID. The bot needs invite and ban permissions."):(fa?"ذخیره انجام نشد؛ فیلدها، فایل و اتصال را بررسی کن.":"Could not save. Check the fields, file and connection."));};
  const save=async(event:FormEvent)=>{event.preventDefault();if(busy)return;setBusy(true);setError("");try{const urls=(draft.content_urls??(draft.content_url?[draft.content_url]:[])).map(url=>url.trim()).filter(Boolean);await api(`/api/catalog${draft.id?`/${draft.id}`:""}`,session.csrf,{method:"POST",body:JSON.stringify({...draft,content_urls:urls,content_url:urls[0]??"",questions:[]})});onSaved();}catch(err){failure(err);}finally{setBusy(false);}};
  const upload=async(files:File[])=>{
    if(busy)return;setBusy(true);setError("");
    try{
      for(const file of files){
        setUploading({name:file.name,percent:0});
        const asset=await new Promise<Asset>((resolve,reject)=>{
          const request=new XMLHttpRequest();uploadRequest.current=request;
          let idle=window.setTimeout(()=>request.abort(),60_000);
          const reset=()=>{clearTimeout(idle);idle=window.setTimeout(()=>request.abort(),60_000);};
          request.open("POST","/api/catalog-assets");request.setRequestHeader("X-CSRF-Token",session.csrf);
          request.upload.onprogress=e=>{reset();setUploading({name:file.name,percent:e.lengthComputable?Math.round(e.loaded/e.total*100):0});};
          request.upload.onload=reset;
          request.onerror=()=>{clearTimeout(idle);reject(new Error("upload_failed"));};
          request.onabort=()=>{clearTimeout(idle);reject(new Error("upload_cancelled"));};
          request.onload=()=>{clearTimeout(idle);try{const data=JSON.parse(request.responseText);if(request.status>=400)reject(new ApiError(request.status,data.error??"upload_failed"));else resolve(data);}catch{reject(new ApiError(request.status,"invalid_upload"));}};
          const body=new FormData();body.append("file",file);request.send(body);
        });
        if(catalogPreviewKind(file.name)!=="file"){
          const url=URL.createObjectURL(file);localPreviews.current.set(asset.id,url);
          setPreviewUrls(old=>({...old,[asset.id]:url}));
        }
        setDraft(old=>({...old,assets:[...(old.assets??(old.asset_id?[{id:old.asset_id,filename:old.filename??"File"}]:[])),asset],asset_ids:[...(old.asset_ids??(old.asset_id?[old.asset_id]:[])),asset.id],asset_id:old.asset_id??asset.id}));
      }
    }catch(err){setError(err instanceof ApiError&&err.code==="invalid_file_type"?(fa?"فایل خالی است یا ساختار آن با پسوندش مطابقت ندارد. نسخهٔ اصلی فایل را دوباره انتخاب کن.":"The file is empty or its contents do not match its extension. Select the original file again."):err instanceof ApiError&&err.status===507?(fa?"فضای امن ذخیره‌سازی سرور کافی نیست؛ فایل‌های قبلی حفظ شده‌اند.":"Server storage reserve reached. Previously uploaded files are kept."):fa?"آپلود کامل نشد یا لغو شد. فایل‌های موفق در فهرست باقی مانده‌اند؛ نوع فایل و اتصال را بررسی کن.":"Upload failed or was cancelled. Completed files are kept; check file type and connection.");}
    finally{uploadRequest.current=null;setUploading(null);setBusy(false);}
  };
  const connect=async()=>{setBusy(true);setError("");try{const chat_id=Number(channelInput);const result=await api<{title:string}>("/api/catalog-channels",session.csrf,{method:"POST",body:JSON.stringify({chat_id})});setChannelList(old=>[...old.filter(c=>c.chat_id!==chat_id),{chat_id,title:result.title}]);set("channel_id",chat_id);setChannelInput("");}catch(err){failure(err);}finally{setBusy(false);}};
  const archive=async()=>{setBusy(true);setError("");try{await api(`/api/catalog/${draft.id}/archive`,session.csrf,{method:"POST"});onSaved();}catch{setArchiveError(true);}finally{setBusy(false);}};
  const modes:[Product["delivery_mode"],ReactNode,string][]=[["manual",fa?"اختصاصی":"Custom",fa?"بررسی اطلاعات ← طراحی ← تحویل مربی":"Review → design → coach delivery"],["content",fa?"آماده":"Ready-made",fa?"پرداخت ← ارسال خودکار محتوا":"Payment → automatic delivery"],["channel",<span className="catalog-mode-title" key="channel">{fa?"کانال خصوصی":"Private channel"}<span className="catalog-beta">{fa?"بتا":"Beta"}</span></span>,fa?"پرداخت ← دعوت اختصاصی ← پایان اشتراک":"Payment → private invite → expiry"]];
  return <dialog ref={dialog} className="catalog-dialog" onPointerDown={event=>{const rect=event.currentTarget.getBoundingClientRect();backdrop.current=event.pointerType==="mouse"&&window.matchMedia("(min-width: 821px) and (hover: hover) and (pointer: fine)").matches&&event.target===event.currentTarget&&(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom);}} onClick={event=>{const rect=event.currentTarget.getBoundingClientRect();if(backdrop.current&&!busy&&event.target===event.currentTarget&&(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom))event.currentTarget.close();backdrop.current=false;}} onCancel={event=>{if(busy)event.preventDefault();}} onClose={onClose} aria-labelledby="catalog-title" dir={fa?"rtl":"ltr"}><header><div><small>{fa?"مدیریت دوره":"PRODUCT SETTINGS"}</small><h2 id="catalog-title">{draft.id?(fa?"ویرایش دوره":"Edit product"):(fa?"ساخت دوره جدید":"New product")}</h2></div><button className="icon-button" disabled={busy} aria-label={fa?"بستن":"Close"} onClick={()=>dialog.current?.close()}><X/></button></header>{uploading&&<div className="catalog-upload-progress" role="status"><span>{uploading.name}</span><progress max={100} value={uploading.percent}/><small>{uploading.percent}%</small><button type="button" className="button secondary" onClick={()=>uploadRequest.current?.abort()}>{fa?"لغو آپلود":"Cancel upload"}</button></div>}<form onSubmit={save}><fieldset className="catalog-form-fields" disabled={busy}><div className="catalog-editor"><section><h3>01 <span>{fa?"مشخصات و فروش":"Product & pricing"}</span></h3><label>{fa?"نام دوره":"Product name"}<input required maxLength={100} value={draft.title} onChange={e=>set("title",e.target.value)}/></label><label>{fa?"توضیحات قبل از خرید":"Before-purchase description"}<textarea rows={3} maxLength={1500} value={draft.description} onChange={e=>set("description",e.target.value)}/></label><div className="catalog-fields"><label>{fa?"قیمت (تومان)":"Price (Toman)"}<input type="number" min={1000} max={1000000000} step={1} required value={draft.price_irr} onChange={e=>set("price_irr",Number(e.target.value))}/></label>{!["lifetime","once"].includes(unit)&&<label>{fa?"مدت اعتبار":"Duration"}<input type="number" required min={1} max={Math.floor(36500/factor)} step={1} value={draft.duration_days/factor} onChange={e=>set("duration_days",Number(e.target.value)*factor)}/></label>}<SelectMenu label={fa?"واحد مدت":"Duration unit"} value={unit} options={durationUnits(fa)} onChange={value=>setDraft(old=>({...old,duration_unit:value,duration_days:value==="lifetime"?0:value==="once"?-1:(durationFactors[value]??1)*Math.max(1,Math.min(Math.floor(36500/(durationFactors[value]??1)),Math.round(old.duration_days/factor))),delivery_mode:value==="once"?"content":old.delivery_mode}))}/></div><div className="catalog-placement">
  <h4><Layers/>{fa?"جایگاه در ویترین":"Storefront position"}</h4>
  <p>{fa?"مشخص کن این دوره قبل از کدام دوره در فهرست خرید بات دیده شود.":"Choose where this course appears in the bot’s purchase list."}</p>
  <SelectMenu label={fa?"محل نمایش دوره":"Display position"} value={draft.before_id===undefined?"keep":draft.before_id===null?"last":String(draft.before_id)}
    options={[...(draft.id?[["keep",fa?"حفظ جایگاه فعلی":"Keep current position"] as [string,string]]:[]),...products.filter(p=>p.id!==draft.id).map(p=>[String(p.id),(fa?"پیش از ":"Before ")+p.title] as [string,string]),["last",fa?"انتهای ویترین":"End of storefront"]]}
    onChange={value=>set("before_id",value==="keep"?undefined:value==="last"?null:Number(value))}/>
  <div className="catalog-position-preview"><GripVertical/><strong>{draft.title||(fa?"این دوره":"This course")}</strong><span>{draft.before_id===undefined?(fa?"جایگاه فعلی":"Current position"):draft.before_id===null?(fa?"آخر فهرست":"Last in list"):(fa?"قبل از ":"Before ")+products.find(p=>p.id===draft.before_id)?.title}</span></div>
</div>
<div className="catalog-visibility" data-active={draft.active}>
  <div>{draft.active?<Eye/>:<EyeOff/>}<h4>{fa?"وضعیت فروش در بات":"Bot storefront visibility"}</h4></div>
  <div className="catalog-visibility-options" role="group" aria-label={fa?"وضعیت فروش در بات":"Bot storefront visibility"}>
    <button type="button" aria-pressed={!draft.active} onClick={()=>set("active",false)}><EyeOff/>{fa?"پنهان / پیش‌نویس":"Hidden / draft"}{!draft.active&&<Check/>}</button>
    <button type="button" aria-pressed={draft.active} onClick={()=>set("active",true)}><Eye/>{fa?"نمایش و فروش":"Visible for sale"}{draft.active&&<Check/>}</button>
  </div>
  <p>{draft.active?(fa?"پس از ذخیره، کاربران می‌توانند این دوره را در بات ببینند و بخرند.":"After saving, customers can see and buy this course in the bot."):(fa?"پس از ذخیره از خریدهای جدید پنهان می‌شود؛ دسترسی خریداران قبلی حفظ می‌شود.":"After saving, hidden from new purchases. Existing buyers keep their access.")}</p>
</div></section><section><h3>02 <span>{fa?"اطلاعات خریدار":"Buyer information"}</span></h3><p>{fa?"فقط موارد موردنیاز این دوره را انتخاب کن. اطلاعات ثابت قبلی دوباره پرسیده نمی‌شود. برای دوره با ارزیابی بدنی، چهار عکس تازه از مردان دریافت می‌شود؛ عکس بانوان اختیاری است.":"Select what this product needs. Saved static details are reused; body assessment requests four fresh photos from men; women may skip photos."}</p><div className="catalog-checks">{fields.map(([key,persian,english])=><label key={key}><input type="checkbox" checked={draft.form_fields.includes(key)} onChange={e=>set("form_fields",e.target.checked?[...draft.form_fields,key]:draft.form_fields.filter(f=>f!==key))}/>{fa?persian:english}</label>)}</div></section><section className="catalog-delivery"><h3>03 <span>{fa?"پس از تأیید پرداخت":"After verified payment"}</span></h3><div className="catalog-modes">{modes.map(([key,title,description])=><button type="button" key={key} aria-pressed={draft.delivery_mode===key} disabled={unit==="once"&&key!=="content"} onClick={()=>set("delivery_mode",key)}><strong>{title}{draft.delivery_mode===key&&<Check/>}</strong><small>{description}</small></button>)}</div>{draft.delivery_mode==="content" ? <DeliveryBundleFields automatic lang={lang} message={draft.response_text} onMessageChange={value=>set("response_text",value)} links={draft.content_urls??(draft.content_url?[draft.content_url]:[])} onLinksChange={urls=>setDraft(old=>({...old,content_urls:urls,content_url:urls[0]??""}))} maxLength={2000}>
<DeliveryFilePicker lang={lang} count={draft.assets?.length??0} description={fa?"پس از پرداخت، فایل‌ها خودکار برای خریدار فرستاده می‌شوند.":"Files are sent automatically after payment."} disabled={busy} onFiles={files=>void upload(files)}/>
<ul className="catalog-assets">{(draft.assets??(draft.asset_id?[{id:draft.asset_id,filename:draft.filename??"File"}]:[])).map(asset=><CatalogAsset key={asset.id} asset={asset} fa={fa} source={previewUrls[asset.id]??`/api/catalog-assets/${asset.id}/preview`} onPreview={setPreview} onRemove={()=>{
  const url=localPreviews.current.get(asset.id);if(url){URL.revokeObjectURL(url);localPreviews.current.delete(asset.id);}
  setPreviewUrls(old=>{const next={...old};delete next[asset.id];return next;});
  setDraft(old=>{const assets=(old.assets??[]).filter(a=>a.id!==asset.id);return {...old,assets,asset_ids:assets.map(a=>a.id),asset_id:assets[0]?.id??null,filename:undefined};});
}}/>)}</ul>
{!downloadReady&&(draft.assets??[]).some(a=>(a.byte_size??0)>50*1024*1024)&&<p className="staff-feedback" role="status">{fa?"فایل آپلود شده، اما تلگرام برای ارسال مستقیم فایل جدید سقف ۵۰ مگابایت دارد. برای تحویل فایل بزرگ‌تر، مدیر فنی باید دسترسی عمومی امن به دانلود از همین سرور را فعال کند.":"The file is uploaded. Telegram limits direct uploads to 50 MB per file. For larger files, your technical administrator must enable secure public downloads from this server."}</p>}
{unit==="once"&&<p className="catalog-delivery-hint"><Check/>{fa?"تحویل یک‌باره: فایل‌ها پس از خرید یک‌بار در همین تلگرام ارسال می‌شوند و در گفت‌وگوی خریدار باقی می‌مانند.":"One-time delivery: files are sent once after purchase and remain in the buyer’s Telegram conversation."}</p>}
</DeliveryBundleFields> : <label>{fa?"پیام پس از پرداخت":"Post-payment message"}<textarea rows={3} maxLength={2000} value={draft.response_text} placeholder={fa?"در حالت اختصاصی: زمان آماده‌سازی و مرحله بعد را توضیح بده…":"For custom programs: explain preparation time and the next step…"} onChange={e=>set("response_text",e.target.value)}/></label>}{draft.delivery_mode==="channel"&&<div className="catalog-channel"><SelectMenu label={fa?"کانال متصل":"Connected channel"} value={String(draft.channel_id??"")} options={[["",fa?"انتخاب کانال":"Select channel"],...channelList.map(c=>[String(c.chat_id),c.title] as [string,string])]} onChange={value=>set("channel_id",value?Number(value):null)}/><details><summary><Radio/>{fa?"اتصال کانال خصوصی جدید":"Connect a private channel"}</summary><p>{fa?"بات را با اجازه دعوت و حذف اعضا ادمین کانال کن و شناسه عددی کانال را وارد کن. ورود فقط برای حساب خریدار تأیید می‌شود. اعضای قدیمی ناشناخته قابل فهرست‌کردن نیستند؛ برای کانال اشتراکی از کانال خالی شروع کن.":"Make the bot an admin with invite and ban rights, then enter the channel ID. Only the buyer’s account is admitted. Telegram cannot list pre-existing members; start with an empty subscription channel."}</p><div className="catalog-connect"><input aria-label={fa?"شناسه کانال":"Channel ID"} inputMode="text" placeholder="-100…" value={channelInput} onChange={e=>setChannelInput(e.target.value)}/><button type="button" className="button secondary" disabled={busy||!channelInput} onClick={()=>void connect()}>{fa?"بررسی و اتصال":"Verify & connect"}</button></div></details>{channelList.find(c=>c.chat_id===draft.channel_id)?.last_error&&<p role="alert">{fa?"بررسی عضویت با خطا مواجه شده؛ دسترسی‌های بات را بررسی و کانال را دوباره متصل کن.":"Membership checks failed. Check bot permissions and reconnect."}</p>}<p>{fa?"اعتبار از فعال‌سازی پس از پرداخت شروع می‌شود. تمدید به زمان باقی‌مانده اضافه می‌شود؛ بررسی اعضا هر ۸ ساعت انجام می‌شود.":"Access starts after payment activation. Renewals extend remaining time; membership is checked every 8 hours."}</p></div>}</section></div>{error&&<p role="alert" className="staff-feedback error">{error}</p>}<p className="catalog-duration-note">{fa?"هر ماه ۳۰ روز و هر سال ۳۶۵ روز است؛ دورهٔ دائمی پایان ندارد.  اعتبار برنامهٔ اختصاصی از تحویل و محصولات آماده از پرداخت و تحویل خودکار شروع می‌شود.":"Each month is 30 days; each year is 365 days. Lifetime access does not expire. Custom programs start on delivery; ready-made purchases start after verified payment and fulfillment."}</p></fieldset><footer>{draft.id&&<button type="button" className="button danger" disabled={busy} onClick={()=>{setArchiveError(false);setConfirmArchive(true);}}><Archive/>{fa?"حذف از فروشگاه":"Archive product"}</button>}<button className="button primary" disabled={busy}>{busy?<LoaderCircle className="spin"/>:<Save/>}{fa?"ذخیره دوره":"Save product"}</button></footer></form>{preview&&<CatalogPreview media={preview} lang={lang} onClose={()=>setPreview(null)}/ >}{confirmArchive&&<ArchiveConfirmation fa={fa} title={draft.title} busy={busy} error={archiveError} onCancel={()=>setConfirmArchive(false)} onConfirm={()=>void archive()}/>}</dialog>;
}


function catalogPreviewKind(name:string):PreviewMedia["kind"] {
  if(/\.(jpe?g|png|webp|gif)$/i.test(name))return "image";
  if(/\.(mp4|mov|webm)$/i.test(name))return "video";
  return "file";
}

function CatalogAsset({asset,source,fa,onRemove,onPreview}:{asset:Asset;source:string;fa:boolean;onRemove:()=>void;onPreview:(media:PreviewMedia)=>void}) {
  const [failed,setFailed]=useState(false);
  const kind=catalogPreviewKind(asset.filename),canPreview=kind!=="file"&&!failed;
  return <li>
    <button type="button" className="catalog-asset-preview" disabled={!canPreview} aria-label={(fa?"پیش‌نمایش ":"Preview ")+asset.filename} onClick={()=>onPreview({source,kind,name:asset.filename})}>
      {canPreview&&kind==="image"?<img src={source} alt="" loading="lazy" decoding="async" onError={()=>setFailed(true)}/>:canPreview&&kind==="video"?<><video src={source+"#t=0.1"} muted playsInline preload="metadata" onError={()=>setFailed(true)}/><Play className="catalog-video-play"/></>:<FileText/>}
    </button>
    <span><strong dir="auto">{asset.filename}</strong><small>{asset.byte_size!==undefined&&<>{new Intl.NumberFormat(fa?"fa-IR":"en",{maximumFractionDigits:1}).format(asset.byte_size/1024/1024)} MB · </>}{canPreview?(fa?"برای پیش‌نمایش لمس کن":"Tap thumbnail to preview"):(fa?"پیوست · بدون پیش‌نمایش در این مرورگر":"Attachment · no browser preview")}</small></span>
    <button type="button" className="icon-button" aria-label={(fa?"حذف ":"Remove ")+asset.filename} onClick={onRemove}><X/></button>
  </li>;
}

function CatalogPreview({media,lang,onClose}:{media:PreviewMedia;lang:Lang;onClose:()=>void}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{ref.current?.showModal();},[]);
  return <dialog ref={ref} className="catalog-media-dialog" aria-label={media.name} onClose={event=>{event.stopPropagation();onClose();}} onCancel={event=>event.stopPropagation()} onKeyDownCapture={event=>{if(event.key==="Escape"){event.preventDefault();event.stopPropagation();ref.current?.close();}}}>
    <MediaViewer media={media} lang={lang} onClose={()=>ref.current?.close()}/>
  </dialog>;
}

function ArchiveConfirmation({fa,title,busy,error,onCancel,onConfirm}:{fa:boolean;title:string;busy:boolean;error:boolean;onCancel:()=>void;onConfirm:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{dialog.current?.showModal();},[]);
  return <dialog ref={dialog} className="staff-confirm catalog-confirm" role="alertdialog" aria-labelledby="catalog-archive-title" aria-describedby="catalog-archive-description"
    onClose={event=>{event.stopPropagation();onCancel();}} onCancel={event=>{event.stopPropagation();if(busy)event.preventDefault();}}>
    <i><Archive/></i><h3 id="catalog-archive-title">{fa?"این دوره از فروشگاه حذف شود؟":"Archive this course?"}</h3>
    <strong className="catalog-confirm-title">{title}</strong>
    <p id="catalog-archive-description">{fa?"از ویترین بات حذف می‌شود، اما سفارش‌ها، فایل‌ها و دسترسی خریداران قبلی حفظ می‌شوند.":"It will be removed from the bot storefront. Existing orders, files and buyer access are preserved."}</p>
    {error&&<p role="alert" className="staff-confirm-error">{fa?"حذف انجام نشد؛ اتصال را بررسی کن و دوباره تلاش کن.":"Could not archive. Check your connection and try again."}</p>}
    <div><button type="button" className="button secondary" autoFocus disabled={busy} onClick={()=>dialog.current?.close()}>{fa?"انصراف":"Cancel"}</button><button type="button" className="button danger" disabled={busy} onClick={onConfirm}>{busy?<LoaderCircle className="spin"/>:<Archive/>}{fa?"تأیید حذف":"Confirm archive"}</button></div>
  </dialog>;
}

const durationFactors:Record<string,number>={days:1,weeks:7,months:30,years:365};
function durationUnits(fa:boolean):[string,string][]{return [["days",fa?"روز":"Days"],["weeks",fa?"هفته":"Weeks"],["months",fa?"ماه":"Months"],["years",fa?"سال":"Years"],["lifetime",fa?"دائمی":"Lifetime"],["once",fa?"یک‌بار مصرف":"One-time"]];}
function durationText(product:Product,fa:boolean){
  if(product.duration_days===0)return fa?"دائمی":"Lifetime";
  if(product.duration_days===-1)return fa?"یک‌بار مصرف":"One-time";
  const unit=product.duration_unit??"days";
  return new Intl.NumberFormat(fa?"fa-IR":"en").format(product.duration_days/(durationFactors[unit]??1))+" "+durationUnits(fa).find(([key])=>key===unit)?.[1];
}
function ProductOrder({items,nextId,fa,disabled,onMove,start}:{start:number;items:Product[];nextId:number|null;fa:boolean;disabled:boolean;onMove:(id:number,before:number|null)=>void}){
  const [drag,setDrag]=useState<number|null>(null),[slot,setSlot]=useState<number|null>(null);
  const gesture=useRef<{index:number;y:number;slot:number|null}|null>(null);
  const reset=()=>{gesture.current=null;setDrag(null);setSlot(null);};
  // A slot is the gap BEFORE an item (items.length is the final gap), never a replacement.
  const drop=(index:number,position:number)=>{if(disabled||position===index||position===index+1)return;onMove(items[index].id!,items[position]?.id??nextId);};
  return <section id="catalog-order" className="catalog-sort glass" aria-busy={disabled} aria-label={fa?"ترتیب دوره‌ها":"Product order"}>
    <header><div><h2>{fa?"ترتیب نمایش در فروشگاه بات":"Bot storefront order"}</h2><p>{fa?"دستگیره را بکش؛ خط روشن، محل درج بین دو دوره است. فلش‌ها هم همین کار را می‌کنند.":"Drag a handle. The highlighted line shows where the product will be inserted. Or use the arrows."}</p></div><span role="status">{disabled?<><LoaderCircle className="spin"/>{fa?"ذخیره…":"Saving…"}</>:<><Check/>{fa?"ذخیره خودکار":"Auto-save"}</>}</span></header>
    {items.map((product,index)=><div key={product.id} data-order-index={index} className={`catalog-sort-row${drag===index?" is-dragging":""}`}>
      {(slot===index||(index===items.length-1&&slot===items.length))&&<i className={`catalog-insert-line${slot===items.length?" at-end":""}`} aria-hidden="true"><span>{fa?"اینجا قرار می‌گیرد":"Insert here"}</span></i>}
      <button type="button" className="icon-button catalog-drag" disabled={disabled} aria-label={(fa?"جابجایی ":"Move ")+product.title}
        onPointerDown={e=>{if(!e.isPrimary||e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);gesture.current={index,y:e.clientY,slot:null};}}
        onPointerMove={e=>{
          const current=gesture.current;if(!current||Math.abs(e.clientY-current.y)<6&&drag===null)return;
          setDrag(current.index);
          const list=e.currentTarget.closest("section")!,rect=list.getBoundingClientRect();
          const rows=Array.from(list.querySelectorAll<HTMLElement>("[data-order-index]"));
          let position:number|null=null;
          if(e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom){
            position=rows.findIndex(row=>{const bounds=row.getBoundingClientRect();return e.clientY<bounds.top+bounds.height/2;});
            if(position===-1)position=items.length;
            if(position===current.index||position===current.index+1)position=null;
          }
          current.slot=position;setSlot(position);
        }}
        onPointerUp={()=>{const current=gesture.current;if(current?.slot!=null)drop(current.index,current.slot);reset();}}
        onPointerCancel={reset} onLostPointerCapture={reset}
        onKeyDown={e=>{if(e.key==="Escape")reset();if(e.key==="ArrowUp"&&index>0){e.preventDefault();drop(index,index-1);}if(e.key==="ArrowDown"&&index<items.length-1){e.preventDefault();drop(index,index+2);}}}><GripVertical/></button>
      <b className="catalog-sort-position">{new Intl.NumberFormat(fa?"fa-IR":"en").format(start+index+1)}</b><span>{product.title}<small>{product.active?(fa?"در حال فروش":"On sale"):(fa?"پیش‌نویس / متوقف":"Draft / paused")}</small></span>
      <button type="button" className="icon-button" disabled={disabled||index===0} aria-label={fa?"انتقال به بالا":"Move up"} onClick={()=>drop(index,index-1)}><ArrowUp/></button>
      <button type="button" className="icon-button" disabled={disabled||index===items.length-1} aria-label={fa?"انتقال به پایین":"Move down"} onClick={()=>drop(index,index+2)}><ArrowDown/></button>
    </div>)}
  </section>;
}
