const faDigits = "۰۱۲۳۴۵۶۷۸۹";

/** Persian digits for display. */
export const fa = (value: number | string) => String(value).replace(/\d/g, (d) => faDigits[Number(d)]);

/** Toman amount with Persian digits and the Persian thousands separator. */
export const toman = (value: number) => fa(value.toLocaleString("en-US").replace(/,/g, "٬"));
