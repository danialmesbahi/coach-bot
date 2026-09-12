"use client";
import { chatViewport } from "@/lib/chat-viewport";
/* eslint-disable @next/next/no-img-element -- Telegram avatars are authenticated same-origin streams. */

import {
  Activity, ArrowLeft, ArrowRight, BarChart3, CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight,
  CircleDollarSign, ClipboardList, CreditCard, Download, Dumbbell, FileDown, FileText, HeartPulse, Images, LayoutDashboard, LoaderCircle,
  LockKeyhole, LogOut, Menu, MessageCircle, Moon, PackageCheck, Paperclip, Phone, Ruler, Scale, Search, Send,
  RotateCcw, Sun, Target, UnlockKeyhole, Upload, UserRound, UsersRound, X, ZoomIn, ZoomOut,
} from "lucide-react";
import { FormEvent, Fragment, KeyboardEvent, ReactNode, TouchEvent as ReactTouchEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { can, StaffPanel, CollaborationPanel } from "./staff-panel";
import { CopyKey, translator } from "@/lib/i18n";
import type {
  CustomerDetailData, CustomerPage, DashboardData, Lang, MessageItem, OrderDetail, OrderPage,
  ProductOption, RealtimeUpdate, SalesData, SalesPeriod, Session, ThreadDetailData, ThreadListItem, ThreadPage, View,
} from "@/lib/types";

type PageData = DashboardData | CustomerPage | OrderPage | ThreadPage | SalesData;
type DrawerState = { type: "order" | "thread" | "customer"; id: number; source?: "sales" } | null;
type Connection = "online" | "connecting" | "offline";
type PreviewMedia = { source: string; kind: "image" | "video" | "audio" | "pdf" | "file"; name?: string };

const avatarSources = new Map<number, string>();
const avatarLoads = new Map<number, Promise<string>>();
const avatarJobs: Array<() => Promise<void>> = [];
let activeAvatarJobs = 0;
function runAvatarJobs() {
  while (activeAvatarJobs < 3 && avatarJobs.length) {
    activeAvatarJobs += 1;
    avatarJobs.shift()?.().finally(() => { activeAvatarJobs -= 1; runAvatarJobs(); });
  }
}
function cachedAvatar(userId: number) {
  const source = avatarSources.get(userId) ?? "";
  if (source) { avatarSources.delete(userId); avatarSources.set(userId, source); }
  return source;
}
function loadAvatar(userId: number) {
  const cached = cachedAvatar(userId);
  if (cached) return Promise.resolve(cached);
  const pending = avatarLoads.get(userId);
  if (pending) return pending;
  const load = new Promise<string>((resolve, reject) => {
    avatarJobs.push(async () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 5_000);
      try {
        const response = await fetch(`/media/customers/${userId}/avatar`, { credentials:"same-origin", cache:"force-cache", signal:controller.signal });
        if (!response.ok) throw new Error("avatar_unavailable");
        const source = URL.createObjectURL(await response.blob());
        if (avatarSources.size >= 160) { const oldest = avatarSources.entries().next().value as [number, string] | undefined; if (oldest) { avatarSources.delete(oldest[0]); URL.revokeObjectURL(oldest[1]); } }
        avatarSources.set(userId, source); resolve(source);
      } catch (error) { reject(error); }
      finally { window.clearTimeout(timeout); }
    });
    runAvatarJobs();
  }).finally(() => avatarLoads.delete(userId));
  avatarLoads.set(userId, load);
  return load;
}

const periods: SalesPeriod[] = ["day", "week", "month", "all"];
const realtimeTables: Record<View, string[]> = {
  dashboard: ["users", "orders", "support_messages", "sales_gate"],
  orders: ["orders", "users", "products", "staff_assignments", "staff_notes"],
  messages: ["support_messages", "users", "staff_assignments", "staff_notes"],
  customers: ["users", "orders"],
  sales: ["orders", "users", "products"],
};
const statusFa: Record<string, string> = { awaiting_payment:"منتظر پرداخت", awaiting_receipt:"بررسی کارت‌به‌کارت", payment_rejected:"رد رسید", paid:"بررسی اطلاعات", needs_info:"منتظر پاسخ شاگرد", in_progress:"در حال طراحی", ready:"آماده", delivered:"تحویل‌شده", cancelled:"لغوشده" };
const statusEn: Record<string, string> = { awaiting_payment:"Awaiting payment", awaiting_receipt:"Bank transfer review", payment_rejected:"Receipt rejected", paid:"Review information", needs_info:"Awaiting client reply", in_progress:"In design", ready:"Ready", delivered:"Delivered", cancelled:"Cancelled" };

function money(value: number | string | undefined, lang: Lang) {
  return `${new Intl.NumberFormat(lang === "fa" ? "fa-IR" : "en-US").format(Number(value ?? 0))} ${lang === "fa" ? "تومان" : "Toman"}`;
}
function compactMoney(value: number | string | undefined, lang: Lang) {
  return new Intl.NumberFormat(lang === "fa" ? "fa-IR" : "en-US", { notation:"compact", maximumFractionDigits:1 }).format(Number(value ?? 0));
}
function formatDate(value: string | undefined, lang: Lang, compact = false) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(lang === "fa" ? "fa-IR-u-ca-persian" : "en-US", compact ? { month:"short", day:"numeric" } : { dateStyle:"medium", timeStyle:"short" }).format(new Date(value));
}
function conversationTime(value: string | undefined, lang: Lang) {
  if (!value) return "";
  const date = new Date(value);
  const now = new Date();
  if (date.toDateString() === now.toDateString()) return new Intl.DateTimeFormat(lang === "fa" ? "fa-IR" : "en-US", { hour:"2-digit", minute:"2-digit" }).format(date);
  return new Intl.DateTimeFormat(lang === "fa" ? "fa-IR-u-ca-persian" : "en-US", { month:"short", day:"numeric" }).format(date);
}
function messageTime(value: string | undefined, lang: Lang) {
  if (!value) return "";
  return new Intl.DateTimeFormat(lang === "fa" ? "fa-IR" : "en-US", { hour:"2-digit", minute:"2-digit" }).format(new Date(value));
}
function conversationDay(value: string | undefined, lang: Lang) {
  if (!value) return "";
  const date = new Date(value), today = new Date(), yesterday = new Date(); yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return lang === "fa" ? "امروز" : "Today";
  if (date.toDateString() === yesterday.toDateString()) return lang === "fa" ? "دیروز" : "Yesterday";
  return new Intl.DateTimeFormat(lang === "fa" ? "fa-IR-u-ca-persian" : "en-US", { month:"long", day:"numeric", year:date.getFullYear() === today.getFullYear() ? undefined : "numeric" }).format(date);
}
function dayKey(value: string | undefined) {
  const date = value ? new Date(value) : new Date(0);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}
function mediaLabel(type: string | undefined, lang: Lang) {
  const labels: Record<string, [string,string]> = { photo:["عکس","Photo"], video:["ویدیو","Video"], animation:["تصویر متحرک","Animation"], voice:["پیام صوتی","Voice message"], audio:["فایل صوتی","Audio"], document:["فایل","File"], sticker:["استیکر","Sticker"] };
  return labels[type ?? ""]?.[lang === "fa" ? 0 : 1] ?? (lang === "fa" ? "پیام" : "Message");
}
function displayName(user: { name?: string; first_name?: string; last_name?: string } | undefined, lang: Lang) {
  return user?.name || [user?.first_name, user?.last_name].filter(Boolean).join(" ") || (lang === "fa" ? "بدون نام" : "Unnamed");
}
function initial(name: string) { return Array.from(name.trim())[0] ?? "?"; }
function orderCode(id: number) { return `ORD-${String(id).padStart(6, "0")}`; }
function statusText(value: string, lang: Lang) { return (lang === "fa" ? statusFa : statusEn)[value] ?? value ?? "—"; }

function useCustomerAvatar(userId: number) {
  const [source, setSource] = useState(() => cachedAvatar(userId));
  useEffect(() => { let mounted = true; if (!source) loadAvatar(userId).then((next) => { if (mounted) setSource(next); }).catch(() => undefined); return () => { mounted = false; }; }, [source, userId]);
  return source;
}

function CustomerPhoto({ userId, name }: { userId: number; name: string }) {
  const source = useCustomerAvatar(userId);
  return <div className="customer-photo"><span className="customer-initial">{initial(name)}</span><small className="customer-code">U{String(userId).padStart(6,"0")}</small>{source && <img src={source} alt="" loading="lazy" decoding="async"/>}</div>;
}

function useLocalState<T extends string>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(fallback);
  // The persisted preference is browser-only and intentionally applied after hydration.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { const stored = localStorage.getItem(key) as T | null; if (stored) setValue(stored); }, [key]);
  const update = useCallback((next: T) => { setValue(next); localStorage.setItem(key, next); }, [key]);
  return [value, update] as const;
}

function Glass({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`glass ${className}`}>{children}</section>;
}

function Status({ value, lang }: { value: string; lang: Lang }) {
  return <span className={`status status-${value}`}><i />{statusText(value, lang)}</span>;
}

function Empty({ text }: { text: string }) {
  return <div className="empty-state"><PackageCheck aria-hidden="true" /><p>{text}</p></div>;
}

function Skeleton() {
  return <div className="skeleton-grid" aria-label="Loading"><i /><i /><i /><i /></div>;
}

function Pager({ page, total, size, t, onChange }: { page: number; total: number; size: number; t: (key: CopyKey) => string; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return <nav className="pager" aria-label={t("page")}>
    <button className="button secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}><ChevronRight aria-hidden="true" />{t("previous")}</button>
    <span>{t("page")} <strong>{page}</strong> / {pages}</span>
    <button className="button secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>{t("next")}<ChevronLeft aria-hidden="true" /></button>
  </nav>;
}

function SelectMenu({ label, value, options, onChange, compact = false, compactDefault }: { label: string; value: string; options: Array<[string, string]>; onChange: (value: string) => void; compact?: boolean; compactDefault?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const selected = options.find(([key]) => key === value)?.[1] ?? options[0]?.[1];
  const focusOption = (offset: number) => {
    const items = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') ?? []);
    if (!items.length) return;
    const current = Math.max(0, items.indexOf(document.activeElement as HTMLButtonElement));
    items[(current + offset + items.length) % items.length]?.focus();
  };
  const openAndFocus = () => { setOpen(true); requestAnimationFrame(() => (list.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]') ?? list.current?.querySelector<HTMLButtonElement>('[role="option"]'))?.focus()); };
  useEffect(() => {
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close);
  }, []);
  return <div className={`select-menu ${compact ? "compact" : ""} ${open ? "open" : ""}`} ref={root}>
    <span className="select-label">{label}</span>
    <button ref={trigger} type="button" className="select-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={() => open ? setOpen(false) : openAndFocus()} onKeyDown={(event) => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); openAndFocus(); } }}>
      <span>{compact && value === options[0]?.[0] ? compactDefault ?? selected : selected}</span><ChevronDown aria-hidden="true" />
    </button>
    {open && <div ref={list} className="select-options" role="listbox" tabIndex={-1} onKeyDown={(event) => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } else if (event.key === "ArrowDown") { event.preventDefault(); focusOption(1); } else if (event.key === "ArrowUp") { event.preventDefault(); focusOption(-1); } }}>
      {options.map(([key, text]) => <button type="button" role="option" aria-selected={key === value} key={key} onClick={() => { onChange(key); setOpen(false); trigger.current?.focus(); }}>
        <span>{text}</span>{key === value && <Check aria-hidden="true" />}
      </button>)}
    </div>}
  </div>;
}

function TrendChart({ data, lang }: { data: DashboardData["sales"]; lang: Lang }) {
  const values = data.trend.map((item) => {
    const value = Number(item.revenue);
    return Number.isFinite(value) && value >= 0 ? value : 0;
  });
  const max = Math.max(1, ...values);
  const width = 1000, height = 230, padX = 24, padY = 28;
  const points = values.map((value, index) => {
    const x = values.length <= 1 ? width / 2 : padX + index * ((width - padX * 2) / (values.length - 1));
    const y = height - padY - (value / max) * (height - padY * 2);
    return [x, y] as const;
  });
  const line = points.map(([x, y]) => `${x},${y}`).join(" ");
  const area = points.length ? `${padX},${height - padY} ${line} ${width - padX},${height - padY}` : "";
  const tickCount = Math.min(data.period === "day" ? 6 : data.period === "all" ? 4 : 5, data.trend.length);
  const ticks = Array.from({ length: tickCount }, (_, index) => Math.round(index * (data.trend.length - 1) / Math.max(1, tickCount - 1)));
  return <div className="trend-chart">
    <div className="chart-scale"><span>{lang === "fa" ? "بیشینهٔ بازه" : "Period peak"}: {money(values.some(Boolean) ? max : 0, lang)}</span><span>{lang === "fa" ? "مبنای نمودار: صفر" : "Baseline: zero"}</span></div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={lang === "fa" ? "روند فروش" : "Sales trend"} preserveAspectRatio="xMidYMid meet">
      <defs><linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--accent)" stopOpacity=".45"/><stop offset="1" stopColor="var(--accent)" stopOpacity="0"/></linearGradient></defs>
      <g className="chart-grid"><line x1="0" y1={padY} x2={width} y2={padY}/><line x1="0" y1={height / 2} x2={width} y2={height / 2}/><line x1="0" y1={height - padY} x2={width} y2={height - padY}/></g>
      {area && <polygon points={area} fill="url(#trendFill)" />}
      {line && <polyline points={line} fill="none" vectorEffect="non-scaling-stroke" />}
      {points.map(([x, y], index) => <circle key={index} cx={x} cy={y} r="6"><title>{money(values[index], lang)}</title></circle>)}
    </svg>
    <div className="chart-axis">{ticks.map((index) => <span key={index}><b>{compactMoney(values[index], lang)}</b><small>{formatDate(data.trend[index]?.bucket, lang, true)}</small></span>)}</div>
  </div>;
}

