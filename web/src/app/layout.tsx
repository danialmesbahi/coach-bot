import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Sensi Console", template: "%s · Sensi" },
  description: "پنل حرفه‌ای مدیریت سنسی",
  applicationName: "Sensi Console",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "Sensi" },
  formatDetection: { telephone: false },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/icon-180.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#151820" },
    { media: "(prefers-color-scheme: light)", color: "#eef1ff" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="fa" dir="rtl" suppressHydrationWarning><body>{children}</body></html>;
}
