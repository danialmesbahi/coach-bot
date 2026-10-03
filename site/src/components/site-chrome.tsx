"use client";

import { useEffect, useRef } from "react";

/**
 * Page-wide interaction glue, kept in one small listener set:
 * scroll progress bar, header state, cursor spotlights on [data-spot] and magnetic [data-magnet] buttons.
 */
export default function SiteChrome() {
  const bar = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const progress = bar.current;
    const header = document.querySelector<HTMLElement>(".site-header");
    let raf = 0;
    let scrolled = false;
    const update = () => {
      raf = 0;
      const y = window.scrollY;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (progress) progress.style.transform = `scaleX(${max > 0 ? Math.min(1, y / max) : 0})`;
      const s = y > 24;
      if (s !== scrolled && header) { scrolled = s; header.classList.toggle("is-scrolled", s); }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);

    const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let magnet: HTMLElement | null = null;
    const onMove = (e: PointerEvent) => {
      const t = e.target as Element | null;
      const spot = t?.closest<HTMLElement>("[data-spot]");
      if (spot) {
        const r = spot.getBoundingClientRect();
        spot.style.setProperty("--mx", `${e.clientX - r.left}px`);
        spot.style.setProperty("--my", `${e.clientY - r.top}px`);
      }
      if (reduce) return;
      const m = t?.closest<HTMLElement>("[data-magnet]") ?? null;
      if (magnet && magnet !== m) { magnet.style.transform = ""; }
      magnet = m;
      if (m) {
        const r = m.getBoundingClientRect();
        const dx = (e.clientX - (r.left + r.width / 2)) / r.width;
        const dy = (e.clientY - (r.top + r.height / 2)) / r.height;
        m.style.transform = `translate(${(dx * 10).toFixed(1)}px, ${(dy * 8).toFixed(1)}px)`;
      }
    };
    if (fine) document.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      document.removeEventListener("pointermove", onMove);
    };
  }, []);

  return (
    <div className="progress" aria-hidden="true">
      <div ref={bar} />
    </div>
  );
}
