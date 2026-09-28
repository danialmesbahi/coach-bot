# Architecture and development

One coach business, one deployment, multiple staff. This is not a multi-tenant platform.

## Boundaries

- `app/main.py`: Telegram private-chat routing, polling/webhook lifecycle, payment callbacks.
- `app/handlers/`: customer registration and order/profile edits. Telegram does not authenticate web staff. The legacy `admin.py` is not registered.
- `app/webapp.py`: aiohttp staff API, authentication/authorization, uploads, SSE and read-cache limits.
- `app/db/repositories.py`: parameterized SQL and atomic business transitions. Money is stored as toman despite legacy `price_irr`; only the gateway adapter converts to rial.
- `app/services/payment.py`: gateway request/verification. `payment_attempts` preserves earlier retry authorities; settlement is atomic and cannot rewrite an already-paid order.
- `app/services/staff.py`: database-backed accounts, password-only authentication/change/reset, permission catalog, hierarchy and audit. See `docs/STAFF_ACCESS.md` for onboarding and deployment.
- `app/utils/media.py`: shared file-signature allowlist and bounded buffers. Signature checks are not malware scanning.
- `web/`: Next.js/React/TypeScript PWA. The client never decides permissions or writes directly to the database.
- `alembic/versions/`: ordered schema migrations. Never reset volumes to deploy a migration.

## Deployment

Only nginx ingress publishes port 8090. It proxies web UI to `web:3000`, API/media/SSE to `web-api:8090`, and production webhook/payment returns to `bot:8080`. PostgreSQL, Redis and API have no public ports.

Copy `.env.example` and `.env.live.example` to their non-example names and fill credentials locally. `.env.live` overrides `.env`. Never commit these files or database/browser backups.

For an Internet-facing VPS, port 8090 binds to loopback by default and HTTPS terminates at the edge described in `deploy/nginx.conf.example`. Set `INGRESS_BIND_IP=0.0.0.0` only for intentional local-network testing. Add only that edge's verified source address in `deploy/trusted-proxies.conf`; it must overwrite `X-Real-IP`. Do not trust a whole LAN or arbitrary forwarding headers. Tunnels without reliable client identity intentionally share an IP bucket: configure/validate the edge before multi-user production use. Standalone Next development is not a public ingress.

`APP_ENV=production` requires real credentials, HTTPS, webhook secret, and a non-mock payment mode. Changing code does not activate a real merchant. Back up before migration; bot runs migrations by default, API does not.

## Checks

```sh
python -m pytest -q
cd web
node node_modules/eslint/bin/eslint.js
node node_modules/typescript/bin/tsc --noEmit
node --test tests/chat-viewport.test.mjs
pnpm build
```

`scripts/check_services.py` checks real PostgreSQL/Redis with temporary SQL tables, explicit test IDs and its own expiring Redis key. It rolls back and sends no Telegram messages. Use `PYTHONPATH=.` locally or `/app` in a container. CI runs migrations against disposable services before this check.

Before committing: `python scripts/check_secrets.py`. This inspects staged content, blocks sensitive paths and recognized tokens, and checks local credential values without printing them. It is a limited guard, not an exhaustive scanner. CI uses `--tracked`.

## Capacity and known ceilings

- Run one polling bot. Photo/FSM locks are process-local; multiple bot workers need coordinated state handling first.
- Upload concurrency, media/cache byte budgets, API pagination and SSE subscriber count are bounded. Rejected load must be retried with backoff, not tight loops.
- Search and paging still use database aggregation; test realistic row counts and query plans before claiming thousands of concurrent users.
- `scripts/load_smoke.py` is a local-only, password-authenticated smoke helper (`--credentials-file`), not proof of production capacity. It caps requests below the API rate limit.
- A paid callback settles before Telegram notification. If Telegram notification fails, order data stays paid; guaranteed notification delivery/reconciliation is not implemented.
- Native iPhone PWA keyboard behavior still requires real-device checks; desktop viewport tests cannot certify it.
