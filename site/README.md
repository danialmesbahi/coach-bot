# Sensi public site

Landing page and future customer web platform for Sensi. Separate from the staff panel in `../web`.

- Next.js 16 (App Router, all pages static), React 19, TypeScript, no animation libraries.
- Interactions: cursor spotlight and chalk dust on the hero, a heart-rate line that rises with scroll speed,
  scroll-lit statement, expanding discipline panels, front/back muscle map, scroll-driven Telegram journey.
- Photography in `src/assets` was generated with GPT Image; replace with real coach/student photos when available.
- SEO/GEO: metadata, Open Graph image, JSON-LD (Organization, Service + Offers, HowTo, FAQPage, Breadcrumbs),
  `sitemap.xml`, `robots.txt`, `manifest.webmanifest`, `llms.txt`.

## Before publishing (eNamad / Samandehi / ZarinPal)

Set these build-time variables (or edit `src/lib/site.ts`). They must match the eNamad registration exactly.

| Variable | Purpose |
|---|---|
| `SITE_URL` | Public origin, e.g. `https://sensi.ir` |
| `BUSINESS_LEGAL_NAME`, `BUSINESS_ADDRESS`, `BUSINESS_POSTAL_CODE`, `BUSINESS_PHONE`, `BUSINESS_EMAIL`, `BUSINESS_HOURS` | Footer, contact page, structured data |
| `ENAMAD_ID`, `ENAMAD_CODE` | eNamad trust seal in the footer |
| `SAMANDEHI_ID`, `SAMANDEHI_P` | Samandehi seal |
| `ZARINPAL_TRUST=true` | ZarinPal trust badge after merchant approval |

### Live programs

The programs section reads the panel's catalog from `GET /api/public/catalog` on the web API (only storefront fields:
title, description, price, duration, type and questionnaire fields; never delivery content). Set `CATALOG_API_URL`
at runtime, e.g. `http://web-api:8090/api/public/catalog` inside Docker. The home page reads it on every render (host nginx
keeps a 60-second copy), so panel edits show within a minute; each program's button opens that exact product in the bot (`?start=buy_<id>`). If the API is unreachable the
defaults in `src/lib/site.ts` are shown instead.

Review `/terms`, `/privacy` and `/refund` before launch.

## Commands

```bash
pnpm install
pnpm dev      # http://localhost:3100
pnpm check    # lint + typecheck + build
```
