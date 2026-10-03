import type { MetadataRoute } from "next";
import { config, site } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${site.name} | برنامه تمرینی و غذایی اختصاصی`,
    short_name: site.name,
    description: site.description,
    start_url: "/",
    display: "standalone",
    background_color: config.theme.night,
    theme_color: config.theme.night,
    lang: "fa",
    dir: "rtl",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