function Login({ lang }: { lang: Lang }) {
  const t = translator(lang);
  const [request, setRequest] = useState<{url:string;code:string;expiresAt:number} | null>(null);
  const [busy, setBusy] = useState(false);
  const [credentials,setCredentials] = useState(()=>({username:"",password:"",invite:typeof window==="undefined"?"":new URLSearchParams(location.hash.slice(1)).get("invite")??""}));
  const [passwordMode,setPasswordMode] = useState(Boolean(credentials.invite));
  useEffect(() => {
    const token = new URLSearchParams(location.hash.slice(1)).get("invite");
    if(token) history.replaceState(null,"",location.pathname);
  }, []);
  const [message, setMessage] = useState<"error" | "expired" | "denied" | null>(null);
  const begin = async () => {
    setBusy(true); setMessage(null);
    try {
      const result = await api<{url:string;code:string;expiresIn:number}>("/api/auth/bot/start", "", {method:"POST",headers:{"X-Login-Request":"1"},body:passwordMode?JSON.stringify(credentials):undefined});
      setCredentials(old=>({...old,password:""}));
      setRequest({...result,expiresAt:Date.now()+result.expiresIn*1000});
    } catch(error) { setMessage(error instanceof ApiError && [401,403].includes(error.status) ? "denied" : "error"); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    if (!request) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let running = false;
    const poll = async () => {
      if (running || controller.signal.aborted) return;
      clearTimeout(timer);
      if (Date.now() >= request.expiresAt) { setRequest(null); setMessage("expired"); return; }
      if (document.hidden) { timer = setTimeout(poll,3000); return; }
      running = true;
      let again = true;
      try {
        const result = await api<{status:"pending" | "approved" | "expired" | "denied"}>("/api/auth/bot/poll", "", {method:"POST",headers:{"X-Login-Request":"1"},signal:controller.signal});
        if (controller.signal.aborted) return;
        if (result.status === "approved") { again=false; location.reload(); }
        else if (result.status !== "pending") { again=false; setRequest(null); setMessage(result.status); }
      } catch {
        if (!controller.signal.aborted) { again=false; setRequest(null); setMessage("error"); }
      } finally {
        running=false;
        if (again && !controller.signal.aborted) timer=setTimeout(poll,3000);
      }
    };
    void poll();
    document.addEventListener("visibilitychange",poll);
    return () => { controller.abort(); clearTimeout(timer); document.removeEventListener("visibilitychange",poll); };
  }, [request]);
  return <main className="login-shell">
    <div className="login-orb" aria-hidden="true" />
    <Glass className="login-card">
      <div className="brand-mark"><span>S</span></div>
      <p className="eyebrow">SENSI CONSOLE</p><h1>{t("loginTitle")}</h1><p>{t("loginText")}</p>
      {!request && <><div className="staff-tabs"><button aria-pressed={!passwordMode} onClick={()=>setPasswordMode(false)}>{lang==="fa"?"ورود تلگرام":"Telegram"}</button><button aria-pressed={passwordMode} onClick={()=>setPasswordMode(true)}>{lang==="fa"?"حساب همکار":"Staff account"}</button></div>{passwordMode&&<form id="staff-login" className="staff-form" onSubmit={event=>{event.preventDefault();void begin();}}><label>{lang==="fa"?"نام کاربری":"Username"}<input autoComplete="username" required dir="ltr" maxLength={40} value={credentials.username} onChange={event=>setCredentials({...credentials,username:event.target.value})}/></label><label>{credentials.invite?(lang==="fa"?"انتخاب رمز جدید (۱۲ تا ۱۲۸ نویسه)":"Choose password (12–128 characters)"):(lang==="fa"?"رمز عبور":"Password")}<input type="password" required minLength={12} maxLength={128} autoComplete={credentials.invite?"new-password":"current-password"} value={credentials.password} onChange={event=>setCredentials({...credentials,password:event.target.value})}/></label></form>}</>}
      {request ? <>
        <p>{lang === "fa" ? "این کد را با پیام ربات تطبیق بده و ورود را تأیید کن؛ سپس به همین صفحه برگرد." : "Match this code in the bot, approve your login, then return to this page."}</p>
        <strong dir="ltr" style={{fontSize:28,letterSpacing:6}}>{request.code}</strong>
        <a className="button primary wide" href={request.url} target="_blank" rel="noopener noreferrer"><Send/>{lang === "fa" ? "باز کردن تلگرام و تأیید ورود" : "Open Telegram & approve"}</a>
        <span role="status">{lang === "fa" ? "منتظر تأیید تو در تلگرام…" : "Waiting for your approval in Telegram…"}</span>
      </> : <button className="button primary wide" disabled={busy} form={passwordMode?"staff-login":undefined} type={passwordMode?"submit":"button"} onClick={passwordMode?undefined:begin}>
        {busy ? <LoaderCircle className="spin"/> : <Send/>}
        {busy ? (lang === "fa" ? "در حال آماده‌سازی…" : "Preparing…") : (lang === "fa" ? "ادامه و تأیید تلگرام" : "Continue & verify Telegram")}
      </button>}
      {message && <p role="alert">{message === "expired" ? (lang === "fa" ? "درخواست منقضی شد؛ دوباره ورود را بزن." : "Request expired. Start again.") : message === "denied" ? (lang === "fa" ? "ورود رد شد یا این حساب دسترسی مدیریت ندارد." : "Login denied or this account has no management access.") : (lang === "fa" ? "اتصال برقرار نشد؛ دوباره تلاش کن. اگر ادامه داشت، سرویس‌های ربات و پنل باید به‌روز شوند." : "Could not connect. Try again; if this continues, update the bot and panel services.")}</p>}
      <small><LockKeyhole aria-hidden="true" />{t("secureLogin")}</small>
    </Glass>
  </main>;
}

function MediaViewer({ media, lang, onClose }: { media: PreviewMedia; lang: Lang; onClose: () => void }) {
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [pinching, setPinching] = useState(false);
  const [panning, setPanning] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const pinch = useRef<{ distance: number; zoom: number } | null>(null);
  const pan = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null);
  useEffect(() => { const close = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") onClose(); }; addEventListener("keydown", close); return () => removeEventListener("keydown", close); }, [onClose]);
  const changeZoom = (next: number) => {
    setZoom(next);
    if (next <= 1) setPosition({ x: 0, y: 0 });
  };
  const download = `${media.source}${media.source.includes("?") ? "&" : "?"}download=1`;
  const label = media.name || (lang === "fa" ? "پیوست پیام" : "Message attachment");
  const touchDistance = (event: ReactTouchEvent) => Math.hypot(event.touches[0].clientX - event.touches[1].clientX, event.touches[0].clientY - event.touches[1].clientY);
  const startGesture = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (media.kind !== "image") return;
    if (event.touches.length === 2) {
      pan.current = null;
      pinch.current = { distance: touchDistance(event), zoom };
      setPanning(false);
      setPinching(true);
    } else if (event.touches.length === 1 && zoom > 1) {
      const touch = event.touches[0];
      pan.current = { x: touch.clientX, y: touch.clientY, originX: position.x, originY: position.y };
      setPanning(true);
    }
  };
  const moveGesture = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2 && pinch.current) {
      event.preventDefault();
      changeZoom(Math.min(4, Math.max(.5, pinch.current.zoom * touchDistance(event) / Math.max(1, pinch.current.distance))));
    } else if (event.touches.length === 1 && pan.current) {
      event.preventDefault();
      const touch = event.touches[0];
      setPosition({ x: pan.current.originX + touch.clientX - pan.current.x, y: pan.current.originY + touch.clientY - pan.current.y });
    }
  };
  const endGesture = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length < 2) { pinch.current = null; setPinching(false); }
    if (event.touches.length === 0) { pan.current = null; setPanning(false); }
  };
  return <div className="media-viewer" role="dialog" aria-modal="true" aria-label={label} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <header><strong title={label}>{label}</strong><div>{media.kind === "image" && <><button onClick={() => changeZoom(Math.max(.5, zoom - .25))} aria-label={lang === "fa" ? "کوچک‌نمایی" : "Zoom out"}><ZoomOut/></button><button onClick={() => changeZoom(Math.min(4, zoom + .25))} aria-label={lang === "fa" ? "بزرگ‌نمایی" : "Zoom in"}><ZoomIn/></button><button onClick={() => setRotation((value) => value + 90)} aria-label={lang === "fa" ? "چرخاندن" : "Rotate"}><RotateCcw/></button></>}<a href={download} download aria-label={lang === "fa" ? "دانلود" : "Download"}><Download/></a><button onClick={onClose} aria-label={lang === "fa" ? "بستن" : "Close"}><X/></button></div></header>
    <div className={`media-viewer__stage${media.kind === "image" ? " media-viewer__stage--image" : ""}`} onTouchStart={startGesture} onTouchMove={moveGesture} onTouchEnd={endGesture} onTouchCancel={endGesture}>{media.kind === "image" ? <img className={pinching || panning ? "is-gesturing" : undefined} src={media.source} alt={label} style={{ transform:`translate3d(${position.x}px,${position.y}px,0) scale(${zoom}) rotate(${rotation}deg)` }}/> : media.kind === "video" ? <video src={media.source} controls autoPlay playsInline/> : media.kind === "audio" ? <audio src={media.source} controls autoPlay/> : media.kind === "pdf" ? <iframe src={media.source} title={label}/> : <div className="media-viewer__file"><FileText/><strong>{label}</strong><a className="button primary" href={download} download><Download/>{lang === "fa" ? "دانلود امن فایل" : "Download file"}</a></div>}</div>
  </div>;
}

