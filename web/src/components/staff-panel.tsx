"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, Check, LoaderCircle, LogOut, ShieldCheck, TriangleAlert, UsersRound, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { SelectMenu } from "@/components/select-menu";
import { PasswordField } from "@/components/password-field";
import { passwordPolicyError } from "@/lib/password-policy";
import type { Lang, Session } from "@/lib/types";

export const can = (session: Session, permission: string) => session.role === "platform" || session.role === "leader" || session.permissions.includes(permission);
type Account = { id:number; telegram_id:number|null; username:string; display_name:string; role:Session["role"]; permissions:string[]; status:"active"|"invited"|"disabled"; session_version:number };
type Team = { items:Account[]; total:number; permissions:Record<string,[string,string]>; templates:Record<string,string[]> };
type AuditItem = {id:number;actor_name:string|null;actor_role:string|null;action:string;target_type:string;target_id:number;target_name:string|null;created_at:string};
type Audit = { items:AuditItem[]; next:number|null };
type Notice = {kind:"success"|"error";text:string};

export function LogoutButton({session,lang,className="button danger staff-logout",children}:{session:Session;lang:Lang;className?:string;children?:ReactNode}) {
  const dialog=useRef<HTMLDialogElement>(null),titleId=useId(),descriptionId=useId();
  const [busy,setBusy]=useState(false),[error,setError]=useState(false);
  const fa=lang==="fa";
  const logout=async()=>{if(busy)return;setBusy(true);setError(false);try{await api("/api/logout",session.csrf,{method:"POST"});location.reload();}catch{setError(true);setBusy(false);}};
  return <><button type="button" className={className} onClick={()=>{setError(false);dialog.current?.showModal();}}>{children??<><LogOut/>{fa?"خروج از حساب":"Sign out"}</>}</button><dialog ref={dialog} role="alertdialog" aria-labelledby={titleId} aria-describedby={descriptionId} className="staff-confirm" onClose={event=>event.stopPropagation()} onClick={event=>{event.stopPropagation();if(event.target===dialog.current)dialog.current.close();}}><i><LogOut/></i><h3 id={titleId}>{fa?"از حساب خارج می‌شوی؟":"Sign out of this account?"}</h3><p id={descriptionId}>{fa?"برای ورود دوباره به نام کاربری و رمز عبورت نیاز داری.":"You will need your username and password to sign in again."}</p>{error&&<p className="staff-confirm-error" role="alert">{fa?"خروج انجام نشد؛ اتصال را بررسی و دوباره تلاش کن.":"Could not sign out. Check your connection and try again."}</p>}<div><button type="button" className="button secondary" autoFocus disabled={busy} onClick={()=>dialog.current?.close()}>{fa?"ماندن":"Stay signed in"}</button><button type="button" className="button danger" disabled={busy} onClick={()=>void logout()}>{busy?<LoaderCircle className="spin"/>:<LogOut/>}{fa?"خروج":"Sign out"}</button></div></dialog></>;
}

