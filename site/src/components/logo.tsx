import { site } from "@/lib/site";

/** Sensi mark: a heartbeat peak inside an ember tile. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="var(--ember)" />
      <path d="M5 18h5.2l2.4-7.5 4.2 13 2.6-8 1.4 2.5H27" fill="none" stroke="var(--night)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Uses the custom logo from sensi.config.ts (brand.logo) when set, otherwise the built-in mark. */
export function Logo() {
  return (
    <span className="logo">
      {site.logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="logo__mark logo__mark--custom" src={site.logo} alt="" width={34} height={34} />
      ) : (
        <LogoMark className="logo__mark" />
      )}
      <span className="logo__word">{site.name}</span>
    </span>
  );
}