function Drawer({ state, session, lang, t, realtimeVersion, onClose, onChanged, onNavigate }: { state: Exclude<DrawerState, null>; session: Session; lang: Lang; t: (key: CopyKey) => string; realtimeVersion: number; onClose: () => void; onChanged: () => void; onNavigate: (state:DrawerState) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const customerScroll = useRef(0);
  const [data, setData] = useState<OrderDetail | ThreadDetailData | CustomerDetailData>();
  const [selectedCustomerOrder, setSelectedCustomerOrder] = useState<OrderDetail>();
  const [preview, setPreview] = useState<PreviewMedia>();
  const [error, setError] = useState(false);
  useLayoutEffect(() => {
    if (state.type !== "customer") return;
    ref.current?.querySelector<HTMLElement>(".drawer-inner")?.scrollTo({ top:selectedCustomerOrder ? 0 : customerScroll.current, behavior:"instant" });
  }, [selectedCustomerOrder, state.type]);
  const load = useCallback(async () => {
    void realtimeVersion;
    const path = state.type === "order" ? `/api/orders/${state.id}` : state.type === "thread" ? `/api/threads/${state.id}` : `/api/customers/${state.id}`;
    try { setError(false); setData(await api(path, session.csrf)); } catch { setError(true); }
  }, [realtimeVersion, session.csrf, state]);
  // Fetching is tied to the modal lifecycle; updates happen after the request resolves.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { if (!ref.current?.open) ref.current?.showModal(); load(); }, [load]);
  useLayoutEffect(() => {
    const body = document.body, root = document.documentElement, y = scrollY;
    const previous = { position:body.style.position, top:body.style.top, width:body.style.width, overflow:body.style.overflow, height:body.style.height, minHeight:body.style.minHeight };
    const previousRoot = { overflow:root.style.overflow, height:root.style.height, scrollBehavior:root.style.scrollBehavior };
    root.style.scrollBehavior = "auto";
    body.style.position = "fixed";
    body.style.top = state.type === "thread" ? "0px" : `-${y}px`;
    body.style.width = "100%";
    body.style.overflow = "hidden";
    if (state.type === "thread") {
      root.style.height = body.style.height = "100%";
      root.style.overflow = "hidden";
      body.style.minHeight = "0";
      scrollTo(0, 0);
    }
    return () => {
      Object.assign(body.style, previous);
      Object.assign(root.style, previousRoot, { scrollBehavior:"auto" });
      scrollTo(0, y);
      root.style.scrollBehavior = previousRoot.scrollBehavior;
    };
  }, [state.type]);
  const action = async (path: string, init: RequestInit) => { const result = await api<{notification_sent?:boolean}>(path, session.csrf, init); await load(); onChanged(); if (result.notification_sent === false) throw new Error("notification_failed"); };
  const isProfile = state.type === "customer";
  const isChat = state.type === "thread";
  const isWork = state.type === "order";
  const chatData = data && isChat ? data as ThreadDetailData : undefined;
  const backToCustomer = () => setSelectedCustomerOrder(undefined);
  return <dialog className={`drawer${isProfile ? " profile-dialog" : isChat ? " chat-dialog" : isWork ? ` order-dialog${state.source === "sales" ? " sales-order-dialog" : ""}` : ""}`} ref={ref} onClose={onClose} onClick={(event) => { if (event.target === ref.current) ref.current.close(); }}>
    <div className="drawer-inner">
      <header>{isProfile || isChat || isWork ? <><button className="icon-button drawer-desktop-close" onClick={() => ref.current?.close()} aria-label={t("close")}><X /></button><button className="drawer-mobile-back" onClick={() => selectedCustomerOrder ? backToCustomer() : ref.current?.close()} aria-label={lang === "fa" ? "بازگشت" : "Back"}>{lang === "fa" ? <ArrowRight/> : <ArrowLeft/>}<span>{lang === "fa" ? "بازگشت" : "Back"}</span></button></> : <button className="icon-button drawer-desktop-close" onClick={() => ref.current?.close()} aria-label={t("close")}><X /></button>}{chatData ? <div className="chat-dialog-person"><ConversationAvatar userId={chatData.user.id} name={displayName(chatData.user, lang)}/><div><h2>{displayName(chatData.user, lang)}</h2><span dir="ltr">{chatData.user.username ? `@${chatData.user.username}` : `U${String(chatData.user.id).padStart(6,"0")}`}</span></div></div> : <h2>{selectedCustomerOrder ? orderCode(selectedCustomerOrder.id) : state.type === "order" ? orderCode(state.id) : state.type === "thread" ? t("conversation") : t("profile")}</h2>}</header>
      {!data && !error && <Skeleton />}{error && <Empty text={t("error")} />}
      {data && state.type === "order" && <OrderDrawer realtimeVersion={realtimeVersion} data={data as OrderDetail} session={session} lang={lang} t={t} action={action} onPreview={setPreview} onConversation={() => onNavigate({type:"thread",id:(data as OrderDetail).customer_id ?? (data as OrderDetail).user_id!})} />}
      {data && state.type === "thread" && <ThreadDrawer realtimeVersion={realtimeVersion} session={session} data={data as ThreadDetailData} id={state.id} lang={lang} t={t} action={action} previewOpen={Boolean(preview)} onPreview={setPreview} />}
      {data && state.type === "customer" && (selectedCustomerOrder ? <><button className="profile-back" onClick={backToCustomer}>{lang === "fa" ? <ArrowRight/> : <ArrowLeft/>}{lang === "fa" ? "بازگشت به پروفایل" : "Back to profile"}</button><OrderDrawer key={selectedCustomerOrder.id} data={{...selectedCustomerOrder, customer_id:(data as CustomerDetailData).user.id, name:(data as CustomerDetailData).user.name, first_name:(data as CustomerDetailData).user.first_name, username:(data as CustomerDetailData).user.username}} session={session} lang={lang} t={t} action={action} onPreview={setPreview} onConversation={() => onNavigate({type:"thread",id:(data as CustomerDetailData).user.id})} readOnly/></> : <CustomerDrawer data={data as CustomerDetailData} lang={lang} t={t} onSelectOrder={(order, position) => { customerScroll.current=position; setSelectedCustomerOrder(order); }} onPreview={setPreview} />)}
    </div>
    {preview && <MediaViewer media={preview} lang={lang} onClose={() => setPreview(undefined)}/>}
  </dialog>;
}

function OrderDrawer({ data: o, session, lang, realtimeVersion=0, t, action, onPreview, onConversation, readOnly = false }: { data: OrderDetail; session: Session; lang: Lang; realtimeVersion?: number; t: (key: CopyKey) => string; action: (path: string, init: RequestInit) => Promise<void>; onPreview: (media: PreviewMedia) => void; onConversation: () => void; readOnly?: boolean }) {
  const f = o.form_snapshot ?? {};
  const [info, setInfo] = useState(""); const [fileName, setFileName] = useState(""); const [busy, setBusy] = useState(false); const [feedback, setFeedback] = useState<"success" | "error" | "notification">(); const [requestOpen,setRequestOpen] = useState(false);
  const copy = lang === "fa" ? { workspace:"فضای انجام کار", next:"اقدام بعدی", details:"اطلاعات موردنیاز طراحی", photos:"عکس‌های این سفارش", receipt:"رسید پرداخت", openReceipt:"نمایش رسید کامل", approved:"تغییر با موفقیت ثبت شد", failed:"عملیات انجام نشد؛ دوباره تلاش کنید.", request:"اطلاعات تکمیلی", delivery:"تحویل برنامه", resume:"ادامه طراحی و آماده‌سازی فایل" } : { workspace:"Work workspace", next:"Next action", details:"Design brief", photos:"Order photos", receipt:"Payment receipt", openReceipt:"Open full receipt", approved:"Change saved successfully", failed:"The action failed. Please try again.", request:"Additional information", delivery:"Plan delivery", resume:"Continue design and prepare the file" };
  const manualReceipt = o.status === "awaiting_receipt" && o.payment_method === "card_to_card";
  const isPaid = o.payment_status === "paid" || Boolean(o.paid_at);
  const steps = lang === "fa" ? ["پرداخت", "بررسی اطلاعات", "طراحی", "تحویل"] : ["Payment", "Review", "Design", "Delivery"];
  const step = o.status === "delivered" ? 3 : ["in_progress","ready"].includes(o.status) ? 2 : isPaid ? 1 : 0;
  const next = manualReceipt ? (lang === "fa" ? "رسید کارت‌به‌کارت را بررسی کنید" : "Review the bank transfer receipt") : o.status === "paid" ? (lang === "fa" ? "اطلاعات و عکس‌ها را بررسی کنید" : "Review the brief and photos") : o.status === "needs_info" ? (lang === "fa" ? "پاسخ شاگرد را بررسی کنید" : "Check the client’s reply") : o.status === "in_progress" ? copy.resume : (lang === "fa" ? statusFa[o.status] : statusEn[o.status]);
  const submit = async (task: () => Promise<void>) => { if (busy) return; setBusy(true); setFeedback(undefined); try { await task(); setFeedback("success"); setRequestOpen(false); setInfo(""); } catch (error) { setFeedback(error instanceof Error && error.message === "notification_failed" ? "notification" : "error"); } finally { setBusy(false); } };
  const userId = o.customer_id ?? o.user_id;
  return <div className="order-workspace order-workspace-v2">{can(session,"orders.read")&&<CollaborationPanel kind="order" id={o.id} session={session} lang={lang} version={realtimeVersion}/>}
    <ol className="order-steps" aria-label={lang === "fa" ? "مسیر انجام دوره" : "Order progress"}>{steps.map((label,index) => <li key={label} className={index < step ? "done" : index === step ? "current" : ""} aria-current={index === step ? "step" : undefined}><b>{index < step ? <Check/> : index+1}</b><span>{label}</span></li>)}</ol>
    <section className={`order-work-hero status-${o.status}`}><div><span>{copy.workspace}</span><bdi>{orderCode(o.id)}</bdi><h3>{o.product_title}</h3><p>{copy.next} · <strong>{next}</strong></p></div><Status value={o.status} lang={lang}/></section>
    <section className="order-client-strip">{userId ? <ConversationAvatar userId={userId} name={displayName(o,lang)}/> : <span className="conversation-avatar" aria-hidden="true">{initial(displayName(o,lang))}</span>}<div><small>{t("customer")}</small><strong>{displayName(o,lang)}</strong><span dir="ltr">{o.username ? `@${o.username}` : o.telegram_id ? `ID ${o.telegram_id}` : o.phone ?? "—"}</span></div><dl><div><dt>{t("amount")}</dt><dd>{money(o.amount,lang)}</dd></div><div><dt>{t("created")}</dt><dd>{formatDate(o.created_at,lang,true)}</dd></div></dl></section>
    {isPaid && <div className="order-payment-note"><Check/><span>{o.payment_method === "zarinpal" ? (lang === "fa" ? "پرداخت توسط زرین‌پال تأیید شده؛ تأیید دستی لازم نیست." : "Payment verified by ZarinPal. No manual approval needed.") : (lang === "fa" ? "پرداخت این سفارش تأیید شده است." : "Payment confirmed.")}{o.gateway_ref && <small>{lang === "fa" ? "کد پیگیری: " : "Reference: "}<bdi>{o.gateway_ref}</bdi></small>}</span></div>}
    {o.status === "needs_info" && <section className="order-waiting"><MessageCircle/><div><strong>{lang === "fa" ? "منتظر اطلاعات تکمیلی" : "Waiting for information"}</strong><p>{o.info_request || (lang === "fa" ? "پاسخ شاگرد را در گفت‌وگو بررسی کنید و پس از کامل شدن اطلاعات، طراحی را شروع کنید." : "Read the client’s reply, then start design once the brief is complete.")}</p>{userId && <button className="button secondary" disabled={!can(session,"chats.read")} onClick={onConversation}><MessageCircle/>{lang === "fa" ? "دیدن گفت‌وگو و پاسخ‌ها" : "Open conversation"}</button>}</div></section>}
    {can(session,"payments.review") && manualReceipt && o.receipt_file_id && <section className="order-receipt"><header><CreditCard/><div><h3>{lang === "fa" ? "رسید کارت‌به‌کارت" : "Bank transfer receipt"}</h3><span>{orderCode(o.id)}</span></div></header>{o.receipt_type === "photo" ? <button onClick={() => onPreview({ source:`/media/orders/${o.id}/receipt`, kind:"image", name:copy.receipt })}><img src={`/media/orders/${o.id}/receipt`} alt={copy.receipt} decoding="async"/><span>{copy.openReceipt}<FileDown/></span></button> : <button className="message-file" onClick={() => onPreview({ source:`/media/orders/${o.id}/receipt`, kind:"file", name:copy.receipt })}><FileDown/><span>{copy.openReceipt}</span></button>}</section>}
    <section className="profile-section order-brief"><header><div><UserRound/><h3>{copy.details}</h3></div></header><div className="profile-facts"><ProfileFact icon={<CalendarDays/>} label={t("age")} value={String(f.age ?? "—")}/><ProfileFact icon={<UserRound/>} label={t("gender")} value={String(f.gender ?? "—")}/><ProfileFact icon={<Ruler/>} label={t("height")} value={f.height_cm ? `${f.height_cm} cm` : "—"}/><ProfileFact icon={<Scale/>} label={t("weight")} value={f.weight_kg ? `${f.weight_kg} kg` : "—"}/><ProfileFact icon={<Target/>} label={t("goal")} value={String(f.goal ?? "—")} wide/><ProfileFact icon={<Dumbbell/>} label={t("history")} value={String(f.training_history ?? "—")} wide/>{f.notes ? <ProfileFact icon={<Activity/>} label={t("notes")} value={String(f.notes)} wide/> : null}</div></section>
    <section className="profile-section"><header><div><HeartPulse/><h3>{lang === "fa" ? "تغذیه و محدودیت‌ها" : "Nutrition & restrictions"}</h3></div></header><div className="profile-facts">{[["allergy",lang === "fa" ? "حساسیت‌ها" : "Allergies"],["restriction",lang === "fa" ? "محدودیت‌ها" : "Restrictions"],["supplements",lang === "fa" ? "مکمل‌ها" : "Supplements"]].map(([key,label]) => <ProfileFact key={key} icon={<HeartPulse/>} label={label} value={String(f[key] || (lang === "fa" ? "ثبت نشده" : "Not provided"))} wide/>)}</div></section>
    <section className="profile-section"><header><div><Images/><h3>{copy.photos}</h3></div><span>{o.photo_count ?? 0}</span></header>{(o.photo_count ?? 0) > 0 ? <PhotoGallery count={o.photo_count!} source={(index) => `/media/orders/${o.id}/photos/${index}`} lang={lang} onPreview={onPreview}/> : <p className="order-photo-empty">{lang === "fa" ? "عکسی برای این سفارش ثبت نشده است." : "No photos attached to this order."}</p>}</section>
    {!readOnly && session.permissions.some(p=>p==="orders.review"||p==="orders.deliver"||p==="payments.review") && (manualReceipt || ["paid","needs_info","in_progress","ready"].includes(o.status)) && <section className="order-actions"><header><ClipboardList/><div><h3>{copy.next}</h3><p>{next}</p></div></header>{feedback && <p className={`action-feedback ${feedback === "success" ? "success" : "error"}`} role="status">{feedback === "success" ? copy.approved : feedback === "notification" ? (lang === "fa" ? "وضعیت ذخیره شد، اما پیام تلگرام ارسال نشد. از گفت‌وگوی شاگرد دوباره پیام بدهید." : "Status saved, but Telegram delivery failed. Send the message again from the conversation.") : copy.failed}</p>}<div className="action-stack">
      {can(session,"payments.review") && manualReceipt && <><button disabled={busy} className="button success" onClick={() => submit(() => action(`/api/orders/${o.id}/action`, { method:"POST", body:JSON.stringify({ action:"approve_receipt" }) }))}>{busy ? <LoaderCircle className="spin"/> : <Check/>}{t("approve")}</button><button disabled={busy} className="button danger" onClick={() => confirm(t("reject")) && submit(() => action(`/api/orders/${o.id}/action`, { method:"POST", body:JSON.stringify({ action:"reject_receipt" }) }))}><X/>{t("reject")}</button></>}
      {can(session,"orders.review") && ["paid","needs_info"].includes(o.status) && <button disabled={busy} className="button primary" onClick={() => submit(() => action(`/api/orders/${o.id}/action`, { method:"POST", body:JSON.stringify({ action:"in_progress" }) }))}>{busy ? <LoaderCircle className="spin"/> : <Check/>}{lang === "fa" ? "تأیید اطلاعات و شروع طراحی" : "Approve information & start design"}</button>}
      {can(session,"orders.deliver") && ["in_progress","ready"].includes(o.status) && <form className="upload-form" onSubmit={(event) => { event.preventDefault(); const element=event.currentTarget; const form = new FormData(element); submit(async () => { await action(`/api/orders/${o.id}/plan`, { method:"POST", body:form }); element.reset(); setFileName(""); }); }}><div className="upload-title"><Upload/><div><strong>{copy.delivery}</strong><span>{lang === "fa" ? "فایل نهایی مستقیماً برای شاگرد ارسال می‌شود." : "The final file will be sent directly to the client."}</span></div></div><label className="file-picker"><Upload/><span>{fileName || t("chooseFile")}</span><input name="file" type="file" accept=".pdf,.doc,.docx,.xlsx,.jpg,.jpeg,.png" disabled={busy} onChange={(event) => setFileName(event.currentTarget.files?.[0]?.name ?? "")} required /></label><button disabled={busy || !fileName} className="button primary" type="submit">{busy ? <LoaderCircle className="spin"/> : <Send/>}{lang === "fa" ? "ارسال فایل و تحویل دوره" : "Send file & complete order"}</button></form>}
      {can(session,"orders.review") && ["paid","in_progress"].includes(o.status) && <button className="button secondary" disabled={busy} aria-expanded={requestOpen} aria-controls="order-request-form" onClick={() => setRequestOpen(!requestOpen)}><MessageCircle/>{lang === "fa" ? "درخواست اطلاعات بیشتر" : "Request more information"}<ChevronDown/></button>}
      {can(session,"orders.review") && requestOpen && ["paid","in_progress"].includes(o.status) && <form id="order-request-form" onSubmit={(event) => { event.preventDefault(); if (info.trim()) submit(() => action(`/api/orders/${o.id}/action`, { method:"POST", body:JSON.stringify({ action:"needs_info", message:info.trim() }) })); }} className="inline-form"><div><label htmlFor="order-info-request">{t("requestText")}</label></div><textarea id="order-info-request" value={info} maxLength={1000} onChange={(event) => setInfo(event.target.value)} placeholder={lang === "fa" ? "مثلاً: لطفاً سابقه آسیب‌دیدگی و عکس پشت بدن را بفرست." : "For example: please send your injury history and a back photo."} required/><button disabled={busy || !info.trim()} className="button secondary" type="submit"><Send/>{lang === "fa" ? "ارسال درخواست به شاگرد" : "Send request to client"}</button><button disabled={busy} className="button secondary" type="button" onClick={() => setRequestOpen(false)}>{lang === "fa" ? "انصراف" : "Cancel"}</button></form>}
      {userId && o.status !== "needs_info" && <button className="button secondary" disabled={busy || !can(session,"chats.read")} onClick={onConversation}><MessageCircle/>{lang === "fa" ? "گفت‌وگو با شاگرد" : "Chat with client"}</button>}
    </div></section>}
  </div>;
}

function ThreadDrawer({ data, id, session, lang, realtimeVersion, t, action, previewOpen, onPreview }: { data: ThreadDetailData; id: number; session: Session; lang: Lang; realtimeVersion: number; t: (key: CopyKey) => string; action: (path: string, init: RequestInit) => Promise<void>; previewOpen: boolean; onPreview: (media: PreviewMedia) => void }) {
  const [message, setMessage] = useState(""); const [file, setFile] = useState<File>(); const [busy, setBusy] = useState(false); const [failed, setFailed] = useState(false);
  const list = useRef<HTMLDivElement>(null); const editor = useRef<HTMLTextAreaElement>(null); const composer = useRef<HTMLFormElement>(null);
  const stableHeight = useRef(0);
  const previewing = useRef(false); const previewScroll = useRef<number | null>(null);
  const scrollToLatest = useCallback(() => { const node = list.current; if (node && !previewing.current) requestAnimationFrame(() => node.scrollTop = node.scrollHeight); }, []);
  useEffect(scrollToLatest, [data.items.length, scrollToLatest]);
  useLayoutEffect(() => {
    if (previewOpen || !previewing.current || previewScroll.current === null) return;
    const saved = previewScroll.current;
    requestAnimationFrame(() => { if (list.current) list.current.scrollTop = saved; previewing.current = false; });
  }, [previewOpen]);
  useLayoutEffect(() => {
    const node = composer.current;
    if (!node) return;
    const root = document.documentElement;
    const update = () => root.style.setProperty("--chat-composer-height", `${Math.ceil(node.getBoundingClientRect().height)}px`);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => { observer.disconnect(); root.style.removeProperty("--chat-composer-height"); };
  }, []);
  useLayoutEffect(() => {
    const viewport = window.visualViewport;
    const root = document.documentElement;
    let frame = 0;
    const measure = () => {
      // Keep Safari's document scroll separate from the message-list scroll.
      if (window.scrollY !== 0) window.scrollTo({ top:0, left:0, behavior:"instant" });
      const visibleHeight = viewport?.height ?? innerHeight;
      const offsetTop = viewport?.offsetTop ?? 0;
      const prior = chatViewport(stableHeight.current || visibleHeight, visibleHeight, offsetTop);
      if (stableHeight.current === 0 || (!prior.keyboard && document.activeElement !== editor.current)) stableHeight.current = visibleHeight;
      const rect = chatViewport(stableHeight.current, visibleHeight, offsetTop);
      root.style.setProperty("--chat-layout-height", `${Math.round(stableHeight.current)}px`);
      root.style.setProperty("--chat-keyboard-inset", `${rect.keyboardInset}px`);
      root.classList.toggle("chat-keyboard-open", rect.keyboard);
      if (rect.keyboard) scrollToLatest();
    };
    const update = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    viewport?.addEventListener("resize", update);
    viewport?.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    document.addEventListener("focusin", update);
    document.addEventListener("focusout", update);
    return () => {
      cancelAnimationFrame(frame);
      viewport?.removeEventListener("resize", update);
      viewport?.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      document.removeEventListener("focusin", update);
      document.removeEventListener("focusout", update);
      root.classList.remove("chat-keyboard-open");
      root.style.removeProperty("--chat-layout-height");
      root.style.removeProperty("--chat-keyboard-inset");
    };
  }, [scrollToLatest]);
  const send = async (event: FormEvent) => { event.preventDefault(); if ((!message.trim() && !file) || busy) return; setBusy(true); setFailed(false); try { const body = file ? new FormData() : JSON.stringify({ message:message.trim() }); if (body instanceof FormData) { body.append("message",message.trim()); body.append("file",file!); } await action(`/api/threads/${id}/reply`, { method:"POST", body }); setMessage(""); setFile(undefined); } catch { setFailed(true); } finally { setBusy(false); } };
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && matchMedia("(hover: hover) and (pointer: fine)").matches) { event.preventDefault(); event.currentTarget.closest("form")?.requestSubmit(); } };
  const openPreview = (media: PreviewMedia) => { previewScroll.current = list.current?.scrollTop ?? 0; previewing.current = true; onPreview(media); };
  return <div className="chat-shell"><div ref={list} className="chat-list" aria-live="polite"><CollaborationPanel kind="thread" id={id} session={session} lang={lang} version={realtimeVersion}/>{data.items.length ? data.items.map((item: MessageItem, index) => <Fragment key={item.id}>{dayKey(item.created_at) !== dayKey(data.items[index - 1]?.created_at) && <div className="chat-day"><span>{conversationDay(item.created_at,lang)}</span></div>}<div className={`bubble ${item.direction}`}><>{item.direction==="sensi"&&<small className="message-author">{item.sender_name??(lang==="fa"?"مربی (پیام قدیمی)":"Coach (legacy)")}</small>}</><MessageContent item={item} lang={lang} onMediaLoad={scrollToLatest} onPreview={openPreview}/><time>{messageTime(item.created_at, lang)}</time></div></Fragment>) : <Empty text={t("empty")}/>}</div><form ref={composer} hidden={!can(session,"chats.reply")} className="chat-composer" onSubmit={send}>{failed && <p className="chat-composer__error" role="alert">{lang === "fa" ? "ارسال انجام نشد؛ فایل باید حداکثر ۱۰ مگابایت و از نوع مجاز باشد." : "Could not send. Use a supported file up to 10 MB."}</p>}{file && message.length > 1024 && <p className="chat-composer__error" role="alert">{lang === "fa" ? "توضیح پیوست باید حداکثر ۱۰۲۴ نویسه باشد؛ متن فعلی حفظ شده است." : "Attachment captions allow 1,024 characters. Your text has been kept."}</p>}{file && <AttachmentDraft key={`${file.name}-${file.lastModified}`} file={file} lang={lang} onRemove={() => setFile(undefined)} onPreview={openPreview}/>}<label className="chat-composer__attachment" aria-label={lang === "fa" ? "افزودن عکس یا فایل" : "Attach photo or file"}><Paperclip/><input type="file" accept=".jpg,.jpeg,.png,.webp,.gif,.mp4,.mp3,.m4a,.ogg,.wav,.pdf,.doc,.docx,.xlsx,.zip,.txt" onChange={(event) => { const next=event.currentTarget.files?.[0]; if (next && next.size <= 10 * 1024 * 1024) { setFile(next); setFailed(false); } else if (next) setFailed(true); event.currentTarget.value=""; }}/></label><textarea ref={editor} id="reply" className="chat-composer__editor" aria-label={t("reply")} rows={1} maxLength={file ? 1024 : 4000} value={message} placeholder={lang === "fa" ? "پیامت را بنویس…" : "Write a message…"} onChange={(event) => { setMessage(event.currentTarget.value); if (failed) setFailed(false); }} onKeyDown={submitOnEnter}/><button className="chat-composer__send" disabled={busy || (!message.trim() && !file) || Boolean(file && message.length > 1024)} aria-label={t("send")}>{busy ? <LoaderCircle className="spin"/> : <Send />}</button></form></div>;
}

