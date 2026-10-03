import type { Metadata } from "next";
import DocPage from "@/components/doc-page";
import { botUrl, site } from "@/lib/site";

export const metadata: Metadata = {
  title: "تماس با ما",
  description: "راه‌های ارتباط با سنسی: پشتیبانی داخل ربات تلگرام، ایمیل، تلفن و نشانی.",
  alternates: { canonical: "/contact" },
};

export default function Contact() {
  const b = site.business;
  return (
    <DocPage path="/contact" title="تماس با ما" lead="سریع‌ترین راه، دکمه «🎧 پشتیبانی» داخل ربات سنسی است. سؤال درباره یک سفارش را همراه کد سفارش بفرست.">
      <div className="contact-grid">
        <div className="contact-card contact-card--wide">
          <h2>پشتیبانی در تلگرام</h2>
          <a href={botUrl("site_contact")} target="_blank" rel="noopener" dir="ltr">@{site.bot.username}</a>
        </div>
        <div className="contact-card">
          <h2>ایمیل</h2>
          <a href={`mailto:${b.email}`} dir="ltr">{b.email}</a>
        </div>
        {b.phone && (
          <div className="contact-card">
            <h2>تلفن</h2>
            <a href={`tel:${b.phone}`} dir="ltr">{b.phone}</a>
          </div>
        )}
        <div className="contact-card">
          <h2>ساعت پاسخ‌گویی</h2>
          <p>{b.hours}</p>
        </div>
        <div className="contact-card contact-card--wide">
          <h2>نشانی</h2>
          <p>{b.address}</p>
          {b.postalCode && <p>کد پستی: <span dir="ltr">{b.postalCode}</span></p>}
        </div>
      </div>
    </DocPage>
  );
}
