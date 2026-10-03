"use client";

import { useEffect, useRef, useState } from "react";
import { journey } from "@/lib/journey";
import { fa } from "@/lib/format";
import { centerInRow } from "@/lib/center-chip";
import PhoneChat, { renderItem } from "./phone-chat";

/** Desktop: scrollytelling where each step of the purchase journey plays its real bot conversation. */
function PathDesktop() {
  const [active, setActive] = useState(0);
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const items = Array.from(list.current?.querySelectorAll<HTMLElement>("[data-step]") ?? []);
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.step));
        }
      },
      { rootMargin: "-42% 0px -42% 0px" },
    );
    items.forEach((item) => io.observe(item));
    return () => io.disconnect();
  }, []);

  return (
    <div className="path">
      <ol className="path__steps" ref={list}>
        {journey.map((s, i) => (
          <li key={s.id} data-step={i} className={`path-step${i === active ? " is-active" : ""}`}>
            <span className="path-step__num">{fa(i + 1)}</span>
            <div className="path-step__text">
              <h3>{s.title}</h3>
              <p>{s.body}</p>
              {s.note && <p className="path-step__note">{s.note}</p>}
            </div>
          </li>
        ))}
      </ol>
      <div className="path__stage">
        <div className="path__sticky">
          <div className="path__rail" aria-hidden="true">
            {journey.map((s, i) => <span key={s.id} className={i <= active ? "is-done" : undefined} />)}
          </div>
          <PhoneChat steps={journey.slice(0, active + 1)} />
        </div>
      </div>
    </div>
  );
}

/**
 * Phones: one card per step in a native swipe row (scroll-snap, so it is smooth on any device).
 * Each card holds the step's text and the real bot messages for it; the bar on top shows progress and jumps.
 */
function PathMobile() {
  const [active, setActive] = useState(0);
  const track = useRef<HTMLDivElement>(null);
  const last = journey.length - 1;

  // the active step is the card closest to the middle of the row
  useEffect(() => {
    const row = track.current;
    if (!row) return;
    let raf = 0;
    const measure = () => {
      raf = 0;
      const mid = row.getBoundingClientRect().left + row.clientWidth / 2;
      let best = 0;
      let dist = Infinity;
      row.querySelectorAll<HTMLElement>("[data-i]").forEach((el, i) => {
        const r = el.getBoundingClientRect();
        const d = Math.abs(r.left + r.width / 2 - mid);
        if (d < dist) { dist = d; best = i; }
      });
      setActive(best);
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(measure); };
    row.addEventListener("scroll", onScroll, { passive: true });
    return () => { row.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, []);

  const go = (i: number) => centerInRow(track.current, `[data-i="${Math.max(0, Math.min(last, i))}"]`);

  return (
    <div className="pathm">
      <div className="pathm__bar">
        <button type="button" className="pathm__arrow" onClick={() => go(active - 1)} disabled={active === 0} aria-label="مرحله قبل">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
        </button>
        <div className="pathm__segs" role="tablist" aria-label="مرحله‌های خرید">
          {journey.map((s, i) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={i === active}
              aria-label={`مرحله ${fa(i + 1)}: ${s.title}`}
              className={i < active ? "is-done" : undefined}
              onClick={() => go(i)}
            />
          ))}
        </div>
        <span className="pathm__count">{fa(active + 1)} از {fa(journey.length)}</span>
        <button type="button" className="pathm__arrow" onClick={() => go(active + 1)} disabled={active === last} aria-label="مرحله بعد">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
        </button>
      </div>

      <div className="pathm__track" ref={track}>
        {journey.map((s, i) => {
          const picks = s.preview ?? [s.chat.length - 2, s.chat.length - 1].filter((n) => n >= 0);
          return (
            <article key={s.id} data-i={i} className={`pathm__slide${i === active ? " is-active" : ""}`} aria-label={`مرحله ${fa(i + 1)}`}>
              <div className="pathm__head">
                <span className="pathm__num">{fa(i + 1)}</span>
                <h3>{s.title}</h3>
              </div>
              <p className="pathm__body">{s.body}</p>
              <div className="tg-mini" aria-hidden="true">
                <div className="tg-mini__chat">
                  {picks.map((n, k) => renderItem(s.chat[n], `${s.id}-m${n}`, { typing: null, at: 0 }, 2 + i * 3 + k, true))}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

/** Both layouts are rendered; CSS shows the one that fits the screen, so there is no layout jump on load. */
export default function PathStory() {
  return (
    <>
      <div className="path-desktop"><PathDesktop /></div>
      <div className="path-mobile"><PathMobile /></div>
    </>
  );
}
