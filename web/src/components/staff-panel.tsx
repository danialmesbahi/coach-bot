"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Copy, LoaderCircle, ShieldCheck, UsersRound, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Lang, Session } from "@/lib/types";

export const can = (session: Session, permission: string) => session.role === "platform" || session.role === "leader" || session.permissions.includes(permission);
type Account = { id:number; telegram_id:number; username:string; display_name:string; role:Session["role"]; permissions:string[]; status:"active"|"invited"|"disabled"; session_version:number };
type Team = { items:Account[]; total:number; permissions:Record<string,[string,string]>; templates:Record<string,string[]> };
type Audit = { items:Array<{id:number;actor_name:string;action:string;target_type:string;target_id:number;created_at:string}>; next:number|null };

export function StaffPanel({session,lang,onClose}:{session:Session;lang:Lang;onClose:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const fa=lang==="fa", manager=session.role!=="staff";
  const [tab,setTab]=useState<"profile"|"team"|"audit">("profile");
  const [team,setTeam]=useState<Team>(), [audit,setAudit]=useState<Audit>();
  const [page,setPage]=useState(1), [cursor,setCursor]=useState<number|null>(null);
  const [busy,setBusy]=useState(false), [feedback,setFeedback]=useState("");
  const [invite,setInvite]=useState("");
  const [name,setName]=useState(session.displayName);
  const [editing,setEditing]=useState<Account|null>(null), [creating,setCreating]=useState(false);
  const [draft,setDraft]=useState({display_name:"",username:"",telegram_id:"",role:"staff",permissions:[] as string[]});
  const roleName=(role:string)=>({platform:fa?"تیم توسعه":"Platform",leader:fa?"مربی اصلی":"Leader",staff:fa?"همکار":"Staff"}[role]??role);
  const reload=useCallback((signal?:AbortSignal)=>{
    if(tab==="team") return api<Team>(`/api/staff/team?page=${page}`,session.csrf,{signal}).then(setTeam);
    if(tab==="audit") return api<Audit>(`/api/staff/audit${cursor?`?before=${cursor}`:""}`,session.csrf,{signal}).then(setAudit);
    return Promise.resolve();
  },[tab,page,cursor,session.csrf]);
  useEffect(()=>{
    dialog.current?.showModal();
    const old=document.body.style.overflow; document.body.style.overflow="hidden";
    return ()=>{document.body.style.overflow=old;};
  },[]);
  useEffect(()=>{const controller=new AbortController(); void reload(controller.signal).catch(()=>{if(!controller.signal.aborted)setFeedback(fa?"دریافت اطلاعات انجام نشد.":"Could not load data.");});return ()=>controller.abort();},[reload,fa]);
  const run=async(path:string,body:unknown)=>{
    if(busy)return;
    setBusy(true);setFeedback("");setInvite("");
    try {
      const result=await api<{invite?:string}>(path,session.csrf,{method:"POST",body:JSON.stringify(body)});
      if(result.invite)setInvite(`${location.origin}/#invite=${result.invite}`);
      setFeedback(fa?"ذخیره شد":"Saved"); setCreating(false);setEditing(null);await reload();
    } catch(error) { setFeedback(error instanceof ApiError && error.status===409 ? (fa?"اطلاعات تغییر کرده یا حساب/لیدر تکراری است؛ تازه‌سازی کن.":"Account changed or account/leader already exists. Refresh first.") : (fa?"عملیات انجام نشد؛ اطلاعات و دسترسی را بررسی کن.":"Action failed. Check the details and permissions.")); }
    finally{setBusy(false);}
  };
  const edit=(item:Account)=>{setEditing(item);setCreating(false);setDraft({display_name:item.display_name,username:item.username,telegram_id:String(item.telegram_id),role:item.role,permissions:item.permissions});};
  const submit=(event:FormEvent)=>{event.preventDefault();void run("/api/staff/team",editing?{action:"permissions",id:editing.id,version:editing.session_version,permissions:draft.permissions}:{...draft,action:"create",telegram_id:Number(draft.telegram_id)});};
  return <dialog ref={dialog} className="staff-dialog" onClose={onClose} onClick={event=>{if(event.target===dialog.current)dialog.current?.close();}} dir={fa?"rtl":"ltr"}>
    <header className="staff-heading"><div><ShieldCheck/><div><small>{roleName(session.role)}</small><h2>{fa?"فضای تیم":"Team workspace"}</h2></div></div><button className="icon-button" onClick={()=>dialog.current?.close()} aria-label={fa?"بستن":"Close"}><X/></button></header>
    <nav className="staff-tabs" aria-label={fa?"مدیریت تیم":"Team management"}>{(["profile",...(manager?["team","audit"]:[])] as typeof tab[]).map(value=><button key={value} aria-pressed={tab===value} onClick={()=>{setTab(value);setFeedback("");}}>{({profile:fa?"پروفایل من":"My profile",team:fa?"اعضای تیم":"Members",audit:fa?"گزارش فعالیت":"Activity log"})[value]}</button>)}</nav>
    <div className="staff-body">
      {feedback&&<p role="status" className="staff-feedback">{feedback}</p>}
      {invite&&<section className="staff-invite"><strong>{fa?"دعوت‌نامهٔ یک‌بارمصرف · معتبر تا ۲۴ ساعت":"One-use invitation · valid for 24 hours"}</strong><p>{fa?"این لینک و نام کاربری را فقط برای صاحب حساب بفرست. تأیید تلگرام همان فرد هم لازم است.":"Send this link and username only to the account owner. Their Telegram approval is also required."}</p><input readOnly aria-label="Invitation URL" dir="ltr" value={invite} onFocus={event=>event.currentTarget.select()}/><button className="button secondary" onClick={()=>(navigator.clipboard ? navigator.clipboard.writeText(invite) : Promise.reject(new Error("Clipboard unavailable"))).then(()=>setFeedback(fa?"کپی شد":"Copied")).catch(()=>setFeedback(fa?"لینک را انتخاب و کپی کن":"Select and copy the link"))}><Copy/>{fa?"کپی لینک":"Copy link"}</button></section>}
      {tab==="profile"&&<form className="staff-form" onSubmit={event=>{event.preventDefault();void run("/api/staff/profile",{display_name:name});}}><h3>{session.displayName}</h3><p dir="ltr">@{session.username} · {session.telegramId}</p><label>{fa?"نام نمایشی در تیم":"Team display name"}<input required maxLength={80} value={name} onChange={event=>setName(event.target.value)}/></label><p>{fa?"نامت کنار پیام‌ها و فعالیت‌های جدید ثبت می‌شود. نام فعالیت‌های گذشته تغییر نمی‌کند.":"Your name appears on new messages and activity. Historical attribution stays unchanged."}</p><button className="button primary" disabled={busy}>{busy?<LoaderCircle className="spin"/>:<Check/>}{fa?"ذخیره نام":"Save name"}</button><button type="button" className="button secondary" onClick={()=>void api("/api/logout",session.csrf,{method:"POST"}).then(()=>location.reload())}>{fa?"خروج امن":"Sign out"}</button></form>}
      {tab==="team"&&<>
        <div className="staff-section-title"><h3><UsersRound/>{team?.total??0} {fa?"عضو":"members"}</h3><button className="button primary" onClick={()=>{setCreating(true);setEditing(null);setDraft({display_name:"",username:"",telegram_id:"",role:"staff",permissions:[]});}}>{fa?"افزودن همکار":"Add member"}</button></div>
        {(creating||editing)&&<form className="staff-form staff-editor" onSubmit={submit}><h3>{editing?editing.display_name:fa?"همکار جدید":"New member"}</h3>{creating&&<div className="staff-fields"><label>{fa?"نام":"Name"}<input required maxLength={80} value={draft.display_name} onChange={e=>setDraft({...draft,display_name:e.target.value})}/></label><label>{fa?"نام کاربری ورود":"Login username"}<input required pattern="[a-zA-Z0-9_.\-]{3,40}" autoComplete="off" dir="ltr" value={draft.username} onChange={e=>setDraft({...draft,username:e.target.value})}/></label><label>{fa?"شناسه عددی تلگرام":"Telegram numeric ID"}<input required inputMode="numeric" pattern="[0-9]+" dir="ltr" value={draft.telegram_id} onChange={e=>setDraft({...draft,telegram_id:e.target.value})}/></label>{session.role==="platform"&&<label>{fa?"سطح حساب":"Account level"}<select value={draft.role} onChange={e=>setDraft({...draft,role:e.target.value})}>{["staff","leader","platform"].map(role=><option key={role} value={role}>{roleName(role)}</option>)}</select></label>}</div>}
        {draft.role==="staff"&&<><div className="staff-template">{Object.entries(team?.templates??{}).map(([key,permissions])=><button type="button" key={key} onClick={()=>setDraft({...draft,permissions})}>{({support:fa?"پشتیبانی":"Support",designer:fa?"طراح برنامه":"Designer",finance:fa?"مالی":"Finance",observer:fa?"ناظر":"Observer"})[key]}</button>)}</div><fieldset className="staff-permissions"><legend>{fa?"دسترسی‌ها":"Permissions"}</legend>{Object.entries(team?.permissions??{}).map(([key,label])=><label key={key}><input type="checkbox" checked={draft.permissions.includes(key)} onChange={e=>setDraft({...draft,permissions:e.target.checked?[...draft.permissions,key]:draft.permissions.filter(p=>p!==key)})}/><span>{label[fa?0:1]}</span></label>)}</fieldset></>}
        {draft.role!=="staff"&&<p>{fa?"این سطح دسترسی کامل مدیریتی دارد. فقط برای افراد مورداعتماد ایجاد کن.":"This level has full management privileges. Create only for trusted people."}</p>}
        <div className="staff-actions"><button className="button primary" disabled={busy}>{fa?"ذخیره":"Save"}</button><button type="button" className="button secondary" onClick={()=>{setCreating(false);setEditing(null);}}>{fa?"لغو":"Cancel"}</button></div></form>}
        <div className="staff-members">{team?.items.map(item=>{const editable=item.id!==session.staffId&&(session.role==="platform"||item.role==="staff");return <article className="staff-member" key={item.id}><div><strong>{item.display_name}</strong><small dir="ltr">@{item.username} · {item.telegram_id}</small><span>{roleName(item.role)} · {({active:fa?"فعال":"Active",invited:fa?"دعوت‌شده":"Invited",disabled:fa?"غیرفعال":"Disabled"})[item.status]}</span></div>{editable&&<div className="staff-actions">{item.role==="staff"&&<button onClick={()=>edit(item)}>{fa?"دسترسی‌ها":"Permissions"}</button>}{item.status!=="disabled"&&<button disabled={busy} onClick={()=>{if(confirm(fa?"دعوت‌نامه جدید صادر و نشست‌های قبلی بسته شود؟":"Issue a new invitation and revoke existing sessions?"))void run("/api/staff/team",{action:"invite",id:item.id,version:item.session_version});}}>{fa?"دعوت / بازیابی":"Invite / reset"}</button>}<button disabled={busy} onClick={()=>{if(confirm(fa?"نشست‌های این حساب بسته می‌شوند. ادامه می‌دهی؟":"This account’s sessions will be revoked. Continue?"))void run("/api/staff/team",{action:item.status==="disabled"?"enable":"disable",id:item.id,version:item.session_version});}}>{item.status==="disabled"?(fa?"فعال‌سازی":"Enable"):(fa?"غیرفعال‌سازی":"Disable")}</button><button disabled={busy} onClick={()=>void run("/api/staff/team",{action:"revoke",id:item.id,version:item.session_version})}>{fa?"بستن نشست‌ها":"Revoke sessions"}</button></div>}</article>;})}</div>
        <div className="staff-pager"><button disabled={page<=1} onClick={()=>setPage(page-1)}>{fa?<ArrowRight/>:<ArrowLeft/>}</button><span>{page}</span><button disabled={page*20>=(team?.total??0)} onClick={()=>setPage(page+1)}>{fa?<ArrowLeft/>:<ArrowRight/>}</button></div>
      </>}
      {tab==="audit"&&<><p>{fa?"فعالیت‌ها فقط خواندنی‌اند؛ رمزها و محتوای خصوصی دعوت‌نامه ثبت نمی‌شوند.":"Read-only activity history. Passwords and invitation secrets are never recorded."}</p><ol className="staff-audit">{audit?.items.map(item=><li key={item.id}><strong>{item.actor_name??(fa?"سیستم / سابق":"System / legacy")}</strong><span>{item.action.replaceAll("_"," ")} · {item.target_type} #{item.target_id}</span><time>{new Intl.DateTimeFormat(fa?"fa-IR":"en-GB",{dateStyle:"medium",timeStyle:"short"}).format(new Date(item.created_at))}</time></li>)}</ol><div className="staff-actions"><button onClick={()=>setCursor(null)} disabled={!cursor}>{fa?"آخرین فعالیت‌ها":"Latest"}</button><button disabled={!audit?.next} onClick={()=>setCursor(audit?.next??null)}>{fa?"قدیمی‌تر":"Older"}</button></div></>}
    </div>
  </dialog>;
}

type CollaborationData={assignment:{staff_id:number|null;version:number;display_name?:string};notes:Array<{id:number;author_name:string;body:string;created_at:string}>;members:Array<{id:number;display_name:string}>};
export function CollaborationPanel({kind,id,session,lang,version}:{kind:"thread"|"order";id:number;session:Session;lang:Lang;version:number}) {
  const [data,setData]=useState<CollaborationData>(),[note,setNote]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState(false);
  const path=`/api/collaboration/${kind}/${id}`,fa=lang==="fa";
  const editable=can(session,kind==="thread"?"chats.reply":"orders.review");
  useEffect(()=>{const controller=new AbortController();void api<CollaborationData>(path,session.csrf,{signal:controller.signal}).then(setData).catch(()=>{if(!controller.signal.aborted)setError(true);});return()=>controller.abort();},[path,session.csrf,version]);
  const change=async(body:unknown)=>{if(busy)return;setBusy(true);setError(false);try{setData(await api<CollaborationData>(path,session.csrf,{method:"POST",body:JSON.stringify(body)}));setNote("");}catch{setError(true);}finally{setBusy(false);}};
  return <details className="collaboration-panel"><summary>{fa?"همکاری تیم":"Team handoff"}<span>{data?.assignment.display_name??(fa?"بدون مسئول":"Unassigned")}</span></summary><div>{error&&<p role="alert">{fa?"ذخیره نشد؛ ممکن است همکار دیگری مسئولیت را گرفته باشد. صفحه را دوباره باز کن.":"Could not save; another teammate may have claimed this task. Reopen to refresh."}</p>}{editable&&data&&<div className="staff-actions">{session.role!=="staff"?<select aria-label={fa?"مسئول":"Assignee"} value={data.assignment.staff_id??""} disabled={busy} onChange={e=>void change({action:"assign",staff_id:e.target.value?Number(e.target.value):null,version:data.assignment.version})}><option value="">{fa?"بدون مسئول":"Unassigned"}</option>{data.members.map(member=><option value={member.id} key={member.id}>{member.display_name}</option>)}</select>:<button disabled={busy||Boolean(data.assignment.staff_id&&data.assignment.staff_id!==session.staffId)} onClick={()=>void change({action:"assign",staff_id:data.assignment.staff_id===session.staffId?null:session.staffId,version:data.assignment.version})}>{data.assignment.staff_id===session.staffId?(fa?"آزاد کردن":"Release"):(fa?"من انجام می‌دهم":"Assign to me")}</button>}</div>}
  {editable&&<form onSubmit={e=>{e.preventDefault();void change({action:"note",text:note});}}><label>{fa?"یادداشت داخلی · برای شاگرد ارسال نمی‌شود":"Internal note · never sent to the client"}<textarea value={note} maxLength={2000} onChange={e=>setNote(e.target.value)}/></label><button disabled={busy||!note.trim()}>{fa?"ثبت یادداشت":"Add note"}</button></form>}{data?.notes.map(item=><article key={item.id}><strong>{item.author_name}</strong><p>{item.body}</p></article>)}</div></details>;
}
