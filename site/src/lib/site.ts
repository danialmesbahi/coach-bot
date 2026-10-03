import config from "../../sensi.config";

/**
 * Typed access to the site settings. Everything editable lives in `sensi.config.ts`
 * at the root of the site project; this module only derives values from it.
 */
export const site = {
  name: config.brand.name,
  nameLatin: config.brand.nameLatin,
  url: config.brand.url,
  logo: config.brand.logo,
  locale: "fa_IR",
  description: config.seo.description,
  bot: config.bot,
  business: config.business,
  trust: config.trust,
} as const;

export const botUrl = (start?: string) =>
  `https://t.me/${site.bot.username}${start ? `?start=${encodeURIComponent(start)}` : ""}`;

export { config };
export { fa, toman } from "./format";