function previewKind(name: string, mime?: string | null): PreviewMedia["kind"] {
  const suffix = name.toLowerCase().split(".").pop();
  const type = mime || "";
  if (type.startsWith("image/") || ["jpg","jpeg","png","webp","gif"].includes(suffix ?? "")) return "image";
  if (type.startsWith("video/") || suffix === "mp4") return "video";
  if (type.startsWith("audio/") || ["mp3","m4a","ogg","wav"].includes(suffix ?? "")) return "audio";
  if (type === "application/pdf" || suffix === "pdf") return "pdf";
  return "file";
}

function AttachmentDraft({ file, lang, onRemove, onPreview }: { file: File; lang: Lang; onRemove: () => void; onPreview: (media: PreviewMedia) => void }) {
  const [source] = useState(() => URL.createObjectURL(file));
  const kind = previewKind(file.name, file.type);
  useEffect(() => () => URL.revokeObjectURL(source), [source]);
  return <div className="chat-composer__draft"><button type="button" className="draft-preview" onClick={() => onPreview({ source, kind, name:file.name })} aria-label={lang === "fa" ? "پیش‌نمایش پیوست" : "Preview attachment"}>{kind === "image" ? <img src={source} alt=""/> : kind === "video" ? <video src={source} muted playsInline/> : <FileText/>}</button><span><strong>{file.name}</strong><small>{new Intl.NumberFormat(lang === "fa" ? "fa-IR" : "en-US", { maximumFractionDigits:1 }).format(file.size / 1024 / 1024)} MB</small></span><button type="button" onClick={onRemove} aria-label={lang === "fa" ? "حذف پیوست" : "Remove attachment"}><X/></button></div>;
}