export function StaffPanel({session,lang,onClose}:{session:Session;lang:Lang;onClose:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const fa=lang==="fa",manager=session.role!=="staff";
  const [tab,setTab]=useState<"profile"|"team"|"audit">("profile");
  const [team,setTeam]=useState<Team>(),[audit,setAudit]=useState<Audit>();
  const [page,setPage]=useState(1),[cursor,setCursor]=useState<number|null>(null);
  const [busy,setBusy]=useState(false),[feedback,setFeedback]=useState<Notice|null>(null);
  const [name,setName]=useState(session.displayName);
  const [currentPassword,setCurrentPassword]=useState(""),[ownPassword,setOwnPassword]=useState("");
  const [currentPasswordError,setCurrentPasswordError]=useState(""),[ownPasswordError,setOwnPasswordError]=useState(""),[draftPasswordError,setDraftPasswordError]=useState("");
  const [editing,setEditing]=useState<Account|null>(null),[creating,setCreating]=useState(false),[resetting,setResetting]=useState<Account|null>(null);
  const [draft,setDraft]=useState({display_name:"",username:"",password:"",role:"staff",permissions:[] as string[]});
  const roleName=(role:string)=>({platform:fa?"تیم توسعه":"Platform",leader:fa?"مربی اصلی":"Leader",staff:fa?"همکار":"Staff"}[role]??role);
  const actionName=(action:string)=>({staff_login:fa?"وارد پنل شد":"Signed in",staff_profile:fa?"نام نمایشی را تغییر داد":"Updated their display name",staff_password_changed:fa?"رمز ورود خود را تغییر داد":"Changed their password",staff_create:fa?"عضو جدید ساخت":"Created a team member",staff_permissions:fa?"دسترسی‌های عضو را تغییر داد":"Changed member permissions",staff_disable:fa?"حساب عضو را غیرفعال کرد":"Disabled a member",staff_enable:fa?"حساب عضو را فعال کرد":"Enabled a member",staff_reset_password:fa?"رمز عضو را بازنشانی کرد":"Reset a member password",staff_revoke:fa?"نشست‌های عضو را بست":"Revoked member sessions",internal_note:fa?"یادداشت داخلی ثبت کرد":"Added an internal note",assigned:fa?"مسئول کار را تغییر داد":"Changed task assignment",web_sales_gate:fa?"وضعیت فروش را تغییر داد":"Changed sales availability",web_approve_receipt:fa?"پرداخت را تأیید کرد":"Approved a payment",web_reject_receipt:fa?"پرداخت را رد کرد":"Rejected a payment",web_in_progress:fa?"سفارش را وارد طراحی کرد":"Moved an order to production",web_needs_info:fa?"اطلاعات بیشتر درخواست کرد":"Requested more information",web_deliver_plan:fa?"برنامه را تحویل داد":"Delivered a plan"}[action]??(fa?"یک فعالیت ثبت کرد":"Recorded an activity"));
  const targetName=(item:AuditItem)=>item.target_name??({staff:fa?"عضو تیم":"Team member",order:fa?"سفارش":"Order",thread:fa?"گفت‌وگو":"Conversation",sales:fa?"فروش":"Sales"}[item.target_type]??(fa?"رکورد":"Record"))+` #${item.target_id}`;
  const reload=useCallback((signal?:AbortSignal)=>{
    if(tab==="team")return api<Team>(`/api/staff/team?page=${page}`,session.csrf,{signal}).then(setTeam);
    if(tab==="audit")return api<Audit>(`/api/staff/audit${cursor?`?before=${cursor}`:""}`,session.csrf,{signal}).then(setAudit);
    return Promise.resolve();
  },[tab,page,cursor,session.csrf]);
  useEffect(()=>{
    dialog.current?.showModal();
    const old=document.body.style.overflow;document.body.style.overflow="hidden";
    return()=>{document.body.style.overflow=old;};
  },[]);
  useEffect(()=>{const controller=new AbortController();void reload(controller.signal).catch(()=>{if(!controller.signal.aborted)setFeedback({kind:"error",text:fa?"دریافت اطلاعات انجام نشد.":"Could not load data."});});return()=>controller.abort();},[reload,fa]);
  const closeEditor=()=>{setCreating(false);setEditing(null);setResetting(null);setDraftPasswordError("");setDraft(d=>({...d,password:""}));};
  const run=async(path:string,body:unknown)=>{
    if(busy)return;
    let signingOut=false;
    setBusy(true);setFeedback(null);
    try {
      await api(path,session.csrf,{method:"POST",body:JSON.stringify(body)});
      if(path==="/api/staff/password"){
        setOwnPassword("");setCurrentPassword("");
        setFeedback({kind:"success",text:fa?"رمز با موفقیت تغییر کرد؛ در حال خروج امن…":"Password changed. Signing you out securely…"});
        signingOut=true;
        window.setTimeout(()=>location.reload(),1200);return;
      }
      setFeedback({kind:"success",text:fa?"تغییرات با موفقیت ذخیره شد.":"Changes saved successfully."});closeEditor();await reload();
    } catch(error) {
      setFeedback({kind:"error",text:error instanceof ApiError&&error.status===409
        ?(fa?"اطلاعات تغییر کرده یا نام کاربری/مربی تکراری است؛ تازه‌سازی کن.":"Account changed or username/leader already exists. Refresh first.")
        :error instanceof ApiError&&error.status===429
          ?(fa?"تلاش‌های زیادی انجام شده؛ چند دقیقه صبر کن.":"Too many attempts. Please wait a few minutes.")
          :path==="/api/staff/password"&&error instanceof ApiError&&error.status===401
            ?(fa?"رمز فعلی درست نیست یا نشست منقضی شده است.":"Current password is incorrect or your session expired.")
            :error instanceof ApiError&&error.code==="password_policy"
              ?passwordPolicyError(path==="/api/staff/password"?ownPassword:draft.password,lang)
              :(fa?"عملیات انجام نشد؛ اطلاعات، شرایط رمز و دسترسی را بررسی کن.":"Action failed. Check the details, password requirements and permissions.")});
    } finally{if(!signingOut)setBusy(false);}
  };
  const edit=(item:Account,reset=false)=>{
    setEditing(reset?null:item);setResetting(reset?item:null);setCreating(false);
    setDraft({display_name:item.display_name,username:item.username,password:"",role:item.role,permissions:item.permissions});
  };
  const submit=(event:FormEvent)=>{
    event.preventDefault();
    if(creating&&(!draft.display_name.trim()||!/^[a-zA-Z0-9_.-]{3,40}$/.test(draft.username))){
      setFeedback({kind:"error",text:fa?"نام را وارد کن و برای نام کاربری ۳ تا ۴۰ حرف انگلیسی، عدد، نقطه، خط تیره یا زیرخط بنویس.":"Enter a name and use 3–40 letters, numbers, dots, dashes or underscores for the username."});return;
    }
    if((creating||resetting)&&passwordPolicyError(draft.password,lang)){
      setDraftPasswordError(passwordPolicyError(draft.password,lang));return;
    }
    setDraftPasswordError("");
    void run("/api/staff/team",resetting
      ?{action:"reset_password",id:resetting.id,version:resetting.session_version,password:draft.password}
      :editing?{action:"permissions",id:editing.id,version:editing.session_version,permissions:draft.permissions}
        :{...draft,action:"create"});
  };
  const savePassword=(event:FormEvent)=>{
    event.preventDefault();
    const nextError=passwordPolicyError(ownPassword,lang),currentError=currentPassword?"":(fa?"رمز فعلی را وارد کن.":"Enter your current password.");
    setOwnPasswordError(nextError);setCurrentPasswordError(currentError);
    if(nextError||currentError)return;
    void run("/api/staff/password",{current_password:currentPassword,password:ownPassword});
  };
  return <dialog ref={dialog} className="staff-dialog" onClose={onClose} onClick={event=>{if(event.target===dialog.current)dialog.current?.close();}} dir={fa?"rtl":"ltr"} aria-label={fa?"فضای تیم":"Team workspace"}>
    <header className="staff-heading"><div><ShieldCheck/><div><small>{roleName(session.role)}</small><h2>{fa?"فضای تیم":"Team workspace"}</h2></div></div><button className="icon-button" onClick={()=>dialog.current?.close()} aria-label={fa?"بستن":"Close"}><X/></button></header>
    <nav className="staff-tabs" aria-label={fa?"مدیریت تیم":"Team management"}>
      {(["profile",...(manager?["team","audit"]:[])] as typeof tab[]).map(value=><button key={value} aria-pressed={tab===value} onClick={()=>{setTab(value);setFeedback(null);closeEditor();setOwnPassword("");setCurrentPassword("");setOwnPasswordError("");setCurrentPasswordError("");}}>{({profile:fa?"پروفایل من":"My profile",team:fa?"اعضای تیم":"Members",audit:fa?"گزارش فعالیت":"Activity log"})[value]}</button>)}
    </nav>
    <div className="staff-body">
      {feedback&&<p role={feedback.kind==="error"?"alert":"status"} className={`staff-feedback ${feedback.kind}`}>{feedback.kind==="success"?<Check/>:<TriangleAlert/>}{feedback.text}</p>}
      {tab==="profile"&&<div className="staff-profile-sections">
        <form className="staff-form" noValidate onSubmit={event=>{event.preventDefault();if(!name.trim()){setFeedback({kind:"error",text:fa?"نام نمایشی را وارد کن.":"Enter a display name."});return;}void run("/api/staff/profile",{display_name:name});}}>
          <h3>{name||session.displayName}</h3><p dir="ltr">@{session.username}</p>
          <label>{fa?"نام نمایشی در تیم":"Team display name"}<input required maxLength={80} value={name} onChange={event=>setName(event.target.value)}/></label>
          <p>{fa?"این نام کنار پیام‌ها و فعالیت‌های جدید ثبت می‌شود.":"This name appears on your new messages and activity."}</p>
          <button className="button primary" disabled={busy}>{busy?<LoaderCircle className="spin"/>:<Check/>}{fa?"ذخیره نام":"Save name"}</button>
        </form>
        <form className="staff-form staff-editor" noValidate onSubmit={savePassword}>
          <h3>{fa?"تغییر رمز عبور":"Change password"}</h3>
          <PasswordField lang={lang} label={fa?"رمز فعلی":"Current password"} newPassword={false} value={currentPassword} error={currentPasswordError} onChange={value=>{setCurrentPassword(value);setCurrentPasswordError("");}}/>
          <PasswordField lang={lang} label={fa?"رمز جدید":"New password"} value={ownPassword} error={ownPasswordError} onChange={value=>{setOwnPassword(value);setOwnPasswordError("");}}/>
          <p>{fa?"پس از تغییر رمز، از همه دستگاه‌ها خارج می‌شوی. بازیابی رمز فراموش‌شده فقط توسط مدیر بالاتر انجام می‌شود.":"Changing your password signs you out on every device. Forgotten passwords can only be reset by your supervising manager."}</p>
          <button className="button primary" disabled={busy}>{fa?"ذخیره رمز و ورود مجدد":"Save password & sign in again"}</button>
        </form>
        <LogoutButton session={session} lang={lang}/>
      </div>}
      {tab==="team"&&<>
        <div className="staff-section-title"><h3><UsersRound/>{team?.total??0} {fa?"عضو":"members"}</h3>{!(creating||editing||resetting)&&<button className="button primary" onClick={()=>{closeEditor();setCreating(true);setDraft({display_name:"",username:"",password:"",role:"staff",permissions:[]});}}>{fa?"افزودن همکار":"Add member"}</button>}</div>
        {(creating||editing||resetting)&&<form className="staff-form staff-editor" noValidate onSubmit={submit}>
          <h3>{resetting?(fa?`تعیین رمز جدید · ${resetting.display_name}`:`Reset password · ${resetting.display_name}`):editing?editing.display_name:fa?"همکار جدید":"New member"}</h3>
          {creating&&<div className="staff-fields">
            <label>{fa?"نام":"Name"}<input required maxLength={80} value={draft.display_name} onChange={e=>setDraft({...draft,display_name:e.target.value})}/></label>
            <label>{fa?"نام کاربری ورود":"Login username"}<input required pattern="[a-zA-Z0-9_.\\-]{3,40}" autoComplete="off" autoCapitalize="none" spellCheck={false} dir="ltr" value={draft.username} onChange={e=>setDraft({...draft,username:e.target.value})}/></label>
            <PasswordField lang={lang} label={fa?"رمز اولیه":"Initial password"} value={draft.password} error={draftPasswordError} onChange={password=>{setDraft({...draft,password});setDraftPasswordError("");}}/>
            {session.role==="platform"&&<SelectMenu label={fa?"سطح حساب":"Account level"} value={draft.role} onChange={role=>setDraft({...draft,role})} options={["staff","leader","platform"].map(role=>[role,roleName(role)])}/>}
          </div>}
          {resetting&&<><PasswordField lang={lang} label={fa?"رمز جدید":"New password"} value={draft.password} error={draftPasswordError} onChange={password=>{setDraft({...draft,password});setDraftPasswordError("");}}/><p>{fa?"رمز را به‌صورت امن به صاحب حساب بده. همه نشست‌های قبلی بسته می‌شوند؛ حساب غیرفعال، غیرفعال می‌ماند.":"Share the password securely with the account owner. Existing sessions are revoked; disabled accounts remain disabled."}</p></>}
          {!resetting&&draft.role==="staff"&&<>
            <div className="staff-template">{Object.entries(team?.templates??{}).map(([key,permissions])=><button type="button" key={key} onClick={()=>setDraft({...draft,permissions})}>{({support:fa?"پشتیبانی":"Support",designer:fa?"طراح برنامه":"Designer",finance:fa?"مالی":"Finance",observer:fa?"ناظر":"Observer"})[key]}</button>)}</div>
            <fieldset className="staff-permissions"><legend>{fa?"دسترسی‌ها":"Permissions"}</legend>{Object.entries(team?.permissions??{}).map(([key,label])=><label key={key}><input type="checkbox" checked={draft.permissions.includes(key)} onChange={e=>setDraft({...draft,permissions:e.target.checked?[...draft.permissions,key]:draft.permissions.filter(p=>p!==key)})}/><span>{label[fa?0:1]}</span></label>)}</fieldset>
          </>}
          {!resetting&&draft.role!=="staff"&&<p>{fa?"این سطح دسترسی کامل مدیریتی دارد. فقط برای افراد مورداعتماد ایجاد کن.":"This level has full management privileges. Create only for trusted people."}</p>}
          <div className="staff-actions"><button className="button primary" disabled={busy}>{fa?"ذخیره":"Save"}</button><button type="button" className="button secondary" onClick={closeEditor}>{fa?"لغو":"Cancel"}</button></div>
        </form>}
        {!(creating||editing||resetting)&&<div className="staff-members">{team?.items.map(item=>{
          const editable=item.id!==session.staffId&&(session.role==="platform"||item.role==="staff");
          return <article className="staff-member" key={item.id}>
            <div><strong>{item.display_name}</strong><small dir="ltr">@{item.username}</small><span>{roleName(item.role)} · {({active:fa?"فعال":"Active",invited:fa?"نیازمند تعیین رمز":"Password not set",disabled:fa?"غیرفعال":"Disabled"})[item.status]}</span></div>
            {editable&&<div className="staff-actions">
              {item.role==="staff"&&<button onClick={()=>edit(item)}>{fa?"دسترسی‌ها":"Permissions"}</button>}
              <button disabled={busy} onClick={()=>edit(item,true)}>{fa?"تعیین رمز جدید":"Reset password"}</button>
              <button disabled={busy} onClick={()=>{if(confirm(fa?"نشست‌های این حساب بسته می‌شوند. ادامه می‌دهی؟":"This account’s sessions will be revoked. Continue?"))void run("/api/staff/team",{action:item.status==="disabled"?"enable":"disable",id:item.id,version:item.session_version});}}>{item.status==="disabled"?(fa?"فعال‌سازی":"Enable"):(fa?"غیرفعال‌سازی":"Disable")}</button>
              <button disabled={busy} onClick={()=>void run("/api/staff/team",{action:"revoke",id:item.id,version:item.session_version})}>{fa?"بستن نشست‌ها":"Revoke sessions"}</button>
            </div>}
          </article>;
        })}</div>}
        {!(creating||editing||resetting)&&(team?.total??0)>20&&<div className="staff-pager"><button aria-label={fa?"صفحه قبل":"Previous page"} disabled={page<=1} onClick={()=>setPage(page-1)}>{fa?<ArrowRight/>:<ArrowLeft/>}</button><span>{page}</span><button aria-label={fa?"صفحه بعد":"Next page"} disabled={page*20>=(team?.total??0)} onClick={()=>setPage(page+1)}>{fa?<ArrowLeft/>:<ArrowRight/>}</button></div>}
      </>}
      {tab==="audit"&&<section className="staff-audit-section"><header><div><Activity/><div><h3>{fa?"ردپای فعالیت تیم":"Team activity trail"}</h3><p>{fa?"هر تغییر مهم همراه با نام انجام‌دهنده و زمان دقیق ثبت می‌شود؛ رمزها هرگز ذخیره نمی‌شوند.":"Every important change records who did it and when. Passwords are never stored."}</p></div></div><span>{fa?`${audit?.items.length??0} رویداد`:`${audit?.items.length??0} events`}</span></header><ol className="staff-audit">{audit?.items.map(item=><li key={item.id}><i aria-hidden="true"><Activity/></i><div><header><strong>{item.actor_name??(fa?"سیستم":"System")}</strong><span>{item.actor_role?roleName(item.actor_role):fa?"رویداد سیستمی":"System event"}</span></header><p>{actionName(item.action)}</p><small>{targetName(item)}</small></div><time>{new Intl.DateTimeFormat(fa?"fa-IR":"en-GB",{dateStyle:"medium",timeStyle:"short"}).format(new Date(item.created_at))}</time></li>)}</ol>{audit&&!audit.items.length&&<p className="staff-audit-empty">{fa?"هنوز فعالیتی برای نمایش وجود ندارد.":"No activity to show yet."}</p>}<div className="staff-audit-pager"><button onClick={()=>setCursor(null)} disabled={!cursor}>{fa?"جدیدترین‌ها":"Latest"}</button><button disabled={!audit?.next} onClick={()=>setCursor(audit?.next??null)}>{fa?"رویدادهای قدیمی‌تر":"Older events"}</button></div></section>}
    </div>
  </dialog>;
}

type CollaborationData={assignment:{staff_id:number|null;version:number;display_name?:string};notes:Array<{id:number;author_name:string;body:string;created_at:string}>;members:Array<{id:number;display_name:string}>};
export function CollaborationPanel({kind,id,session,lang,version,notesOnly=false}:{kind:"thread"|"order";id:number;session:Session;lang:Lang;version:number;notesOnly?:boolean}) {
  const [data,setData]=useState<CollaborationData>(),[note,setNote]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState(false);
  const path=`/api/collaboration/${kind}/${id}`,fa=lang==="fa";
  const editable=can(session,notesOnly?"customers.read":kind==="thread"?"chats.reply":"orders.review");
  useEffect(()=>{const controller=new AbortController();void api<CollaborationData>(path,session.csrf,{signal:controller.signal}).then(setData).catch(()=>{if(!controller.signal.aborted)setError(true);});return()=>controller.abort();},[path,session.csrf,version]);
  const change=async(body:unknown)=>{if(busy)return;setBusy(true);setError(false);try{setData(await api<CollaborationData>(path,session.csrf,{method:"POST",body:JSON.stringify(body)}));setNote("");}catch{setError(true);}finally{setBusy(false);}};
  return <details className="collaboration-panel"><summary>{notesOnly?(fa?"یادداشت داخلی تیم":"Internal team notes"):(fa?"همکاری تیم":"Team handoff")}<span>{notesOnly?data?.notes.length??0:data?.assignment.display_name??(fa?"بدون مسئول":"Unassigned")}</span></summary><div>{error&&<p role="alert">{fa?"ذخیره نشد؛ ممکن است همکار دیگری مسئولیت را گرفته باشد. صفحه را دوباره باز کن.":"Could not save; another teammate may have claimed this task. Reopen to refresh."}</p>}{editable&&data&&!notesOnly&&<div className="staff-actions">{session.role!=="staff"?<SelectMenu label={fa?"مسئول":"Assignee"} value={String(data.assignment.staff_id??"")} disabled={busy} onChange={value=>void change({action:"assign",staff_id:value?Number(value):null,version:data.assignment.version})} options={[["",fa?"بدون مسئول":"Unassigned"],...data.members.map(member=>[String(member.id),member.display_name] as [string,string])]}/>:<button disabled={busy||Boolean(data.assignment.staff_id&&data.assignment.staff_id!==session.staffId)} onClick={()=>void change({action:"assign",staff_id:data.assignment.staff_id===session.staffId?null:session.staffId,version:data.assignment.version})}>{data.assignment.staff_id===session.staffId?(fa?"آزاد کردن":"Release"):(fa?"من انجام می‌دهم":"Assign to me")}</button>}</div>}
  {editable&&<form onSubmit={e=>{e.preventDefault();void change({action:"note",text:note});}}><label>{fa?"یادداشت داخلی · برای شاگرد ارسال نمی‌شود":"Internal note · never sent to the client"}<textarea value={note} maxLength={2000} onChange={e=>setNote(e.target.value)}/></label><button disabled={busy||!note.trim()}>{fa?"ثبت یادداشت":"Add note"}</button></form>}{data?.notes.map(item=><article key={item.id}><strong>{item.author_name}</strong><p>{item.body}</p></article>)}</div></details>;
}
