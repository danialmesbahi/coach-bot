import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/", name: "Sensi Console", short_name: "Sensi", description: "پنل حرفه‌ای مدیریت سنسی",
    start_url: "/", display: "standalone", background_color: "#151820", theme_color: "#151820",
    orientation: "any", lang: "fa", dir: "rtl",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
