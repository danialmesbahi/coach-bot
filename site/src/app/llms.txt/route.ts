import { faqs } from "@/lib/faq";
import { journey } from "@/lib/journey";
import { getCatalog } from "@/lib/catalog";
import { botUrl, site, toman } from "@/lib/site";

export const dynamic = "force-dynamic";

/** Plain-language summary for AI assistants and answer engines (llmstxt.org). */
export async function GET() {
  const { plans } = await getCatalog();
  const body = `# ${site.name} (${site.nameLatin})

> ${site.description}

## What it is
- Online fitness coaching in Persian for people in Iran.
- A real coach writes a personal training plan, nutrition plan, or both, based on the client's age, height, weight, six body measurements (abdomen, waist, arm, thigh, shoulder width, chest), body photos, goal, training history, food allergies and restrictions.
- Everything happens inside the Telegram bot: ${botUrl()}
- Payment is only through the official ZarinPal gateway and is verified server-side.

## Programs (prices in Toman)
${plans.map((p) => `- ${p.title}: ${toman(p.price)} تومان${p.duration ? ` (${p.duration})` : ""}. ${p.description || p.kindLabel}`).join("\n")}

## How it works
${journey.map((s, i) => `${i + 1}. ${s.title}: ${s.body}`).join("\n")}

## FAQ
${faqs.map((f) => `### ${f.q}\n${f.a}`).join("\n\n")}

## Pages
- [About](${site.url}/about)
- [Contact](${site.url}/contact)
- [Terms](${site.url}/terms)
- [Privacy](${site.url}/privacy)
- [Refund policy](${site.url}/refund)
`;
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
