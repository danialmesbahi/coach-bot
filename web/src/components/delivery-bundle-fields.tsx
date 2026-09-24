/* eslint-disable @next/next/no-img-element -- Local files already exist in the browser; no network image optimization applies. */
import { ReactNode, useEffect, useRef, useState } from "react";
import { FileText, FileUp, Play, Plus, Upload, X } from "lucide-react";
import type { PreviewMedia } from "./media-viewer";
import type { Lang } from "@/lib/types";

export function DeliveryBundleFields({lang,message,onMessageChange,links,onLinksChange,maxLength,disabled,automatic=false,children}:{
  lang:Lang; message:string; onMessageChange:(value:string)=>void; links:string[];
  onLinksChange:(links:string[])=>void; maxLength:number; disabled?:boolean; automatic?:boolean; children:ReactNode;
}) {
  const fa=lang==="fa";
  return <div className={`delivery-bundle-fields${automatic?" delivery-bundle delivery-bundle-automatic":""}`}>
    {automatic&&<div className="upload-title"><Upload/><div><strong>{fa?"تحویل خودکار برنامه":"Automatic delivery"}</strong><span>{fa?"پیام، چند فایل و لینک را با هم یا جداگانه برای خریدار بفرست.":"Send a message, multiple files and links together or separately."}</span></div></div>}
    <label className="delivery-field"><strong>{fa?"پیام همراه تحویل":"Delivery message"}</strong><span>{fa?"اختیاری؛ توضیحی که شاگرد همراه محتوا دریافت می‌کند.":"Optional note the client receives with the content."}</span>
      <textarea maxLength={maxLength} rows={3} value={message} disabled={disabled} onChange={event=>onMessageChange(event.target.value)} placeholder={fa?"توضیح تحویل برنامه…":"Delivery note…"}/>
    </label>
    {children}
    <div className="delivery-links"><strong>{fa?"لینک‌های قابل تحویل":"Delivery links"}</strong><p>{fa?"هر لینک را جدا اضافه کن. برای فایل‌ها نیازی به لینک نیست.":"Add each link separately. Uploaded files need no link."}</p>
      {links.map((url,index)=><div key={index}><input type="url" value={url} placeholder="https://…" maxLength={1500} disabled={disabled} aria-label={(fa?"لینک ":"Link ")+(index+1)} onChange={event=>onLinksChange(links.map((item,i)=>i===index?event.target.value:item))}/><button type="button" className="icon-button" disabled={disabled} aria-label={fa?"حذف لینک":"Remove link"} onClick={()=>onLinksChange(links.filter((_,i)=>i!==index))}><X/></button></div>)}
      <button type="button" className="button secondary" disabled={disabled||links.length>=20} onClick={()=>onLinksChange([...links,""])}><Plus/>{fa?"افزودن لینک":"Add link"}</button>
    </div>
  </div>;
}

export function DeliveryFilePicker({lang,count,description,disabled,onFiles}:{lang:Lang;count:number;description:string;disabled?:boolean;onFiles:(files:File[])=>void}) {
  const fa=lang==="fa",input=useRef<HTMLInputElement>(null),[dragging,setDragging]=useState(false);
  return <><div className="catalog-files-heading delivery-files-heading"><div><h4>{fa?"فایل‌های قابل تحویل":"Delivery files"}</h4><p>{description}</p></div><span>{count.toLocaleString(fa?"fa-IR":"en")} {fa?"فایل":"files"}</span></div>
    <div className="catalog-file-picker delivery-file-picker" data-dragging={dragging} onDragOver={event=>{event.preventDefault();if(!disabled)setDragging(true);}} onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setDragging(false);}} onDrop={event=>{event.preventDefault();setDragging(false);if(!disabled&&event.dataTransfer.files.length)onFiles(Array.from(event.dataTransfer.files));}}>
      <span className="catalog-upload-icon"><FileUp/></span><strong>{fa?"فایل‌ها را اینجا اضافه کن":"Add files here"}</strong>
      <p>{fa?"ویدیو، عکس، PDF و فایل‌های دیگر · انتخاب چندتایی":"Videos, photos, PDFs and other files · Multiple selection"}</p>
      <button type="button" className="button primary" disabled={disabled} onClick={()=>input.current?.click()}><Plus/>{fa?"افزودن فایل‌ها":"Add files"}</button>
      <small>{fa?"از گالری یا فایل‌های دستگاه انتخاب کن؛ روی دسکتاپ می‌توانی فایل‌ها را اینجا بکشی.":"Choose from your gallery or device. On desktop, you can also drop files here."}</small>
      <input ref={input} type="file" multiple hidden disabled={disabled} aria-label={fa?"فایل‌های قابل تحویل":"Delivery files"} onChange={event=>{const files=Array.from(event.currentTarget.files??[]);if(files.length)onFiles(files);event.currentTarget.value="";}}/>
    </div></>;
}

export function DeliverySelectedFiles({files,lang,onRemove,onPreview}:{files:File[];lang:Lang;onRemove:(index:number)=>void;onPreview:(media:PreviewMedia)=>void}) {
  return files.length>0&&<ul className="catalog-assets delivery-selected-files">{files.map((file,index)=><SelectedFile key={`${file.name}-${index}`} file={file} index={index} lang={lang} onRemove={onRemove} onPreview={onPreview}/>)}</ul>;
}

function SelectedFile({file,index,lang,onRemove,onPreview}:{file:File;index:number;lang:Lang;onRemove:(index:number)=>void;onPreview:(media:PreviewMedia)=>void}) {
  const kind:PreviewMedia["kind"]=/\.(jpe?g|png|webp|gif)$/i.test(file.name)?"image":/\.(mp4|mov|webm)$/i.test(file.name)?"video":"file";
  const source=useRef(""),image=useRef<HTMLImageElement>(null),video=useRef<HTMLVideoElement>(null);
  useEffect(()=>{if(kind==="file")return;const url=URL.createObjectURL(file);source.current=url;if(image.current)image.current.src=url;if(video.current)video.current.src=url+"#t=0.1";return()=>{source.current="";URL.revokeObjectURL(url);};},[file,kind]);
  return <li><button type="button" className="catalog-asset-preview" disabled={kind==="file"} aria-label={(lang==="fa"?"پیش‌نمایش ":"Preview ")+file.name} onClick={()=>{if(source.current)onPreview({source:source.current,kind,name:file.name});}}>
    {kind==="image"?<img ref={image} alt=""/>:kind==="video"?<><video ref={video} muted playsInline preload="metadata"/><Play className="catalog-video-play"/></>:<FileText/>}
  </button><span><strong dir="auto">{file.name}</strong><small>{(file.size/1048576).toFixed(1)} MB</small></span><button type="button" className="icon-button" aria-label={(lang==="fa"?"حذف ":"Remove ")+file.name} onClick={()=>onRemove(index)}><X/></button></li>;
}
