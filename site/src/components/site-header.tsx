"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type MouseEvent } from "react";
import { fa } from "@/lib/format";
import { botUrl, config } from "@/lib/site";
import { Logo } from "./logo";

const links = config.nav.links;
const more = [
  { href: "/about", label: "درباره ما" },
  { href: "/contact", label: "تماس" },
  { href: "/terms", label: "قوانین" },
  { href: "/refund", label: "بازگشت وجه" },
];

/** The section currently under the header, so the menu can mark where you are. */
function currentSection() {
  let found = "";
  for (const l of links) {
    const el = document.getElementById(l.href.split("#")[1] ?? "");
    if (el && el.getBoundingClientRect().top < window.innerHeight * 0.4) found = l.href;
  }
  return found;
}

/**
 * App-like header: every link navigates inside the site without a full reload.
 * On the home page the logo and section links scroll smoothly instead of navigating.
 * On phones the menu drops down under the header as a panel of section tiles.
 */
export default function SiteHeader() {
  const pathname = usePathname();
  const onHome = pathname === "/";
  const [open, setOpen] = useState(false);
  const [here, setHere] = useState("");

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onResize = () => { if (window.innerWidth > 1100) setOpen(false); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("resize", onResize); };
  }, [open]);

  const toggle = () => {
    if (!open) setHere(onHome ? currentSection() : "");
    setOpen(!open);
  };

  const toTop = (event: MouseEvent) => {
    setOpen(false);
    if (!onHome) return;
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
    history.replaceState(null, "", "/");
  };

  const toSection = (event: MouseEvent, href: string) => {
    setOpen(false);
    if (!onHome) return;
    const target = document.getElementById(href.split("#")[1] ?? "");
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    history.replaceState(null, "", href.replace(/^\//, ""));
  };

  return (
    <header className={`site-header${open ? " is-open" : ""}`}>
      <div className="site-header__inner">
        <Link href="/" className="site-header__home" aria-label={`${config.brand.name}، صفحه اصلی`} onClick={toTop}>
          <Logo />
        </Link>
        <nav className="site-nav" aria-label="بخش‌های صفحه">
          {links.map((l) => (
            <Link key={l.href} href={l.href} scroll={!onHome} onClick={(e) => toSection(e, l.href)}>{l.label}</Link>
          ))}
        </nav>
        <a className="btn btn--ember btn--small" href={botUrl("site_header")} target="_blank" rel="noopener">
          {config.nav.cta}
        </a>
        <button className="site-header__menu" type="button" aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? "بستن فهرست" : "باز کردن فهرست"} onClick={toggle}>
          <span /><span />
        </button>
      </div>

      <div className="mnav__shade" aria-hidden="true" onClick={() => setOpen(false)} />
      <nav id="mobile-nav" className="mnav" aria-label="فهرست" inert={!open}>
        <div className="mnav__grid">
          {links.map((l, i) => (
            <Link
              key={l.href}
              href={l.href}
              scroll={!onHome}
              className={`mnav__tile${l.href === here ? " is-here" : ""}`}
              style={{ ["--i" as string]: i }}
              onClick={(e) => toSection(e, l.href)}
            >
              <span className="mnav__num">{fa(String(i + 1).padStart(2, "0"))}</span>
              <b>{l.label}</b>
            </Link>
          ))}
        </div>
        <div className="mnav__more">
          {more.map((l) => <Link key={l.href} href={l.href} onClick={() => setOpen(false)}>{l.label}</Link>)}
        </div>
        <a className="btn btn--ember mnav__cta" href={botUrl("site_menu")} target="_blank" rel="noopener" onClick={() => setOpen(false)}>
          {config.nav.cta}
        </a>
      </nav>
    </header>
  );
}
