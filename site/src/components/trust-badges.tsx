import { site } from "@/lib/site";

/**
 * eNamad, Samandehi and ZarinPal seals. Each renders the official markup once its IDs are
 * configured in src/lib/site.ts (or the matching environment variables); until then a slot keeps the layout.
 */
export default function TrustBadges() {
  const { enamadId, enamadCode, samandehiId, samandehiP, zarinpal } = site.trust;
  return (
    <ul className="badges" aria-label="نمادها و مجوزها">
      <li className="badge">
        {enamadId && enamadCode ? (
          <a referrerPolicy="origin" target="_blank" rel="noopener" href={`https://trustseal.enamad.ir/?id=${enamadId}&Code=${enamadCode}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img referrerPolicy="origin" src={`https://trustseal.enamad.ir/logo.aspx?id=${enamadId}&Code=${enamadCode}`} alt="نماد اعتماد الکترونیکی" width={96} height={96} loading="lazy" {...{ code: enamadCode }} />
          </a>
        ) : (
          <span className="badge__slot"><b>نماد اعتماد الکترونیکی</b><small>در حال ثبت</small></span>
        )}
      </li>
      <li className="badge">
        {samandehiId && samandehiP ? (
          <a referrerPolicy="origin" target="_blank" rel="noopener" href={`https://logo.samandehi.ir/Verify.aspx?id=${samandehiId}&p=${samandehiP}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img referrerPolicy="origin" src={`https://logo.samandehi.ir/logo.aspx?id=${samandehiId}&p=${samandehiP}`} alt="نشان ملی ثبت رسانه‌های دیجیتال" width={96} height={96} loading="lazy" />
          </a>
        ) : (
          <span className="badge__slot"><b>نشان ساماندهی</b><small>در حال ثبت</small></span>
        )}
      </li>
      <li className="badge">
        {zarinpal ? (
          <a target="_blank" rel="noopener" href={`https://www.zarinpal.com/trustPage/${new URL(site.url).host}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="https://cdn.zarinpal.com/badges/trustLogo/1.svg" alt="نشان اعتماد زرین‌پال" width={96} height={96} loading="lazy" />
          </a>
        ) : (
          <span className="badge__slot"><b>نشان زرین‌پال</b><small>پرداخت امن</small></span>
        )}
      </li>
    </ul>
  );
}
