import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import RouteProgress from "@/components/route-progress";
import SiteChrome from "@/components/site-chrome";
import SiteFooter from "@/components/site-footer";
import SiteHeader from "@/components/site-header";
import { botUrl, config, site } from "@/lib/site";
import "./globals.css";

const yekan = localFont({
  src: "../fonts/IRANYekanX-Variable.woff2",
  weight: "100 1000",
  variable: "--font-yekan",
  display: "swap",
  preload: true,
  fallback: ["Tahoma", "system-ui", "sans-serif"],
});

const title = config.seo.title;

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: { default: title, template: "%s | سنسی" },
  description: site.description,
  applicationName: site.name,
  keywords: [...config.seo.keywords],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    locale: site.locale,
    url: "/",
    siteName: site.name,
    title,
    description: site.description,
  },
  twitter: { card: "summary_large_image", title, description: site.description },
  robots: { index: true, follow: true, googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 } },
  formatDetection: { telephone: false, email: false, address: false },
  category: "health",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: config.theme.night,
  colorScheme: "dark",
};

const orgLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": ["Organization", "HealthAndBeautyBusiness"],
      "@id": `${site.url}/#org`,
      name: site.name,
      alternateName: site.nameLatin,
      url: site.url,
      logo: `${site.url}/icon.svg`,
      description: site.description,
      email: site.business.email,
      ...(site.business.phone ? { telephone: site.business.phone } : {}),
      address: { "@type": "PostalAddress", streetAddress: site.business.address, addressCountry: "IR", ...(site.business.postalCode ? { postalCode: site.business.postalCode } : {}) },
      sameAs: [botUrl()],
    },
    {
      "@type": "WebSite",
      "@id": `${site.url}/#website`,
      url: site.url,
      name: site.name,
      inLanguage: "fa-IR",
      publisher: { "@id": `${site.url}/#org` },
    },
  ],
};

const t = config.theme;
const themeCss = `:root{--night:${t.night};--carbon:${t.carbon};--carbon-2:${t.carbon2};--steel:${t.steel};--bone:${t.bone};--ash:${t.ash};--ash-2:${t.ash2};--ember:${t.ember};--ember-hot:${t.emberHot}}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className={yekan.variable}>
      <body>
        {/* Colours from sensi.config.ts → theme */}
        <style>{themeCss}</style>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(orgLd) }} />
        <a className="skip-link" href="#main">رفتن به محتوای اصلی</a>
        <SiteHeader />
        <SiteChrome />
        <RouteProgress />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
