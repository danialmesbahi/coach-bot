import type { Lang } from "@/lib/types";

export function passwordPolicyError(password: string, lang: Lang): string {
  const fa = lang === "fa";
  if (password.length < 8) return fa ? "رمز عبور باید حداقل ۸ نویسه باشد." : "Password must be at least 8 characters.";
  if (password.length > 128) return fa ? "رمز عبور نباید بیشتر از ۱۲۸ نویسه باشد." : "Password must not exceed 128 characters.";
  if (!/[A-Z]/.test(password)) return fa ? "حداقل یک حرف بزرگ انگلیسی وارد کن." : "Add at least one uppercase English letter.";
  if (!/[0-9]/.test(password)) return fa ? "حداقل یک عدد وارد کن." : "Add at least one number.";
  if (!/[^\w\s]/.test(password)) return fa ? "حداقل یک نماد مثل ! وارد کن." : "Add at least one symbol such as !.";
  return "";
}
