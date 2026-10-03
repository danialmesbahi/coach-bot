"use client";

import Image, { type StaticImageData } from "next/image";
import { useEffect, useRef, useState } from "react";
import front from "@/assets/anatomy.jpg";
import back from "@/assets/anatomy-back.jpg";
import { centerInRow } from "@/lib/center-chip";
import type config from "../../sensi.config";

type Content = (typeof config)["muscles"];
type View = "front" | "back";

// Hotspot positions (x, y in %) and texts live in sensi.config.ts → muscles.
export default function MuscleMap({ content }: { content: Content }) {
  const VIEWS: Record<View, { label: string; image: StaticImageData; muscles: Content["front"] }> = {
    front: { label: content.frontLabel, image: front, muscles: content.front },
    back: { label: content.backLabel, image: back, muscles: content.back },
  };
  const [view, setView] = useState<View>("front");
  const [active, setActive] = useState("chest");
  const list = useRef<HTMLUListElement>(null);

  // keep the selected muscle chip visible in the scrollable row on phones
  useEffect(() => {
    centerInRow(list.current, '[aria-pressed="true"]');
  }, [active, view]);
  const current = VIEWS[view];
  const muscle = current.muscles.find((m) => m.id === active) ?? current.muscles[0];

  const switchView = (next: View) => {
    setView(next);
    setActive((VIEWS[next].muscles[1] ?? VIEWS[next].muscles[0]).id);
  };

  return (
    <div className="mmap">
      <div className="mmap__figure">
        <div className="mmap__toggle" role="group" aria-label="نمای بدن">
          {(Object.keys(VIEWS) as View[]).map((k) => (
            <button key={k} type="button" aria-pressed={view === k} onClick={() => switchView(k)}>
              {VIEWS[k].label}
            </button>
          ))}
        </div>
        <div className="mmap__stage" key={view}>
          <Image src={current.image} alt={`مدل سه‌بعدی بدن ورزشکار از ${current.label}`} sizes="(max-width: 960px) 80vw, 420px" placeholder="blur" className="mmap__img" />
          {current.muscles.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`mmap__dot${m.id === muscle.id ? " is-active" : ""}`}
              style={{ left: `${m.x}%`, top: `${m.y}%` }}
              onClick={() => setActive(m.id)}
              onPointerEnter={(e) => { if (e.pointerType === "mouse") setActive(m.id); }}
              aria-label={m.name}
              aria-pressed={m.id === muscle.id}
            >
              <span />
            </button>
          ))}
        </div>
      </div>
      <div className="mmap__info" aria-live="polite">
        <ul className="mmap__list" ref={list}>
          {current.muscles.map((m) => (
            <li key={m.id}>
              <button type="button" aria-pressed={m.id === muscle.id} onClick={() => setActive(m.id)}>{m.name}</button>
            </li>
          ))}
        </ul>
        <div className="mmap__card" key={muscle.id}>
          <h3>{muscle.name}</h3>
          <p>{muscle.note}</p>
          <h4>{content.movesTitle}</h4>
          <ol>{muscle.moves.map((x) => <li key={x}>{x}</li>)}</ol>
        </div>
      </div>
    </div>
  );
}