function MessageContent({ item, lang, onMediaLoad, onPreview }: { item: MessageItem; lang: Lang; onMediaLoad?: () => void; onPreview: (media: PreviewMedia) => void }) {
  const type = item.content_type ?? "text";
  const source = `/media/messages/${item.id}`;
  const name = item.file_name || mediaLabel(type,lang);
  const kind = type === "photo" ? "image" : ["video","animation"].includes(type) ? "video" : ["voice","audio"].includes(type) ? "audio" : previewKind(name,item.mime_type);
  const label = lang === "fa" ? "نمایش پیوست" : "Preview attachment";
  return <>{item.content_text && <p>{item.content_text}</p>}{item.has_attachment && kind === "image" && <button className="message-photo" onClick={() => onPreview({ source,kind,name })}><img src={source} alt={lang === "fa" ? "عکس پیام" : "Message photo"} loading="lazy" decoding="async" onLoad={onMediaLoad}/></button>}{item.has_attachment && kind === "video" && <button className="message-video-button" onClick={() => onPreview({ source,kind,name })}><video className="message-video" src={source} muted playsInline preload="metadata" onLoadedMetadata={onMediaLoad}/><span>{label}</span></button>}{item.has_attachment && kind === "audio" && <audio className="message-audio" src={source} controls preload="metadata"/>}{item.has_attachment && ["pdf","file"].includes(kind) && <button className="message-file" onClick={() => onPreview({ source,kind,name })}><FileText aria-hidden="true"/><span><strong>{name}</strong><small>{label}</small></span></button>}</>;
}

function ProfileAvatar({ userId, name }: { userId: number; name: string }) {
  const source = useCustomerAvatar(userId);
  return <div className="profile-avatar"><span aria-hidden="true">{initial(name)}</span>{source && <img src={source} alt="" decoding="async"/>}</div>;
}

function ConversationAvatar({ userId, name }: { userId: number; name: string }) {
  const source = useCustomerAvatar(userId);
  return <span className="conversation-avatar"><b aria-hidden="true">{initial(name)}</b>{source && <img src={source} alt="" loading="lazy" decoding="async"/>}</span>;
}

function ProfileFact({ icon, label, value, wide = false }: { icon: ReactNode; label: string; value: ReactNode; wide?: boolean }) {
  return <div className={`profile-fact${wide ? " wide" : ""}`}><i aria-hidden="true">{icon}</i><div><span>{label}</span><strong>{value === undefined || value === null || value === "" ? "—" : value}</strong></div></div>;
}

function PhotoGallery({ count = 0, source, lang, onPreview }: { count?: number; source: (index: number) => string; lang: Lang; onPreview: (media: PreviewMedia) => void }) {
  if (!count) return <Empty text={lang === "fa" ? "عکسی برای این دوره ثبت نشده است" : "No photos saved for this course"}/>;
  return <div className="profile-gallery">{Array.from({ length:count }, (_, index) => <button key={index} onClick={() => onPreview({ source:source(index), kind:"image", name:`${lang === "fa" ? "عکس" : "Photo"} ${index + 1}` })} aria-label={`${lang === "fa" ? "نمایش عکس" : "Open photo"} ${index + 1}`}><img src={source(index)} alt={`${lang === "fa" ? "عکس ثبت‌شده" : "Saved photo"} ${index + 1}`} loading="lazy" decoding="async"/><span>{index + 1}</span></button>)}</div>;
}

