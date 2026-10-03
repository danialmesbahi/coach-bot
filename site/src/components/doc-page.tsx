import Link from "next/link";
import type { ReactNode } from "react";
import { site } from "@/lib/site";

type Props = { title: string; lead?: string; updated?: string; path: string; children: ReactNode };

/** Shared layout for about, contact and policy pages, with breadcrumb structured data. */
export default function DocPage({ title, lead, updated, path, children }: Props) {
  const crumbs = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: site.name, item: site.url },
      { "@type": "ListItem", position: 2, name: title, item: `${site.url}${path}` },
    ],
  };
  return (
    <article className="doc">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(crumbs) }} />
      <nav className="doc__crumbs" aria-label="مسیر صفحه">
        <Link href="/">{site.name}</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{title}</span>
      </nav>
      <h1>{title}</h1>
      {lead && <p className="doc__lead">{lead}</p>}
      {updated && <p className="doc__updated">آخرین به‌روزرسانی: {updated}</p>}
      <div className="doc__body">{children}</div>
    </article>
  );
}
