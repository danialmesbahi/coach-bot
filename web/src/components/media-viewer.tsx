"use client";
/* eslint-disable @next/next/no-img-element -- Authenticated and local media streams. */
import { useEffect, useRef, useState, TouchEvent as ReactTouchEvent } from "react";
import { Download, FileText, RotateCcw, X, ZoomIn, ZoomOut } from "lucide-react";
import type { Lang } from "@/lib/types";
import { reportClientIssue } from "@/lib/api";

export type PreviewMedia = { source: string; kind: "image" | "video" | "audio" | "pdf" | "file"; name?: string };

export function MediaViewer({ media, lang, onClose }: { media: PreviewMedia; lang: Lang; onClose: () => void }) {
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
  const download = media.source.startsWith("blob:") ? media.source : `${media.source}${media.source.includes("?") ? "&" : "?"}download=1`;
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
    <div className={`media-viewer__stage${media.kind === "image" ? " media-viewer__stage--image" : ""}`} onTouchStart={startGesture} onTouchMove={moveGesture} onTouchEnd={endGesture} onTouchCancel={endGesture}>{media.kind === "image" ? <img className={pinching || panning ? "is-gesturing" : undefined} src={media.source} alt={label} style={{ transform:`translate3d(${position.x}px,${position.y}px,0) scale(${zoom}) rotate(${rotation}deg)` }}/> : media.kind === "video" ? <video src={media.source} controls autoPlay playsInline onError={()=>reportClientIssue("MediaError")}/> : media.kind === "audio" ? <audio src={media.source} controls autoPlay onError={()=>reportClientIssue("MediaError")}/> : media.kind === "pdf" ? <iframe src={media.source} title={label}/> : <div className="media-viewer__file"><FileText/><strong>{label}</strong><a className="button primary" href={download} download><Download/>{lang === "fa" ? "دانلود امن فایل" : "Download file"}</a></div>}</div>
  </div>;
}