function CustomerDrawer({ data, lang, t, onSelectOrder, onPreview }: { data: CustomerDetailData; lang: Lang; t: (key: CopyKey) => string; onSelectOrder: (order: OrderDetail, position: number) => void; onPreview: (media: PreviewMedia) => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [openedAt] = useState(Date.now);
  const u = data.user;
  const name = displayName(u, lang);
  const activeCourses = data.orders.filter((order) => ["paid", "needs_info", "in_progress", "ready"].includes(order.status) || (order.status === "delivered" && Boolean(order.delivered_at) && Date.parse(order.delivered_at!) + 30 * 86400000 > openedAt));
  const paidOrders = data.orders.filter((order) => Boolean(order.paid_at));
  const totalPaid = paidOrders.reduce((total, order) => total + Number(order.amount || 0), 0);
  const copy = lang === "fa" ? {
    customerCode:"کد مشتری", registered:"عضویت", profile:"مشخصات فردی", body:"اندازه‌ها و وضعیت بدنی", photos:"عکس‌های ثبت‌شده", plan:"برنامه و سبک تمرین", nutrition:"تغذیه و سلامت", orders:"تاریخچه سفارش‌ها", activeCourses:"دوره‌های فعال", revisions:"تغییرات ثبت‌شده", messages:"پیام‌های اخیر", active:"دوره فعال", paid:"پرداخت موفق", profileRecords:"نسخه اطلاعات", current:"اطلاعات فعلی", foodAllergy:"حساسیت غذایی", restriction:"محدودیت غذایی", supplements:"مکمل‌ها", trainingDays:"روزهای تمرین", workoutDays:"تمرین در هفته", nutritionDays:"روزهای برنامه تغذیه", noRecords:"تغییری ثبت نشده است",
  } : {
    customerCode:"Customer code", registered:"Joined", profile:"Personal details", body:"Body metrics", photos:"Saved photos", plan:"Training profile", nutrition:"Nutrition & health", orders:"Order history", activeCourses:"Active courses", revisions:"Profile revisions", messages:"Recent messages", active:"Active courses", paid:"Paid total", profileRecords:"Profile record", current:"Current profile", foodAllergy:"Food allergy", restriction:"Food restriction", supplements:"Supplements", trainingDays:"Training days", workoutDays:"Workouts / week", nutritionDays:"Nutrition plan days", noRecords:"No profile changes yet",
  };
  const fact = (value: string | number | undefined) => value === undefined || value === null || value === "" ? "—" : value;
  const revisions = data.history.slice(0, 4).map((record, index) => {
    const snapshot = (record.snapshot && typeof record.snapshot === "object" ? record.snapshot : {}) as Record<string, unknown>;
    const raw = (key: string) => snapshot[key] === undefined || snapshot[key] === null || snapshot[key] === "" ? "—" : String(snapshot[key]);
    return { id:String(record.id ?? record.created_at ?? index), title:String(record.product_title ?? copy.profileRecords), date:formatDate(String(record.created_at ?? ""), lang), weight:raw("weight_kg"), goal:raw("goal") };
  });
  const orderList = (orders: OrderDetail[]) => orders.length ? <div className="profile-order-list">{orders.map((order) => <button type="button" className="profile-order" key={order.id} onClick={() => onSelectOrder(order, root.current?.closest<HTMLElement>(".drawer-inner")?.scrollTop ?? 0)}><div><strong>{order.product_title}</strong><span dir="ltr">{orderCode(order.id)}</span></div><span className="profile-order-state"><Status value={order.status} lang={lang}/>{lang === "fa" ? <ChevronLeft/> : <ChevronRight/>}</span><dl><div><dt>{t("amount")}</dt><dd>{money(order.amount, lang)}</dd></div><div><dt>{t("date")}</dt><dd>{formatDate(order.paid_at ?? order.created_at, lang, true)}</dd></div></dl></button>)}</div> : <Empty text={t("empty")}/>;
  return <div className="customer-profile" ref={root}>
    <section className="customer-profile-hero">
      <ProfileAvatar userId={u.id} name={name}/>
      <div className="customer-profile-identity"><span className="profile-overline">{copy.current}</span><h3>{name}</h3><p dir="ltr">{u.username ? `@${u.username}` : `ID ${u.telegram_id}`}</p></div>
      <div className="profile-code"><span>{copy.customerCode}</span><strong dir="ltr">U{String(u.id).padStart(6, "0")}</strong></div>
    </section>
    <section className="profile-stats" aria-label={t("profile")}>
      <div><span>{t("ordersCount")}</span><strong>{data.orders.length}</strong></div><div><span>{copy.active}</span><strong>{activeCourses.length}</strong></div><div><span>{copy.paid}</span><strong>{money(totalPaid, lang)}</strong></div>
    </section>
    <section className="profile-section"><header><div><UserRound aria-hidden="true"/><h3>{copy.profile}</h3></div><span>{copy.registered} · {formatDate(u.created_at, lang, true)}</span></header><div className="profile-facts"><ProfileFact icon={<Phone/>} label={t("phone")} value={fact(u.phone)}/><ProfileFact icon={<Activity/>} label="Telegram ID" value={<bdi>{u.telegram_id}</bdi>}/><ProfileFact icon={<CalendarDays/>} label={t("age")} value={fact(u.age)}/><ProfileFact icon={<UserRound/>} label={t("gender")} value={fact(u.gender)}/></div></section>
    <section className="profile-section"><header><div><Scale aria-hidden="true"/><h3>{copy.body}</h3></div></header><div className="profile-facts"><ProfileFact icon={<Ruler/>} label={t("height")} value={u.height_cm ? `${u.height_cm} cm` : "—"}/><ProfileFact icon={<Scale/>} label={t("weight")} value={u.weight_kg ? `${u.weight_kg} kg` : "—"}/><ProfileFact icon={<Target/>} label={t("goal")} value={fact(u.goal)} wide/></div></section>
    <section className="profile-section"><header><div><Images aria-hidden="true"/><h3>{copy.photos}</h3></div><span>{u.photo_count ?? 0}</span></header><PhotoGallery count={u.photo_count} source={(index) => `/media/customers/${u.id}/photos/${index}?v=${encodeURIComponent(u.updated_at ?? "")}`} lang={lang} onPreview={onPreview}/></section>
    <section className="profile-section"><header><div><Dumbbell aria-hidden="true"/><h3>{copy.plan}</h3></div></header><div className="profile-facts"><ProfileFact icon={<Dumbbell/>} label={t("history")} value={fact(u.training_history)} wide/><ProfileFact icon={<CalendarDays/>} label={copy.trainingDays} value={fact(u.training_days)}/><ProfileFact icon={<Activity/>} label={copy.workoutDays} value={fact(u.workout_days)}/></div></section>
    <section className="profile-section"><header><div><HeartPulse aria-hidden="true"/><h3>{copy.nutrition}</h3></div></header><div className="profile-facts"><ProfileFact icon={<CalendarDays/>} label={copy.nutritionDays} value={fact(u.nutrition_training_days)}/><ProfileFact icon={<HeartPulse/>} label={copy.foodAllergy} value={fact(u.food_allergy)}/><ProfileFact icon={<HeartPulse/>} label={copy.restriction} value={fact(u.food_restriction)} wide/><ProfileFact icon={<CreditCard/>} label={copy.supplements} value={fact(u.supplements)} wide/>{u.notes && <ProfileFact icon={<Activity/>} label={t("notes")} value={u.notes} wide/>}</div></section>
    <section className="profile-section profile-orders"><header><div><Dumbbell aria-hidden="true"/><h3>{copy.activeCourses}</h3></div><span>{activeCourses.length}</span></header>{orderList(activeCourses)}</section>
    <section className="profile-section profile-orders"><header><div><ClipboardList aria-hidden="true"/><h3>{copy.orders}</h3></div><span>{data.orders.length}</span></header>{orderList(data.orders)}</section>
    <section className="profile-section"><header><div><Activity aria-hidden="true"/><h3>{copy.revisions}</h3></div><span>{data.history.length}</span></header>{revisions.length ? <div className="profile-revision-list">{revisions.map((revision) => <article className="profile-revision" key={revision.id}><div><strong>{revision.title}</strong><span>{revision.date}</span></div><dl><div><dt>{t("weight")}</dt><dd>{revision.weight === "—" ? "—" : `${revision.weight} kg`}</dd></div><div><dt>{t("goal")}</dt><dd>{revision.goal}</dd></div></dl></article>)}</div> : <Empty text={copy.noRecords}/>}</section>
    {data.messages.length > 0 && <section className="profile-section profile-messages"><header><div><MessageCircle aria-hidden="true"/><h3>{copy.messages}</h3></div><span>{data.messages.length}</span></header><div>{data.messages.slice(-4).reverse().map((message) => <article className={`profile-message ${message.direction}`} key={message.id}><MessageContent item={message} lang={lang} onPreview={onPreview}/><time>{formatDate(message.created_at, lang, true)}</time></article>)}</div></section>}
  </div>;
}

export default function ConsoleApp({ initialView = "dashboard" }: { initialView?: View }) {
  const [lang, setLang] = useLocalState<Lang>("sensi-lang", "fa");
  const [theme, setTheme] = useLocalState<"dark" | "light">("sensi-theme", "dark");
  const [collapsed, setCollapsed] = useLocalState<"0" | "1">("sensi-nav-collapsed", "0");
  const [session, setSession] = useState<Session | null>();
  const [staffOpen,setStaffOpen] = useState(false);
  const [view, setView] = useState<View>(initialView);
  const [renderedView, setRenderedView] = useState<View>(initialView);
  const [period, setPeriod] = useLocalState<SalesPeriod>("sensi-sales-period-v2", "all");
  const [connection, setConnection] = useState<Connection>("connecting");
  const [data, setData] = useState<PageData>(); const [loading, setLoading] = useState(true); const [failed, setFailed] = useState(false);
  const [unread, setUnread] = useState(0);
  const [pages, setPages] = useState<Record<View, number>>({ dashboard:1, orders:1, messages:1, customers:1, sales:1 });
  const [filters, setFilters] = useState({ q:"", activity:"all", product:"", sort:"recent" });
  const [orderStatus, setOrderStatus] = useState("all");
  const [orderSearch, setOrderSearch] = useState("");
  const [orderSearchDraft, setOrderSearchDraft] = useState("");
  const [messageFilter, setMessageFilter] = useState<"all" | "unread">("all");
  const [messageSearch, setMessageSearch] = useState("");
  const [messageSearchDraft, setMessageSearchDraft] = useState("");
  const [searchDraft, setSearchDraft] = useState(""); const [drawer, setDrawer] = useState<DrawerState>(null); const [refresh, setRefresh] = useState(0);
  const [mobileCustomerToolsHidden, setMobileCustomerToolsHidden] = useState(false);
  const cache = useRef<Record<string, PageData>>({});
  const pathRef = useRef("");
  const viewRef = useRef<View>(initialView);
  const refreshTimer = useRef<number | null>(null);
  const mobileToolsScrollY = useRef(0);
  const t = useMemo(() => translator(lang), [lang]);

  useEffect(() => { viewRef.current = view; }, [view]);
  useEffect(() => { document.documentElement.lang = lang; document.documentElement.dir = lang === "fa" ? "rtl" : "ltr"; document.documentElement.dataset.theme = theme; }, [lang, theme]);
  useEffect(() => { api<Session>("/api/session").then(setSession).catch((error) => setSession(error instanceof ApiError && error.status === 401 ? null : null)); }, []);
  useEffect(() => { const timer = setTimeout(() => { setFilters((old) => ({ ...old, q:searchDraft.trim() })); setPages((old) => ({ ...old, customers:1 })); }, searchDraft ? 650 : 0); return () => clearTimeout(timer); }, [searchDraft]);
  useEffect(() => { const timer = setTimeout(() => { setOrderSearch(orderSearchDraft.trim()); setPages((old) => ({ ...old, orders:1 })); }, orderSearchDraft ? 650 : 0); return () => clearTimeout(timer); }, [orderSearchDraft]);
  useEffect(() => { const timer = setTimeout(() => { setMessageSearch(messageSearchDraft.trim()); setPages((old) => ({ ...old, messages:1 })); }, messageSearchDraft ? 650 : 0); return () => clearTimeout(timer); }, [messageSearchDraft]);
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const currentY = window.scrollY;
      const scrollingUp = currentY < mobileToolsScrollY.current;
      setMobileCustomerToolsHidden(view === "customers" && window.matchMedia("(max-width: 820px)").matches && currentY > 92 && !scrollingUp);
      mobileToolsScrollY.current = currentY;
    };
    const onScroll = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    update();
    addEventListener("scroll", onScroll, { passive:true });
    addEventListener("resize", update);
    return () => { if (frame) cancelAnimationFrame(frame); removeEventListener("scroll", onScroll); removeEventListener("resize", update); };
  }, [view]);

  useEffect(() => {
    if (!session) return;
    let path = `/api/dashboard?period=${period}`;
    if (view === "orders") { const params = new URLSearchParams({ page:String(pages.orders) }); if (orderStatus !== "all") params.set("status",orderStatus); if (orderSearch) params.set("q",orderSearch); path = `/api/orders?${params}`; }
    if (view === "messages") { const params = new URLSearchParams({ page:String(pages.messages) }); if (messageSearch) params.set("q",messageSearch); if (messageFilter === "unread") params.set("unread","1"); path = `/api/threads?${params}`; }
    if (view === "sales") path = `/api/sales?page=${pages.sales}&period=${period}`;
    if (view === "customers") { const params = new URLSearchParams({ page:String(pages.customers), q:filters.q, activity:filters.activity, sort:filters.sort }); if (filters.product) params.set("product", filters.product); path = `/api/customers?${params}`; }
    const controller = new AbortController();
    pathRef.current = path;
    const appendingCustomers = view === "customers" && pages.customers > 1;
    const cached = appendingCustomers ? undefined : cache.current[path];
    if (cached) { setData(cached); setRenderedView(view); }
    setLoading(true);
    api<PageData>(path, session.csrf, { signal:controller.signal }).then((next) => {
      if (!cache.current[path] && Object.keys(cache.current).length >= 24) delete cache.current[Object.keys(cache.current)[0]];
      cache.current[path] = next;
      if (appendingCustomers) setData((current) => {
        if (!current || !("products" in current)) return next;
        const incoming = next as CustomerPage;
        const known = new Set(current.items.map((item) => item.user_id));
        return { ...incoming, items:[...current.items, ...incoming.items.filter((item) => !known.has(item.user_id))] };
      });
      else setData(next);
      setRenderedView(view); setFailed(false);
      if (view === "dashboard") setUnread(Number((next as DashboardData).counts?.unread ?? 0));
      if (view === "messages") setUnread((next as ThreadPage).counts.unread_messages);
    }).catch((error) => {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.status === 401) setSession(null);
      else if (!cache.current[path]) { setData(undefined); setRenderedView(view); setFailed(true); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filters, messageFilter, messageSearch, orderSearch, orderStatus, pages, period, session, view, refresh]);
  useEffect(() => {
    if (!session) return;
    let opened = false;
    const source = new EventSource("/api/events"); source.onopen = () => { setConnection("online"); if (opened) { delete cache.current[pathRef.current]; setRefresh((value) => value + 1); } opened = true; }; source.onerror = () => setConnection(navigator.onLine ? "connecting" : "offline");
    source.addEventListener("session-expired",()=>{source.close();cache.current={};setDrawer(null);setSession(null);});
    source.addEventListener("update", (event) => { try {
      const update = JSON.parse((event as MessageEvent).data) as RealtimeUpdate;
      if (update.table === "support_messages" && update.action === "insert" && update.direction === "customer") setUnread((value) => value + 1);
      if (update.table && !realtimeTables[viewRef.current].includes(update.table)) return;
      delete cache.current[pathRef.current];
      if (refreshTimer.current === null) refreshTimer.current = window.setTimeout(() => { refreshTimer.current = null; if (viewRef.current === "customers") setPages((old) => ({ ...old, customers:1 })); setRefresh((value) => value + 1); }, 1_000);
    } catch { /* ignored */ } });
    const online = () => setConnection("connecting"), offline = () => setConnection("offline"); window.addEventListener("online", online); window.addEventListener("offline", offline);
    return () => { source.close(); if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current); refreshTimer.current = null; window.removeEventListener("online", online); window.removeEventListener("offline", offline); };
  }, [session]);
  useEffect(() => { if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js", { updateViaCache:"none" }).then((worker) => worker.update()).catch(() => undefined); }, []);

  const showView = useCallback((next: View, push: boolean) => {
    if (next === "customers") setPages((old) => old.customers === 1 ? old : { ...old, customers:1 });
    setView(next); setDrawer(null); setFailed(false); setLoading(true);
    if (push) history.pushState(null, "", next === "dashboard" ? "/" : `/${next}`);
    window.scrollTo({ top:0, behavior:"auto" });
  }, []);
  const navigate = (next: View) => { if (next !== view) showView(next, true); };
  useEffect(() => { const pop = () => { const next = location.pathname.split("/")[1] as View; showView(["orders","messages","customers","sales"].includes(next) ? next : "dashboard", false); }; addEventListener("popstate", pop); return () => removeEventListener("popstate", pop); }, [showView]);
  const setPage = (page: number) => setPages((old) => ({ ...old, [view]:page }));
  const mutate = async (path: string, body: unknown) => { if (!session) return; await api(path, session.csrf, { method:"POST", body:JSON.stringify(body) }); setRefresh((value) => value + 1); };

  if (session === undefined) return <main className="boot"><div className="brand-mark"><span>S</span></div><LoaderCircle className="spin"/></main>;
  if (!session) return <Login lang={lang}/>;
  const allNav: Array<[View, CopyKey, typeof LayoutDashboard]> = [["dashboard","dashboard",LayoutDashboard],["orders","orders",ClipboardList],["messages","messages",MessageCircle],["customers","customers",UsersRound],["sales","sales",BarChart3]];
  const nav = allNav.filter(([key])=>key==="dashboard"||can(session,({orders:"orders.read",messages:"chats.read",customers:"customers.read",sales:"sales.read"} as Record<string,string>)[key]));
  const customerData = renderedView === "customers" && data && "products" in data ? data as CustomerPage : undefined;
  const headerControls = <><div className={`sync-status glass ${connection} ${lang}`} role="status" aria-live="polite"><span>{connection === "online" ? t("connected") : t(connection)}</span>{connection !== "online" && <LoaderCircle className="spin"/>}<i/></div><header className="topbar glass"><button className="top-button" onClick={()=>setStaffOpen(true)} aria-label={lang==="fa"?"پروفایل و مدیریت تیم":"Profile and team"}><UserRound/></button><button className="top-button" onClick={() => setLang(lang === "fa" ? "en" : "fa")} aria-label="Language">{lang === "fa" ? "EN" : "فا"}</button><button className="top-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Theme">{theme === "dark" ? <Sun/> : <Moon/>}</button></header></>;
  return <div className={`app-shell ${collapsed === "1" ? "nav-collapsed" : ""}${view === "customers" ? " customers-view" : ""}`}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    {staffOpen&&<StaffPanel session={session} lang={lang} onClose={()=>{setStaffOpen(false);void api<Session>("/api/session").then(setSession).catch(()=>setSession(null));}}/>}
    <div className="ambient" aria-hidden="true"><i/><i/><i/></div>
    <aside className="sidebar glass"><div className="sidebar-brand"><div className="brand-mark small"><span>S</span></div><strong>Sensi</strong><button className="collapse-button" onClick={() => setCollapsed(collapsed === "1" ? "0" : "1")} aria-expanded={collapsed !== "1"} aria-label={t(collapsed === "1" ? "expandNav" : "collapseNav")}><Menu /></button></div><nav>{nav.map(([key,label,Icon]) => <button key={key} className={view === key ? "active" : ""} onClick={() => navigate(key)} aria-label={t(label)} title={t(label)}><Icon/><span>{t(label)}</span>{key === "messages" && unread > 0 && <b>{unread}</b>}</button>)}</nav><div className="sidebar-foot"><span className={`connection ${connection}`}><i/>{connection === "online" ? t("connected") : t(connection)}</span></div></aside>
    {view === "customers" ? <section className={`customer-mobile-bar glass${mobileCustomerToolsHidden ? " is-hidden" : ""}`}>{headerControls}{customerData && <CustomerTools data={customerData} lang={lang} t={t} setPage={setPage} filters={filters} setFilters={setFilters} searchDraft={searchDraft} setSearchDraft={setSearchDraft} className="mobile-customer-tools"/>}</section> : headerControls}
    <main id="main-content" className="content" tabIndex={-1}>
      {loading && <div className="page-progress" role="progressbar" aria-label="Loading"/>}
      <div className="content-pane" aria-busy={loading}>
        {!data ? (failed ? <Glass><Empty text={t("error")}/><button className="button secondary center" onClick={() => setRefresh((value) => value + 1)}>{t("retry")}</button></Glass> : <Skeleton/>) : <ViewContent view={renderedView} data={data} loading={loading} session={session} lang={lang} t={t} period={period} setPeriod={setPeriod} pages={pages} setPage={setPage} filters={filters} setFilters={setFilters} searchDraft={searchDraft} setSearchDraft={setSearchDraft} orderStatus={orderStatus} setOrderStatus={setOrderStatus} orderSearch={orderSearch} setOrderSearch={setOrderSearch} orderSearchDraft={orderSearchDraft} setOrderSearchDraft={setOrderSearchDraft} messageFilter={messageFilter} setMessageFilter={setMessageFilter} messageSearch={messageSearch} setMessageSearch={setMessageSearch} messageSearchDraft={messageSearchDraft} setMessageSearchDraft={setMessageSearchDraft} navigate={navigate} openDrawer={setDrawer} mutate={mutate} refresh={() => setRefresh((value) => value + 1)}/>}
      </div>
    </main>
    <nav className="mobile-nav glass">{nav.map(([key,label,Icon]) => <button key={key} className={view === key ? "active" : ""} onClick={() => navigate(key)} aria-label={t(label)}><Icon/>{key === "messages" && unread > 0 && <b>{unread}</b>}</button>)}</nav>
    {drawer && <Drawer key={`${drawer.type}:${drawer.id}`} state={drawer} session={session} lang={lang} t={t} realtimeVersion={refresh} onClose={() => setDrawer(null)} onNavigate={setDrawer} onChanged={() => setRefresh((value) => value + 1)}/>}<div className="sr-only" aria-live="polite">{connection === "online" ? t("connected") : t(connection)}</div>
  </div>;
}

function ViewContent(props: { view: View; data: PageData; loading: boolean; session: Session; lang: Lang; t: (key: CopyKey) => string; period: SalesPeriod; setPeriod: (value: SalesPeriod) => void; pages: Record<View, number>; setPage: (page: number) => void; filters: {q:string;activity:string;product:string;sort:string}; setFilters: React.Dispatch<React.SetStateAction<{q:string;activity:string;product:string;sort:string}>>; searchDraft: string; setSearchDraft: (value:string) => void; orderStatus:string; setOrderStatus:(value:string)=>void; orderSearch:string; setOrderSearch:(value:string)=>void; orderSearchDraft:string; setOrderSearchDraft:(value:string)=>void; messageFilter:"all"|"unread"; setMessageFilter:(value:"all"|"unread")=>void; messageSearch:string; setMessageSearch:(value:string)=>void; messageSearchDraft:string; setMessageSearchDraft:(value:string)=>void; navigate:(view:View)=>void; openDrawer:(state:DrawerState)=>void; mutate:(path:string,body:unknown)=>Promise<void>; refresh:()=>void }) {
  if (props.view === "dashboard") return <Dashboard {...props} data={props.data as DashboardData}/>;
  if (props.view === "customers") return <Customers {...props} data={props.data as CustomerPage}/>;
  if (props.view === "orders") return <Orders {...props} data={props.data as OrderPage}/>;
  if (props.view === "messages") return <Messages {...props} data={props.data as ThreadPage}/>;
  return <Sales {...props} data={props.data as SalesData}/>;
}

function Dashboard({ data, session, lang, t, period, setPeriod, navigate, mutate }: { data: DashboardData; session: Session; lang: Lang; t:(key:CopyKey)=>string; period:SalesPeriod; setPeriod:(value:SalesPeriod)=>void; navigate:(view:View)=>void; mutate:(path:string,body:unknown)=>Promise<void> }) {
  const priorities: Array<[CopyKey, string, number]> = [["unreadMessages","violet",data.counts.unread],["receipts","rose",data.counts.receipts],["newOrders","blue",data.counts.new_orders],["designing","cyan",data.counts.designing],["needsInfo","slate",data.counts.needs_info]];
  return <>
    <div className="dashboard-kpis">
      <Glass className={`kpi-card sales-summary${can(session,"sales.read")?"":" staff-restricted"}`}>
        <span className="metric-label"><CircleDollarSign/>{t("sales")}</span>
        <strong>{money(data.sales.revenue, lang)}</strong>
        <small>{data.sales.orders} {t("ordersCount")}</small>
        <div className="segmented sales-periods" aria-label={t("sales")}>
          {periods.map((item) => <button key={item} aria-pressed={period === item} onClick={() => setPeriod(item)}>{t(item)}</button>)}
        </div>
      </Glass>
      <Glass className="kpi-card"><span className="metric-label"><UsersRound/>{t("activeCustomers")}</span><strong>{data.counts.active ?? data.buyers}</strong></Glass>
      <Glass className="kpi-card"><span className="metric-label"><UserRound/>{t("usersCount")}</span><strong>{data.users}</strong></Glass>
      {data.commission !== undefined && <Glass className="kpi-card"><span className="metric-label"><BarChart3/>{t("commission")}</span><strong>{money(data.commission, lang)}</strong></Glass>}
    </div>
    <div className="dashboard-grid">
      <Glass className={`sales-card${can(session,"sales.read")?"":" staff-restricted"}`}><div className="card-head"><span className="metric-label"><BarChart3/>{t("salesTrend")}</span><div className="segmented">{periods.map((item) => <button key={item} aria-pressed={period === item} onClick={() => setPeriod(item)}>{t(item)}</button>)}</div></div><TrendChart data={data.sales} lang={lang}/></Glass>
      {session.permissions.some(p=>p==="orders.review"||p==="orders.deliver"||p==="payments.review") && <div className="dashboard-side"><Glass className="priority-card"><div className="card-title"><h2>{t("priority")}</h2><span>{priorities.reduce((sum, item) => sum + Number(item[2] || 0), 0)}</span></div><div className="priority-list">{priorities.map(([label,color,value]) => <div key={label}><i className={color}/><span>{t(label)}</span><strong>{value || 0}</strong></div>)}</div></Glass><Glass className="quick-card"><div className="card-title"><h2>{t("quickActions")}</h2><span className={`sales-state ${data.salesOpen ? "open" : "closed"}`}><i/>{t(data.salesOpen ? "salesOpen" : "salesClosed")}</span></div><div className="quick-grid"><button disabled={!can(session,"chats.read")} onClick={() => navigate("messages")}><MessageCircle/><span>{t("openMessages")}</span></button><button disabled={!can(session,"orders.read")} onClick={() => navigate("orders")}><ClipboardList/><span>{t("reviewReceipts")}</span></button><button disabled={!can(session,"sales.manage")} className={data.salesOpen ? "danger" : "success"} onClick={() => { if (!data.salesOpen || confirm(t("closeSalesConfirm"))) mutate("/api/sales-gate", { open:!data.salesOpen }); }}>{data.salesOpen ? <LockKeyhole/> : <UnlockKeyhole/>}<span>{t(data.salesOpen ? "closeSales" : "openSales")}</span></button><button className="danger" onClick={() => api("/api/logout", session.csrf, { method:"POST" }).finally(() => location.reload())}><LogOut/><span>{t("logout")}</span></button></div></Glass></div>}
      {!session.permissions.some(p=>p==="orders.review"||p==="orders.deliver"||p==="payments.review") && <div className="dashboard-side"><Glass className="quick-card"><div className="card-title"><h2>{t("quickActions")}</h2></div><div className="quick-grid"><button className="danger" onClick={() => api("/api/logout", session.csrf, { method:"POST" }).finally(() => location.reload())}><LogOut/><span>{t("logout")}</span></button></div></Glass></div>}
    </div>
  </>;
}

function CustomerTools({ data, lang, t, setPage, filters, setFilters, searchDraft, setSearchDraft, className = "" }: { data:CustomerPage; lang:Lang; t:(key:CopyKey)=>string; setPage:(page:number)=>void; filters:{q:string;activity:string;product:string;sort:string}; setFilters:React.Dispatch<React.SetStateAction<{q:string;activity:string;product:string;sort:string}>>; searchDraft:string; setSearchDraft:(value:string)=>void; className?:string }) {
  const searchInput = useRef<HTMLInputElement>(null);
  const products: Array<[string,string]> = [["",t("allCourses")], ...(data.products ?? []).map((p:ProductOption) => [String(p.id),p.title] as [string,string])];
  const change = (key:"activity"|"product"|"sort", value:string) => { setPage(1); setFilters((old) => ({ ...old, [key]:value })); };
  const hasFilters = Boolean(searchDraft || filters.activity !== "all" || filters.product || filters.sort !== "recent");
  const compact = lang === "fa" ? ["وضعیت", "دوره", "تازه‌ترین"] : ["Status", "Course", "Newest"];
  return <Glass className={`customer-tools ${className}`}><label className="search-field"><Search/><span className="sr-only">{t("searchCustomer")}</span><input ref={searchInput} value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder={t("searchCustomer")} autoComplete="off" spellCheck={false} enterKeyHint="search"/></label><div className="filter-row" aria-label={t("sortBy")}><SelectMenu compact compactDefault={compact[0]} label={t("activityFilter")} value={filters.activity} options={[["all",t("allStudents")],["active",t("activeOnly")],["inactive",t("inactiveOnly")]]} onChange={(value) => change("activity",value)}/><SelectMenu compact compactDefault={compact[1]} label={t("courseFilter")} value={filters.product} options={products} onChange={(value) => change("product",value)}/><SelectMenu compact compactDefault={compact[2]} label={t("sortBy")} value={filters.sort} options={[["recent",t("sortRecent")],["name_asc",t("sortNameAsc")],["name_desc",t("sortNameDesc")],["spend_desc",t("sortSpendDesc")],["spend_asc",t("sortSpendAsc")],["orders_desc",t("sortOrdersDesc")],["orders_asc",t("sortOrdersAsc")]]} onChange={(value) => change("sort",value)}/><button className={`filter-clear${hasFilters ? " active" : ""}`} aria-label={t("clearFilters")} title={t("clearFilters")} disabled={!hasFilters} onClick={() => { setPage(1); setSearchDraft(""); setFilters({q:"",activity:"all",product:"",sort:"recent"}); }}><X/><span className="filter-clear-label">{t("clearFilters")}</span></button></div></Glass>;
}

function Customers({ data, loading, lang, t, setPage, filters, setFilters, searchDraft, setSearchDraft, openDrawer }: { data:CustomerPage; loading:boolean; lang:Lang; t:(key:CopyKey)=>string; setPage:(page:number)=>void; filters:{q:string;activity:string;product:string;sort:string}; setFilters:React.Dispatch<React.SetStateAction<{q:string;activity:string;product:string;sort:string}>>; searchDraft:string; setSearchDraft:(value:string)=>void; openDrawer:(state:DrawerState)=>void }) {
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (loading || data.items.length >= data.total || !sentinel.current) return;
    const observer = new IntersectionObserver(([entry]) => { if (entry?.isIntersecting) setPage(data.page + 1); }, { rootMargin:"500px" });
    observer.observe(sentinel.current);
    return () => observer.disconnect();
  }, [data.items.length, data.page, data.total, loading, setPage]);
  return <div className="customers-layout"><CustomerTools data={data} lang={lang} t={t} setPage={setPage} filters={filters} setFilters={setFilters} searchDraft={searchDraft} setSearchDraft={setSearchDraft} className="desktop-customer-tools"/><div className="customer-results">{data.items.length ? <div className="customer-grid">{data.items.map((customer) => { const name=displayName(customer,lang); const identifier=customer.username ? `@${customer.username}` : `U${String(customer.user_id).padStart(6,"0")}`; return <article className="customer-card glass" key={customer.user_id}><button className="customer-profile-action" onClick={() => openDrawer({type:"customer",id:customer.user_id})}><CustomerPhoto userId={customer.user_id} name={name}/><div className="customer-info"><div className="customer-name"><h2>{name}</h2><p dir="ltr">{identifier}</p></div></div></button><footer className="customer-footer"><dl><div><dt>{t("ordersCount")}</dt><dd>{customer.orders_count}</dd></div><div><dt>{lang === "en" ? "Active" : t("activeCourses")}</dt><dd>{customer.active_courses}</dd></div></dl><button className="customer-message" aria-label={t("openMessages")} onClick={() => openDrawer({type:"thread",id:customer.user_id})}><i><MessageCircle/></i></button></footer></article>; })}</div> : <Glass><Empty text={t("noCustomerResults")}/></Glass>}<div ref={sentinel} className={`load-more-sentinel${loading ? " loading" : ""}`} aria-hidden="true">{loading && <LoaderCircle className="spin"/>}</div></div></div>;
}

