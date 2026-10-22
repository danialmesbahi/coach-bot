import { config } from "./site";

/**
 * Live storefront from the panel's product catalog (GET /api/public/catalog on the web API).
 * Read on every render (host nginx caches the page for 60 s); if the API is unreachable the defaults in site.ts are shown.
 */

export type PlanKind = "manual" | "content" | "channel";
export type Visual = "training" | "nutrition" | "combined" | "content" | "channel";

export type Plan = {
  id: number | null;
  title: string;
  description: string;
  price: number;
  duration: string;
  kind: PlanKind;
  kindLabel: string;
  sends: string[];
  visual: Visual;
  featured: boolean;
};

type ApiItem = {
  id: number;
  title: string;
  description: string;
  price_toman: number;
  duration_days: number;
  duration_unit: string;
  delivery_mode: PlanKind;
  form_fields: string[];
};

const FIELD_LABELS: Record<string, string> = {
  age: "سن",
  gender: "جنسیت",
  height: "قد",
  weight: "وزن امروز",
  measurements: "اندازه‌های بدن",
  allergy: "حساسیت غذایی",
  restriction: "محدودیت غذایی",
  supplements: "مکمل‌های مصرفی",
  goal: "هدف",
  training_history: "سابقه تمرین",
  notes: "توضیحات برای مربی",
  body_photo: "عکس بدن",
};

const KIND_LABELS: Record<PlanKind, string> = {
  manual: "برنامه اختصاصی",
  content: "محتوای آماده",
  channel: "کانال خصوصی",
};

const fa = (n: number) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);

function durationLabel(days: number, unit: string) {
  if (unit === "lifetime") return "دسترسی همیشگی";
  if (unit === "once") return "تحویل یک‌باره";
  if (unit === "years") return `${fa(Math.round(days / 365))} ساله`;
  if (unit === "months") return `${fa(Math.round(days / 30))} ماهه`;
  if (unit === "weeks") return `${fa(Math.round(days / 7))} هفته‌ای`;
  return `${fa(days)} روزه`;
}

function visualFor(title: string, kind: PlanKind): Visual {
  if (kind === "channel") return "channel";
  const food = /غذا|تغذیه|رژیم|nutrition|diet/i.test(title);
  const train = /تمرین|بدنساز|ورزش|training|workout/i.test(title);
  if (food && train) return "combined";
  if (food) return "nutrition";
  if (train) return "training";
  return kind === "content" ? "content" : "combined";
}

function withFeatured(plans: Plan[]) {
  const custom = plans.filter((p) => p.kind === "manual");
  const pool = custom.length ? custom : plans;
  const top = pool.reduce<Plan | null>((best, p) => (!best || p.price > best.price ? p : best), null);
  return plans.map((p) => ({ ...p, featured: plans.length > 1 && p === top }));
}

function fallback(): Plan[] {
  return withFeatured(
    config.programs.fallback.map((p) => ({
      id: null,
      title: p.name,
      description: p.summary,
      price: p.price,
      duration: "",
      kind: "manual" as const,
      kindLabel: KIND_LABELS.manual,
      sends: p.sends,
      visual: p.visual as Visual,
      featured: false,
    })),
  );
}

export async function getCatalog(): Promise<{ plans: Plan[]; salesOpen: boolean; live: boolean }> {
  const url = process.env.CATALOG_API_URL?.trim();
  if (!url) return { plans: fallback(), salesOpen: true, live: false };
  try {
    const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error(`catalog ${res.status}`);
    const body = (await res.json()) as { items: ApiItem[]; sales_open: boolean };
    if (!Array.isArray(body.items) || !body.items.length) return { plans: fallback(), salesOpen: body.sales_open !== false, live: false };
    const plans = body.items.map((item) => ({
      id: item.id,
      title: item.title,
      description: item.description,
      price: item.price_toman,
      duration: durationLabel(item.duration_days, item.duration_unit),
      kind: item.delivery_mode,
      kindLabel: KIND_LABELS[item.delivery_mode] ?? KIND_LABELS.manual,
      sends: item.form_fields.map((f) => FIELD_LABELS[f]).filter(Boolean),
      visual: visualFor(item.title, item.delivery_mode),
      featured: false,
    }));
    return { plans: withFeatured(plans), salesOpen: body.sales_open !== false, live: true };
  } catch {
    return { plans: fallback(), salesOpen: true, live: false };
  }
}
