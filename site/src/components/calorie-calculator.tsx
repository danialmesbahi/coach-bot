"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type config from "../../sensi.config";

type Sex = "male" | "female";
type Goal = "cut" | "keep" | "gain";

const ACTIVITY = [
  { factor: 1.2, label: "کم‌تحرک", hint: "کار پشت میز، بدون تمرین" },
  { factor: 1.375, label: "سبک", hint: "۱ تا ۳ جلسه در هفته" },
  { factor: 1.55, label: "متوسط", hint: "۳ تا ۵ جلسه در هفته" },
  { factor: 1.725, label: "زیاد", hint: "۶ تا ۷ جلسه در هفته" },
  { factor: 1.9, label: "خیلی زیاد", hint: "تمرین سنگین یا کار بدنی" },
];

const GOALS: { id: Goal; label: string; adjust: number; protein: number }[] = [
  { id: "cut", label: "کاهش چربی", adjust: -0.2, protein: 2.2 },
  { id: "keep", label: "حفظ وزن", adjust: 0, protein: 1.8 },
  { id: "gain", label: "عضله‌سازی", adjust: 0.1, protein: 2 },
];

const fa = (n: number) => Math.round(n).toLocaleString("fa-IR");

/** Animates a number toward its target so result changes feel physical. */
function useTween(target: number) {
  const [value, setValue] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 600;
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const step = (now: number) => {
      const t = duration ? Math.min(1, (now - start) / duration) : 1;
      const e = 1 - Math.pow(1 - t, 3);
      const v = a + (target - a) * e;
      from.current = v;
      setValue(v);
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return value;
}

function Slider({ id, label, unit, min, max, value, onChange }: { id: string; label: string; unit: string; min: number; max: number; value: number; onChange: (v: number) => void }) {
  return (
    <div className="calc__field">
      <label htmlFor={id}>
        {label}
        <output htmlFor={id}><b>{fa(value)}</b> {unit}</output>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ ["--fill" as string]: `${((value - min) / (max - min)) * 100}%` }}
      />
    </div>
  );
}

export default function CalorieCalculator({ botHref, content }: { botHref: string; content: (typeof config)["calculator"] }) {
  const [sex, setSex] = useState<Sex>("male");
  const [age, setAge] = useState(28);
  const [height, setHeight] = useState(176);
  const [weight, setWeight] = useState(78);
  const [activity, setActivity] = useState(2);
  const [goal, setGoal] = useState<Goal>("keep");

  const result = useMemo(() => {
    // Mifflin–St Jeor resting energy, multiplied by activity level.
    const bmr = 10 * weight + 6.25 * height - 5 * age + (sex === "male" ? 5 : -161);
    const tdee = bmr * ACTIVITY[activity].factor;
    const g = GOALS.find((x) => x.id === goal)!;
    const kcal = tdee * (1 + g.adjust);
    const protein = weight * g.protein;
    const fat = (kcal * 0.25) / 9;
    const carbs = Math.max(0, (kcal - protein * 4 - fat * 9) / 4);
    const bmi = weight / (height / 100) ** 2;
    return { bmr, tdee, kcal, protein, fat, carbs, bmi };
  }, [sex, age, height, weight, activity, goal]);

  const kcal = useTween(result.kcal);
  const out = useRef<HTMLDivElement>(null);
  const [outVisible, setOutVisible] = useState(false);

  // The sticky live bar (phones) steps aside once the full result card is on screen.
  useEffect(() => {
    const el = out.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setOutVisible(entry.isIntersecting), { rootMargin: "0px 0px -35% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const bmiLabel = result.bmi < 18.5 ? "کمتر از حد طبیعی" : result.bmi < 25 ? "طبیعی" : result.bmi < 30 ? "اضافه‌وزن" : "چاقی";
  const macroTotal = result.protein * 4 + result.carbs * 4 + result.fat * 9 || 1;
  const macros = [
    { label: "پروتئین", grams: result.protein, share: (result.protein * 4) / macroTotal, cls: "is-protein" },
    { label: "کربوهیدرات", grams: result.carbs, share: (result.carbs * 4) / macroTotal, cls: "is-carbs" },
    { label: "چربی", grams: result.fat, share: (result.fat * 9) / macroTotal, cls: "is-fat" },
  ];

  return (
    <div className={`calc${outVisible ? " is-out-visible" : ""}`}>
      <div className="calc__live" aria-hidden="true">
        <span className="calc__live-kcal"><b>{fa(kcal)}</b> کالری</span>
        <span className="calc__live-macros">
          <span className="is-protein"><i />{fa(result.protein)}</span>
          <span className="is-carbs"><i />{fa(result.carbs)}</span>
          <span className="is-fat"><i />{fa(result.fat)}</span>
          <small>گرم</small>
        </span>
      </div>
      <form className="calc__form" onSubmit={(e) => e.preventDefault()} aria-label="مشخصات تو">
        <div className="calc__row">
          <div className="seg" role="radiogroup" aria-label="جنسیت">
            {(["male", "female"] as Sex[]).map((s) => (
              <button key={s} type="button" role="radio" aria-checked={sex === s} onClick={() => setSex(s)}>
                {s === "male" ? "آقا" : "خانم"}
              </button>
            ))}
          </div>
          <div className="seg" role="radiogroup" aria-label="هدف">
            {GOALS.map((g) => (
              <button key={g.id} type="button" role="radio" aria-checked={goal === g.id} onClick={() => setGoal(g.id)}>
                {g.label}
              </button>
            ))}
          </div>
        </div>
        <Slider id="calc-age" label="سن" unit="سال" min={15} max={75} value={age} onChange={setAge} />
        <Slider id="calc-height" label="قد" unit="سانتی‌متر" min={140} max={210} value={height} onChange={setHeight} />
        <Slider id="calc-weight" label="وزن" unit="کیلوگرم" min={40} max={160} value={weight} onChange={setWeight} />
        <fieldset className="calc__activity">
          <legend>میزان فعالیت</legend>
          <div className="calc__levels">
            {ACTIVITY.map((a, i) => (
              <button key={a.label} type="button" aria-pressed={activity === i} onClick={() => setActivity(i)}>
                <b>{a.label}</b>
                <small>{a.hint}</small>
              </button>
            ))}
          </div>
        </fieldset>
      </form>

      <div className="calc__out" aria-live="polite" ref={out}>
        <p className="calc__label">{content.resultLabel}</p>
        <p className="calc__kcal"><b>{fa(kcal)}</b><span>کالری</span></p>
        <div className="calc__bar" aria-hidden="true">
          {macros.map((m) => <span key={m.label} className={m.cls} style={{ flexGrow: m.share }} />)}
        </div>
        <ul className="calc__macros">
          {macros.map((m) => (
            <li key={m.label} className={m.cls}>
              <i aria-hidden="true" />
              <span>{m.label}</span>
              <b>{fa(m.grams)} گرم</b>
            </li>
          ))}
        </ul>
        <dl className="calc__facts">
          <div><dt>متابولیسم پایه</dt><dd>{fa(result.bmr)} کالری</dd></div>
          <div><dt>کالری نگه‌دارنده</dt><dd>{fa(result.tdee)} کالری</dd></div>
          <div><dt>شاخص توده بدنی</dt><dd>{result.bmi.toLocaleString("fa-IR", { maximumFractionDigits: 1 })} ({bmiLabel})</dd></div>
        </dl>
        <p className="calc__note">{content.note}</p>
        <a className="btn btn--ember btn--large calc__cta" data-magnet href={botHref} target="_blank" rel="noopener">{content.cta}</a>
      </div>
    </div>
  );
}