function Orders({ data, lang, t, pages, setPage, openDrawer, orderStatus, setOrderStatus, orderSearch, setOrderSearch, orderSearchDraft, setOrderSearchDraft }: { data:OrderPage; lang:Lang; t:(key:CopyKey)=>string; pages:Record<View,number>; setPage:(page:number)=>void; openDrawer:(state:DrawerState)=>void; orderStatus:string; setOrderStatus:(value:string)=>void; orderSearch:string; setOrderSearch:(value:string)=>void; orderSearchDraft:string; setOrderSearchDraft:(value:string)=>void }) {
  const copy = lang === "fa" ? { title:"کارها", subtitle:"از بررسی اطلاعات تا تحویل برنامه", search:"نام شاگرد یا کد سفارش…", all:"همه", receipt:"رسید کارت‌به‌کارت", new:"بررسی اطلاعات", design:"طراحی و ارسال", waiting:"منتظر پاسخ", next:"اقدام بعدی", view:"بازکردن کار", noResult:"کاری با این مشخصات پیدا نشد.", review:"بررسی اطلاعات و عکس‌ها", deliver:"آماده‌سازی و ارسال فایل", reply:"دیدن درخواست و پاسخ‌ها", sorted:"قدیمی‌ترها در ابتدای هر مرحله", count:"کار", cleared:"همه کارها انجام شده‌اند", paid:"پرداخت تأییدشده" } : { title:"Tasks", subtitle:"From client brief to delivery", search:"Client name or order code…", all:"All", receipt:"Bank transfers", new:"Review information", design:"Design & send", waiting:"Awaiting reply", next:"Next action", view:"Open task", noResult:"No task matches these filters.", review:"Review brief & photos", deliver:"Prepare & send plan", reply:"View request & replies", sorted:"Oldest first in each stage", count:"tasks", cleared:"You’re all caught up", paid:"Payment confirmed" };
  const filters = [
    ["paid",copy.new,data.counts.new_orders,ClipboardList],
    ["in_progress",copy.design,data.counts.designing,Activity],
    ["needs_info",copy.waiting,data.counts.needs_info,MessageCircle],
  ] as const;
  const task = (status:string) => status === "awaiting_receipt" ? copy.receipt : status === "paid" ? copy.review : ["in_progress","ready"].includes(status) ? copy.deliver : copy.reply;
  const clearSearch = () => { setPage(1); setOrderSearchDraft(""); setOrderSearch(""); };
  const select = (value:string) => { setPage(1); setOrderStatus(value); };
  return <div className="work-page task-board">
    <header className="task-heading"><div><h1>{copy.title}<span>{data.counts.actionable}</span></h1><p>{copy.subtitle}</p></div><div className="work-search" role="search"><Search/><label className="sr-only" htmlFor="order-search">{copy.search}</label><input id="order-search" value={orderSearchDraft} onChange={(event) => setOrderSearchDraft(event.target.value)} placeholder={copy.search} autoComplete="off" enterKeyHint="search"/>{(orderSearchDraft || orderSearch) && <button type="button" onClick={clearSearch} aria-label={t("clearFilters")}><X/></button>}</div></header>
    <nav className="task-stages" aria-label={t("filters")}>{filters.map(([value,label,count,Icon],index) => <button key={value} aria-pressed={orderStatus === value} onClick={() => select(value)}><span className="task-stage-top"><Icon/><b>{new Intl.NumberFormat(lang === "fa" ? "fa-IR" : "en-US").format(count)}</b></span><span>{label}</span><small>{index === 0 ? (lang === "fa" ? "شروع از اینجا" : "Start here") : index === 1 ? (lang === "fa" ? "آماده‌سازی برنامه" : "Prepare the plan") : (lang === "fa" ? "تکمیل اطلاعات" : "Complete the brief")}</small></button>)}</nav>
    <div className="task-list-toolbar"><div><button aria-pressed={orderStatus === "all"} onClick={() => select("all")}>{copy.all}<b>{data.counts.actionable}</b></button>{(data.counts.receipts > 0 || orderStatus === "awaiting_receipt") && <button aria-pressed={orderStatus === "awaiting_receipt"} onClick={() => select("awaiting_receipt")}><CreditCard/>{copy.receipt}<b>{data.counts.receipts}</b></button>}</div><span>{copy.sorted}</span></div>
    {data.items.length ? <div className="task-list">{data.items.map((item) => { const name=displayName(item,lang); const userId=item.customer_id ?? item.user_id; return <button className={`task-card status-${item.status}`} key={item.id} onClick={() => openDrawer({type:"order",id:item.id})} aria-label={`${task(item.status)}: ${name}, ${item.product_title}`}>
      <span className="task-client">{userId ? <ConversationAvatar userId={userId} name={name}/> : <span className="conversation-avatar" aria-hidden="true">{initial(name)}</span>}<span><strong>{name}</strong><bdi>U{String(userId ?? item.telegram_id ?? 0).padStart(6,"0")}</bdi></span></span>
      <span className="task-product"><strong>{item.product_title}</strong><span><bdi>{orderCode(item.id)}</bdi><time>{formatDate(item.created_at,lang)}</time></span></span>
      <span className="task-status"><Status value={item.status} lang={lang}/><small>{item.payment_method === "zarinpal" && item.payment_status === "paid" ? (lang === "fa" ? "تأیید خودکار زرین‌پال" : "Verified by ZarinPal") : item.paid_at ? copy.paid : money(item.amount,lang)}</small></span>
      <span className="task-cta">{task(item.status)}{lang === "fa" ? <ArrowLeft/> : <ArrowRight/>}</span>
    </button>; })}</div> : <Glass className="work-empty"><Empty text={orderSearch || orderStatus !== "all" ? copy.noResult : copy.cleared}/>{(orderSearch || orderStatus !== "all") && <button className="button secondary" onClick={() => { clearSearch(); select("all"); }}>{t("clearFilters")}</button>}</Glass>}
    <Pager page={pages.orders} total={data.total} size={data.pageSize} t={t} onChange={setPage}/></div>;
}

