"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/** In-app loading bar for page changes, so navigation feels like an app instead of a reload. */
export default function RouteProgress() {
  const pathname = usePathname();
  const bar = useRef<HTMLDivElement>(null);
  const timer = useRef(0);

  // start when an internal link to another page is clicked
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
      const a = (event.target as Element | null)?.closest<HTMLAnchorElement>("a[href]");
      if (!a || a.target === "_blank") return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || url.pathname === location.pathname) return;
      const el = bar.current;
      if (!el) return;
      el.classList.remove("is-done");
      el.classList.add("is-loading");
      document.documentElement.dataset.nav = "1";
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  // finish when the new page is on screen
  useEffect(() => {
    const el = bar.current;
    if (!el || !el.classList.contains("is-loading")) return;
    el.classList.add("is-done");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      el.classList.remove("is-loading", "is-done");
      delete document.documentElement.dataset.nav;
    }, 600);
  }, [pathname]);

  return <div ref={bar} className="route-bar" aria-hidden="true" />;
}
