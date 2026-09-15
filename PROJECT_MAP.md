# Coach Bot — Fast Map

Read this first for any change. Then open only the listed route and its matching test(s).

## Scope and source of truth

- One bot, one Sensi, no multi-tenant model.
- Customers use Telegram. Web roles are `platform`, `leader`, `staff` in `staff_accounts`; permissions live in `app/services/staff.py`. Environment IDs bootstrap accounts once, not on every login. Legacy `Settings.role()` is for bot compatibility, not web authorization.
- Contract precedence: `AGENT.md` → current code/migrations → `README.md`.

## Runtime

`entrypoint.sh` → Alembic → `app/main.py` → Redis FSM/rate limit → routers:

```text
edit router → customer router (private chats only; no web-login approval)
```

- Development: polling. Production: Telegram webhook + ZarinPal callback.
- Persistent data: PostgreSQL. Redis: FSM, password-authenticated staff sessions and rate limits.
- Web: nginx ingress `:8090` → Next.js frontend / aiohttp API. Staff use the web panel, never Telegram admin callbacks.

## Routes by intent

| Change | Open first | Then |
|---|---|---|
| Customer menu, purchase, form, profile, order, support | `app/handlers/user.py` | `keyboards.py`, `states/forms.py`, `db/repositories.py` |
| Coach/admin panel, receipt, plan, reports, buyers | `app/webapp.py` | `web/src/components/console-app.tsx`, `app/db/repositories.py` |
| KPIs, personal/platform analytics, technical counters | `app/analytics_api.py`, `docs/ANALYTICS.md` | `app/services/telemetry.py`, `web/src/components/analytics.tsx`, `tests/test_analytics.py` |
| Profile edit | `app/handlers/edit.py` | `db/repositories.py`, `utils/validation.py` |
| Payment gateway/callback | `services/payment.py`, `main.py` | `handlers/user.py`, `db/repositories.py` |
| Configurable products, ready-made delivery, private channel memberships | `catalog_api.py`, `services/catalog.py`, `services/fulfillment.py` | `web/src/components/catalog.tsx`, `docs/PRODUCT_CATALOG.md` |
| Data/status/reporting | `db/repositories.py` | `schema.sql`, latest Alembic migration |
| Roles, env, webhook, rate limits | `config.py`, `main.py` | `middlewares/security.py`, `docker-compose.yml` |
| Staff accounts, password login/reset, permissions, collaboration | `services/staff.py`, `webapp.py` | `web/src/components/staff-panel.tsx`, `docs/STAFF_ACCESS.md`, `tests/test_password_login.py` |
| UI labels/keyboard/callbacks | `keyboards.py` | relevant handler |

## Core flow

```text
buy → PurchaseForm → users update + order snapshot → payment
→ paid/receipt review → Sensi status → plan file_id → customer delivery
```

- A new order always refreshes age/height/weight/photos; stable profile values are reused.
- Every order gets `form_snapshot` and profile history. Explicit profile edits update the latest enrolled order; earlier orders retain their own data.
- Ownership must use `get_user_order`; privileged callbacks must role-check.
- Valid status transitions live in `update_order_status`; do not bypass them casually.
- Amounts are stored/displayed as Toman despite the legacy `price_irr` column name; ZarinPal request/verify converts them to IRR.

## UX contract

- Customer: product → numbered questionnaire → review → payment → order detail/status → plan/support.
- Recovery stays on the same order: failed gateway → «ادامه پرداخت»; rejected receipt → «ارسال رسید جدید»; cancellation preserves the record.
- Sensi sees only actionable orders; pending receipts reopen with approve/reject controls, and orders/messages are paginated.
- One primary action per message, Persian status labels, immediate callback acknowledgement, and explicit retry text on recoverable failures.

## High-risk seams

- Router order and shared `SupportForm` can swallow messages from another role.
- Payment updates must remain atomic/idempotent; do not duplicate successful sales.
- Telegram files are stored as file IDs, not local uploads; validate type and size.
- New database fields require an Alembic migration; never require `down -v`.

## Verification map

| Area | Tests |
|---|---|
| Validation/text | `tests/test_validation.py`, `tests/test_text.py` |
| Forms, UI, second purchase | `test_v125_ui.py`, `test_v129_ui.py`, `test_v131_second_purchase.py` |
| Roles, reports, buyers | `test_v126_admin_reports.py`, `test_static_integrity.py` |
| Support/profile history | `test_v127_features.py`, `test_v128_profile_and_support.py` |
| Payment hardening/recovery/UX | `test_hardening_and_ux.py` |

## Graph usage

```powershell
graphify query "<feature or function>" --budget 500
graphify path "<node A>" "<node B>"
graphify update .
```

The graph is an optional navigation aid and can be stale; verify exact behavior against current source. See `docs/ARCHITECTURE.md` for deployment and checks.