function Messages({ data, lang, t, pages, setPage, openDrawer, messageFilter, setMessageFilter, messageSearch, setMessageSearch, messageSearchDraft, setMessageSearchDraft }: { data:ThreadPage; lang:Lang; t:(key:CopyKey)=>string; pages:Record<View,number>; setPage:(page:number)=>void; openDrawer:(state:DrawerState)=>void; messageFilter:"all"|"unread"; setMessageFilter:(value:"all"|"unread")=>void; messageSearch:string; setMessageSearch:(value:string)=>void; messageSearchDraft:string; setMessageSearchDraft:(value:string)=>void }) {
  const preview = (item: ThreadListItem) => `${item.last_direction === "sensi" ? (lang === "fa" ? "شما: " : "You: ") : ""}${item.last_content_text?.trim() || mediaLabel(item.last_content_type, lang)}`;
  const copy = lang === "fa" ? { title:"پیام‌ها", search:"جست‌وجوی نام، نام کاربری یا کد مشتری…", all:"همه", unread:"خوانده‌نشده", open:"بازکردن گفت‌وگو", empty:"گفت‌وگویی با این مشخصات پیدا نشد." } : { title:"Messages", search:"Search name, username or customer code…", all:"All", unread:"Unread", open:"Open conversation", empty:"No conversations match these filters." };
  const clear = () => { setPage(1); setMessageSearchDraft(""); setMessageSearch(""); setMessageFilter("all"); };
  const filtered = Boolean(messageSearch || messageFilter !== "all");
  return <div className="messenger-page"><Glass className="messenger-shell"><header className="messenger-head"><div><span className="messenger-icon"><MessageCircle/></span><div><h1>{copy.title}</h1><p>{data.total} {lang === "fa" ? "گفت‌وگو" : "conversations"}</p></div></div>{data.counts.unread_messages > 0 && <span className="messenger-unread"><b>{data.counts.unread_messages}</b><span>{copy.unread}</span></span>}</header><div className="messenger-search" role="search"><Search/><label className="sr-only" htmlFor="message-search">{copy.search}</label><input id="message-search" value={messageSearchDraft} onChange={(event) => setMessageSearchDraft(event.target.value)} placeholder={copy.search} autoComplete="off" enterKeyHint="search"/>{(messageSearchDraft || messageSearch) && <button type="button" onClick={() => { setPage(1); setMessageSearchDraft(""); setMessageSearch(""); }} aria-label={t("clearFilters")}><X/></button>}</div><nav className="messenger-tabs" aria-label={t("filters")}><button aria-pressed={messageFilter === "all"} onClick={() => { setPage(1); setMessageFilter("all"); }}>{copy.all}<b>{data.counts.all}</b></button><button aria-pressed={messageFilter === "unread"} onClick={() => { setPage(1); setMessageFilter("unread"); }}>{copy.unread}<b>{data.counts.unread_threads}</b></button></nav>{data.items.length ? <div className="conversation-list">{data.items.map((item) => { const name=displayName(item,lang); return <button className={`conversation-row${item.unread_count ? " unread" : ""}`} key={item.user_id} onClick={() => openDrawer({type:"thread",id:item.user_id})} aria-label={`${copy.open}: ${name}`}><ConversationAvatar userId={item.user_id} name={name}/><span className="conversation-copy"><strong>{name}</strong><small>{preview(item)}</small></span><span className="conversation-meta"><time>{conversationTime(item.last_message_at,lang)}</time>{item.unread_count > 0 && <b>{item.unread_count}</b>}</span></button>; })}</div> : <div className="messenger-empty"><Empty text={filtered ? copy.empty : t("empty")}/>{filtered && <button className="button secondary" onClick={clear}>{t("clearFilters")}</button>}</div>}</Glass><Pager page={pages.messages} total={data.total} size={data.pageSize} t={t} onChange={setPage}/></div>;
}

function Sales({ data, lang, t, period, setPeriod, pages, setPage, openDrawer }: { data:SalesData; lang:Lang; t:(key:CopyKey)=>string; period:SalesPeriod; setPeriod:(value:SalesPeriod)=>void; pages:Record<View,number>; setPage:(page:number)=>void; openDrawer:(state:DrawerState)=>void }) {
  const average = data.orders ? Number(data.revenue) / data.orders : 0;
  const copy = lang === "fa" ? { title:"مرکز فروش", subtitle:"درآمد، سهم‌ها و فاکتورها در یک نگاه", trend:"روند درآمد", average:"میانگین هر سفارش", split:"تقسیم درآمد", transactions:"تراکنش‌ها", invoices:"فاکتور ثبت‌شده", sensi:"سهم سنسی", open:"مشاهده سفارش" } : { title:"Sales center", subtitle:"Revenue, shares and invoices at a glance", trend:"Revenue trend", average:"Average order", split:"Revenue split", transactions:"Transactions", invoices:"recorded invoices", sensi:"Sensi share", open:"Open order" };
  const changePeriod = (value: SalesPeriod) => { setPage(1); setPeriod(value); };
  return <div className="sales-workspace">
    <Glass className="sales-overview"><header><div><span className="sales-icon"><CircleDollarSign/></span><div><h1>{copy.title}</h1><p>{copy.subtitle}</p></div></div><div className="segmented sales-periods" aria-label={t("sales")}>{periods.map((item) => <button key={item} aria-pressed={period === item} onClick={() => changePeriod(item)}>{t(item)}</button>)}</div></header><div className="sales-metrics"><div><span>{t("sales")}</span><strong>{money(data.revenue,lang)}</strong></div><div><span>{t("ordersCount")}</span><strong>{data.orders}</strong></div><div><span>{copy.average}</span><strong>{money(average,lang)}</strong></div></div></Glass>
    <div className="sales-analysis"><Glass className="sales-trend"><header><div><BarChart3/><h2>{copy.trend}</h2></div><span>{t(period)}</span></header><TrendChart data={data} lang={lang}/></Glass><Glass className="sales-split"><header><div><CircleDollarSign/><h2>{copy.split}</h2></div><b>{data.commissionPercent ?? 50}%</b></header><dl><div><dt>{copy.sensi}</dt><dd>{money(data.net ?? 0,lang)}</dd></div><div><dt>{t("commission")}</dt><dd>{money(data.commission ?? 0,lang)}</dd></div></dl><div className="split-bar" aria-label={copy.split}><i style={{ width:`${100 - (data.commissionPercent ?? 50)}%` }}/><span/></div></Glass></div>
    <Glass className="sales-ledger"><header><div><ClipboardList/><div><h2>{copy.transactions}</h2><p>{data.count} {copy.invoices}</p></div></div></header><div className="sales-ledger-head"><span>{t("orderCode")}</span><span>{t("customer")}</span><span>{t("course")}</span><span>{t("amount")}</span><span>{t("date")}</span></div>{data.items.length ? <div className="sales-ledger-list">{data.items.map((item) => <button key={item.order_id} onClick={() => openDrawer({type:"order",id:item.order_id,source:"sales"})} aria-label={`${copy.open} ${orderCode(item.order_id)}`}><strong dir="ltr">{orderCode(item.order_id)}</strong><span>{displayName(item,lang)}</span><span>{item.product_title}</span><b>{money(item.amount,lang)}</b><time>{formatDate(item.paid_at,lang,true)}</time><i>{lang === "fa" ? <ChevronLeft/> : <ChevronRight/>}</i></button>)}</div> : <Empty text={t("empty")}/>}</Glass>
    <Pager page={pages.sales} total={data.count} size={data.pageSize} t={t} onChange={setPage}/>
  </div>;
}
