"use client";

import { useEffect, useRef } from "react";
import { afterLoad } from "@/lib/after-load";
import { fa } from "@/lib/format";

/**
 * Hero heart-rate monitor: resting at 64 bpm and rising with scroll speed.
 * The ECG strip is a static SVG moved by a compositor (WAAPI transform) animation,
 * so it costs no main-thread work per frame; scroll only nudges its playback rate a few times a second.
 */
const REST = 64;
const MAX = 176;
const BEAT = 150; // px per beat on the strip
const TILES = 14; // enough beats to cover the widest screens
const PERIOD = 60_000 / REST; // ms per beat at rest

/** One ECG beat, phase 0..1 → amplitude roughly -0.35..1. */
function wave(p: number) {
  const bump = (c: number, w: number, a: number) => a * Math.exp(-((p - c) ** 2) / (2 * w * w));
  return bump(0.12, 0.025, 0.12) + bump(0.29, 0.008, -0.16) + bump(0.31, 0.009, 1) + bump(0.335, 0.01, -0.34) + bump(0.56, 0.045, 0.24);
}

const PATH = (() => {
  const out: string[] = [];
  for (let x = 0; x <= BEAT * TILES; x++) {
    const y = 60 - wave((x % BEAT) / BEAT) * 46;
    out.push(`${x ? "L" : "M"}${x} ${y.toFixed(1)}`);
  }
  return out.join("");
})();

export default function PulseLine() {
  const strip = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = strip.current;
    const out = readout.current;
    if (!el || !out || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let move: Animation | null = null;
    let beat: Animation | null = null;
    let bpm = REST;
    let shown = REST;
    let lastY = window.scrollY;
    let lastT = performance.now();
    let timer = 0;
    let visible = true;

    const tick = () => {
      const now = performance.now();
      const dt = Math.max(0.05, (now - lastT) / 1000);
      const y = window.scrollY;
      const speed = Math.abs(y - lastY) / dt;
      lastY = y;
      lastT = now;
      const goal = Math.min(MAX, REST + speed * 0.045);
      // climbs quickly, recovers slowly, like a real heart
      bpm += (goal - bpm) * Math.min(1, goal > bpm ? dt * 2.2 : dt * 0.35);
      if (goal === REST && bpm - REST < 0.5) {
        bpm = REST;
        window.clearInterval(timer);
        timer = 0;
      }
      const rate = bpm / REST;
      move?.updatePlaybackRate(rate);
      beat?.updatePlaybackRate(rate);
      const rounded = Math.round(bpm);
      if (rounded !== shown) { shown = rounded; out.textContent = fa(rounded); }
    };

    const wake = () => {
      // the scroll that woke us counts as one interval of movement from where the page last rested
      if (!timer && visible) { lastT = performance.now() - 160; timer = window.setInterval(tick, 160); }
    };

    const stopWaiting = afterLoad(() => {
      move = el.animate([{ transform: "translate3d(0,0,0)" }, { transform: `translate3d(${-BEAT}px,0,0)` }], { duration: PERIOD, iterations: Infinity, easing: "linear" });
      beat = out.animate(
        [{ transform: "scale(1)" }, { transform: "scale(1.12)", offset: 0.15 }, { transform: "scale(1)", offset: 0.4 }, { transform: "scale(1)" }],
        { duration: PERIOD, iterations: Infinity, easing: "ease-out" },
      );
      window.addEventListener("scroll", wake, { passive: true });
    });

    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      lastY = window.scrollY;
      if (visible) { move?.play(); beat?.play(); } else { move?.pause(); beat?.pause(); }
    });
    io.observe(el);

    return () => {
      stopWaiting();
      io.disconnect();
      window.clearInterval(timer);
      window.removeEventListener("scroll", wake);
      move?.cancel();
      beat?.cancel();
    };
  }, []);

  return (
    <div className="pulse" aria-hidden="true">
      <span ref={readout} className="pulse__bpm">{fa(REST)}</span>
      <div className="pulse__trace">
        <div ref={strip} className="pulse__strip">
          <svg width={BEAT * TILES} height="96" viewBox={`0 0 ${BEAT * TILES} 100`} preserveAspectRatio="none">
            <path d={PATH} />
          </svg>
        </div>
      </div>
    </div>
  );
}
