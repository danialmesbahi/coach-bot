import config from "../../sensi.config";

export type Faq = { q: string; a: string };

/** Edited in sensi.config.ts → faq.items */
export const faqs: Faq[] = config.faq.items;
