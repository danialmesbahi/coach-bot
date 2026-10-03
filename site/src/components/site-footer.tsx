import Link from "next/link";
import { botUrl, config, site } from "@/lib/site";
import { Logo } from "./logo";
import TrustBadges from "./trust-badges";

export default function SiteFooter() {
  const b = site.business;
  return (
    <footer className="site-footer" data-dark>
      <div className="site-footer__inner">
        <div className="site-footer__brand">
          <Logo />
          <p>{config.footer.about}</p>
          <a className="site-footer__bot" href={botUrl("site_footer")} target="_blank" rel="noopener" dir="ltr">@{site.bot.username}</a>
        </div>
        <nav className="site-footer__col" aria-label="سنسی">
          <h2>سنسی</h2>
          <Link href="/about">درباره ما</Link>
          <Link href="/contact">تماس با ما</Link>
          <Link href="/#programs">برنامه‌ها و قیمت‌ها</Link>
          <Link href="/#faq">پرسش‌های پرتکرار</Link>
        </nav>
        <nav className="site-footer__col" aria-label="قوانین">
          <h2>قوانین</h2>
          <Link href="/terms">قوانین و مقررات</Link>
          <Link href="/privacy">حریم خصوصی</Link>
          <Link href="/refund">شرایط بازگشت وجه</Link>
        </nav>
        <address className="site-footer__col site-footer__contact">
          <h2>تماس</h2>
          <span>{b.address}{b.postalCode && <>، کد پستی <span dir="ltr">{b.postalCode}</span></>}</span>
          {b.phone && <a href={`tel:${b.phone}`} dir="ltr">{b.phone}</a>}
          <a href={`mailto:${b.email}`} dir="ltr">{b.email}</a>
          <span>{b.hours}</span>
        </address>
        <div className="site-footer__badges">
          <TrustBadges />
        </div>
      </div>
      <div className="site-footer__base">
        <span>© {b.foundingYear} {site.name}. {config.footer.rights}</span>
        <span>{config.footer.paymentNote}</span>
      </div>
    </footer>
  );
}
