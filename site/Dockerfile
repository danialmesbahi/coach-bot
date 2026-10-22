FROM node:24-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:24-alpine AS builder
WORKDIR /app
# Business identity and trust-badge IDs are baked into the static pages at build time.
ARG SITE_URL BOT_USERNAME BUSINESS_LEGAL_NAME BUSINESS_ADDRESS BUSINESS_POSTAL_CODE BUSINESS_PHONE BUSINESS_EMAIL BUSINESS_HOURS
ARG ENAMAD_ID ENAMAD_CODE SAMANDEHI_ID SAMANDEHI_P ZARINPAL_TRUST
ENV NEXT_TELEMETRY_DISABLED=1 SITE_URL=$SITE_URL BOT_USERNAME=$BOT_USERNAME \
    BUSINESS_LEGAL_NAME=$BUSINESS_LEGAL_NAME BUSINESS_ADDRESS=$BUSINESS_ADDRESS BUSINESS_POSTAL_CODE=$BUSINESS_POSTAL_CODE \
    BUSINESS_PHONE=$BUSINESS_PHONE BUSINESS_EMAIL=$BUSINESS_EMAIL BUSINESS_HOURS=$BUSINESS_HOURS \
    ENAMAD_ID=$ENAMAD_ID ENAMAD_CODE=$ENAMAD_CODE SAMANDEHI_ID=$SAMANDEHI_ID SAMANDEHI_P=$SAMANDEHI_P ZARINPAL_TRUST=$ZARINPAL_TRUST
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:24-alpine AS runner
WORKDIR /app
# Business/trust values are also passed at runtime by docker-compose (pages are rendered per request).
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3100 HOSTNAME=0.0.0.0 CATALOG_API_URL=http://web-api:8090/api/public/catalog
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3100
CMD ["node", "server.js"]
