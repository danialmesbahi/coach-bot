"use client";

import { useEffect, useRef } from "react";

/** Chalk dust: fixed positions so server and client markup match; each mote is a CSS transform animation. */
const MOTES = [
  [8, 62, 0, 11], [14, 80, 3.2, 13], [19, 48, 6.1, 10], [24, 72, 1.4, 14], [29, 90, 8.3, 12],
  [33, 56, 4.7, 11], [38, 84, 2.2, 15], [43, 66, 7.4, 12], [47, 92, 5.3, 13], [52, 52, 0.9, 10],
  [56, 78, 9.1, 14], [11, 96, 10.2, 12], [27, 60, 11.6, 11], [41, 74, 12.8, 13],
] as const;

/**
 * Hero light: a warm spotlight that follows the cursor on desktop and drifts by itself on touch screens.
 * Everything moves with transforms only (no repaint per frame), and the pointer loop sleeps once the light settles.
 */
export default function HeroLight() {
  const spot = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const light = spot.current;
    const hero = light?.closest<HTMLElement>(".hero");
    const media = hero?.querySelector<HTMLElement>(".hero__media");
    if (!light || !hero || !media) return;
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    if (!fine || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    hero.classList.add("is-pointer");
    const home = { x: 0.3, y: 0.42 };
    const target = { ...home };
    const pos = { ...home };
    let raf = 0;

    const frame = () => {
      pos.x += (target.x - pos.x) * 0.12;
      pos.y += (target.y - pos.y) * 0.12;
      const box = hero.getBoundingClientRect();
      light.style.transform = `translate3d(${((pos.x - home.x) * box.width).toFixed(1)}px, ${((pos.y - home.y) * box.height).toFixed(1)}px, 0)`;
      media.style.transform = `translate3d(${((pos.x - 0.5) * -28).toFixed(2)}px, ${((pos.y - 0.5) * -20).toFixed(2)}px, 0) scale(1.02)`;
      const settled = Math.abs(target.x - pos.x) < 0.001 && Math.abs(target.y - pos.y) < 0.001;
      raf = settled ? 0 : requestAnimationFrame(frame);
    };

    const onMove = (e: PointerEvent) => {
      const box = hero.getBoundingClientRect();
      if (e.clientY < box.top || e.clientY > box.bottom) return;
      target.x = (e.clientX - box.left) / box.width;
      target.y = (e.clientY - box.top) / box.height;
      if (!raf) raf = requestAnimationFrame(frame);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      hero.classList.remove("is-pointer");
    };
  }, []);

  return (
    <>
      <div ref={spot} className="hero__spot" aria-hidden="true" />
      <div className="hero__dust" aria-hidden="true">
        {MOTES.map(([x, y, delay, dur], i) => (
          <i key={i} style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${-delay}s`, animationDuration: `${dur}s` }} />
        ))}
      </div>
    </>
  );
}
