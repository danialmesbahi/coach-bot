import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8090";
const botBackend = process.env.BOT_BACKEND_URL ?? "http://bot:8080";
const isDev = process.env.NODE_ENV === "development";
const csp = [
  "default-src 'self'", `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""} https://telegram.org`,
  "style-src 'self' 'unsafe-inline'", "img-src 'self' blob: data:", "media-src 'self' blob:", "font-src 'self'", "connect-src 'self'",
  "frame-src 'self' blob: https://oauth.telegram.org https://telegram.org", "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone", poweredByHeader: false,
  async rewrites() { return { beforeFiles: [
    { source: "/health", destination: `${backend}/health` },
    { source: "/payment/zarinpal/callback", destination: `${botBackend}/payment/zarinpal/callback` },
    { source: "/telegram/webhook", destination: `${botBackend}/telegram/webhook` },
    { source: "/api/:path*", destination: `${backend}/api/:path*` },
    { source: "/auth/:path*", destination: `${backend}/auth/:path*` },
    { source: "/media/:path*", destination: `${backend}/media/:path*` },
  ], afterFiles: [], fallback: [] }; },
  async headers() { return [{ source: "/(.*)", headers: [
    { key:"Content-Security-Policy", value:csp }, { key:"Referrer-Policy", value:"strict-origin-when-cross-origin" },
    { key:"X-Content-Type-Options", value:"nosniff" }, { key:"X-Frame-Options", value:"DENY" },
    { key:"Permissions-Policy", value:"camera=(), microphone=(), geolocation=()" },
  ] }]; },
};

export default nextConfig;
