"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import coachImg from "@/assets/coach.jpg";
import nutritionImg from "@/assets/nutrition.jpg";
import trainImg from "@/assets/train-woman.jpg";
import { centerInRow } from "@/lib/center-chip";
import type config from "../../sensi.config";

type Content = (typeof config)["services"];
const faNum = (n: number) => n.toLocaleString("fa-IR");

/* ---------- samples: small, honest previews of what a client receives (texts in sensi.config.ts) ---------- */

function SessionSample({ sample }: { sample: Content["training"]["sample"] }) {
  const [done, setDone] = useState<number[]>([0]);
  const toggle = (i: number) => setDone((d) => (d.includes(i) ? d.filter((x) => x !== i) : [...d, i]));
  return (
    <div className="sample">
      <p className="sample__tag">{sample.tag}</p>
      <h4>{sample.title}</h4>
      <ul className="session">
        {sample.moves.map((s, i) => (
          <li key={s.move}>
            <button type="button" aria-pressed={done.includes(i)} onClick={() => toggle(i)}>
              <span className="session__check" aria-hidden="true" />
              <span className="session__move">{s.move}</span>
              <span className="session__sets">{s.sets}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="sample__foot">
        <span>{`${faNum(done.length)} از ${faNum(sample.moves.length)} حرکت`}</span>
        <span>{sample.rest}</span>
      </p>
      <div className="session__bar" aria-hidden="true"><span style={{ transform: `scaleX(${done.length / sample.moves.length})` }} /></div>
    </div>
  );
}

function NutritionSample({ sample }: { sample: Content["nutrition"]["sample"] }) {
  const [hover, setHover] = useState<string | null>(null);
  const macros = [
    { key: "protein", label: "پروتئین", grams: sample.macros.protein, kcal: 4, color: "var(--ember)" },
    { key: "carbs", label: "کربوهیدرات", grams: sample.macros.carbs, kcal: 4, color: "var(--bone)" },
    { key: "fat", label: "چربی", grams: sample.macros.fat, kcal: 9, color: "var(--ash)" },
  ];
  const total = macros.reduce((sum, m) => sum + m.grams * m.kcal, 0) || 1;
  const r = 52;
  const c = 2 * Math.PI * r;
  const arcs = macros.map((m, i) => ({
    ...m,
    len: ((m.grams * m.kcal) / total) * c,
    start: macros.slice(0, i).reduce((sum, x) => sum + ((x.grams * x.kcal) / total) * c, 0),
  }));
  return (
    <div className="sample">
      <p className="sample__tag">{sample.tag}</p>
      <div className="macro">
        <svg viewBox="0 0 140 140" className="macro__ring" aria-hidden="true">
          <circle cx="70" cy="70" r={r} className="macro__track" />
          {arcs.map((m) => (
            <circle
              key={m.key}
              cx="70"
              cy="70"
              r={r}
              className={`macro__arc${hover && hover !== m.key ? " is-dim" : ""}`}
              stroke={m.color}
              strokeDasharray={`${Math.max(0, m.len - 4)} ${c}`}
              strokeDashoffset={-m.start}
              onPointerEnter={() => setHover(m.key)}
              onPointerLeave={() => setHover(null)}
            />
          ))}
        </svg>
        <div className="macro__center">
          <b>{faNum(total)}</b>
          <small>کالری</small>
        </div>
        <ul className="macro__legend">
          {macros.map((m) => (
            <li key={m.key} onPointerEnter={() => setHover(m.key)} onPointerLeave={() => setHover(null)} className={hover && hover !== m.key ? "is-dim" : undefined}>
              <i style={{ background: m.color }} />
              <span>{m.label}</span>
              <b>{faNum(m.grams)} گرم</b>
            </li>
          ))}
        </ul>
      </div>
      <ul className="meals">
        {sample.meals.map((meal) => <li key={meal.name}><span>{meal.name}</span>{meal.text}</li>)}
      </ul>
    </div>
  );
}

function CoachSample({ sample }: { sample: Content["coaching"]["sample"] }) {
  return (
    <div className="sample">
      <p className="sample__tag">{sample.tag}</p>
      <div className="minichat">
        <p className="minichat__msg minichat__msg--me">{sample.question}</p>
        <p className="minichat__msg">
          <b>{sample.answerTitle}</b>
          {sample.answer}
        </p>
        <p className="minichat__msg minichat__msg--me">{sample.thanks}</p>
      </div>
      <ul className="coach-steps">
        {sample.steps.map((step) => <li key={step.title}><b>{step.title}</b> {step.text}</li>)}
      </ul>
    </div>
  );
}

const MEDIA = {
  training: { image: trainImg, alt: "ورزشکار زن با پوشش ورزشی در حال تمرین با کتل‌بل", position: "50% 20%" },
  nutrition: { image: nutritionImg, alt: "ظرف‌های غذای سالم ورزشی با مرغ، برنج، بروکلی و تخم‌مرغ", position: "50% 60%" },
  coaching: { image: coachImg, alt: "مربی در حال اصلاح فرم اسکات ورزشکار", position: "60% 30%" },
} as const;

type Id = keyof typeof MEDIA;

/**
 * App-style services showcase: tabs switch between training, nutrition and coaching.
 * The photo, the description and an interactive sample of each service stay together on screen;
 * on touch screens the stage can also be swiped.
 */
export default function ServiceShowcase({ content }: { content: Content }) {
  const ids: Id[] = ["training", "nutrition", "coaching"];
  const [active, setActive] = useState<Id>("training");
  const [dir, setDir] = useState(1);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const tabs = useRef<HTMLDivElement>(null);
  const index = ids.indexOf(active);
  const item = content[active];
  const media = MEDIA[active];

  const go = (next: number) => {
    const i = (next + ids.length) % ids.length;
    setDir(i > index ? 1 : -1);
    setActive(ids[i]);
  };

  // keep the active tab centred when the tab bar scrolls on narrow screens
  useEffect(() => {
    centerInRow(tabs.current, '[aria-selected="true"]');
  }, [active]);

  const sample =
    active === "training" ? <SessionSample sample={content.training.sample} /> :
    active === "nutrition" ? <NutritionSample sample={content.nutrition.sample} /> :
    <CoachSample sample={content.coaching.sample} />;

  return (
    <div className="show" style={{ ["--tab" as string]: index }}>
      <div className="show__tabs" role="tablist" aria-label="خدمات" ref={tabs}>
        <span className="show__indicator" aria-hidden="true" />
        {ids.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`show-tab-${id}`}
            aria-selected={id === active}
            aria-controls="show-panel"
            onClick={() => go(ids.indexOf(id))}
          >
            {content[id].title}
          </button>
        ))}
      </div>

      <div
        className="show__stage"
        id="show-panel"
        role="tabpanel"
        aria-labelledby={`show-tab-${active}`}
        onTouchStart={(e) => { touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }; }}
        onTouchEnd={(e) => {
          const start = touch.current;
          touch.current = null;
          if (!start) return;
          const dx = e.changedTouches[0].clientX - start.x;
          const dy = e.changedTouches[0].clientY - start.y;
          // RTL: swiping right moves forward
          if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) go(index + (dx > 0 ? 1 : -1));
        }}
      >
        <div className="show__visual" key={`v-${active}`} data-dir={dir}>
          <Image src={media.image} alt={media.alt} fill sizes="(max-width: 960px) 100vw, 55vw" placeholder="blur" style={{ objectPosition: media.position }} />
          <div className="show__copy">
            <h3>{item.title}</h3>
            <p>{item.lead}</p>
            <ul>{item.points.map((pt) => <li key={pt}>{pt}</li>)}</ul>
          </div>
          <div className="show__dots" aria-hidden="true">
            {ids.map((id) => <span key={id} className={id === active ? "is-on" : undefined} />)}
          </div>
        </div>
        <div className="show__sample" key={`s-${active}`} data-dir={dir}>
          {sample}
        </div>
      </div>
    </div>
  );
}
