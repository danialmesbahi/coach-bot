# Test gate before real payments and deployment

## 1. Local automated checks

From the repository root:

```powershell
.venv/Scripts/python.exe -m pytest -q
cd web
pnpm exec tsc --noEmit
pnpm lint
pnpm build
node --test tests/chat-viewport.test.mjs tests/password-policy.test.mjs tests/api-diagnostics.test.mjs
```

Run `scripts/verify_catalog.py` inside the app container via stdin: it creates its own disposable database and fakes Telegram. Never point load tests at customer chats or payment gateways. This check covers paid/unpaid delivery, duplicate callbacks, file checkpoint/retry, once/lifetime subscriptions, archive access and role restrictions.

Browser scripts use mock API responses, never real purchases. With `TEST_BASE_URL` pointing to the built preview and Playwright installed, run `web/tests/catalog-ui.mjs` and `web/tests/catalog-delivery-ui.mjs`. They cover FA/EN, phone/tablet/desktop, file previews, high-resolution video containment, archive confirmation, save errors and the absence of the removed custom-question field. Also run `web/tests/workspace-integration.mjs` for related staff/catalog/order flows.

## 2. Real-device acceptance session

Record the approximate local time, page, account role, browser/OS, PWA or browser, and expected/actual result. Use test accounts and no real paid transactions yet.

- iPhone PWA + Safari, portrait/landscape: keyboard open/close, chat composer, safe areas, scroll restoration, large portrait/landscape media playback and close/back.
- iPad and desktop: resized layouts, overlays, filters, navigation and keyboard focus.
- Staff/leader/developer: allowed actions succeed; disallowed actions are not merely hidden but rejected by API.
- Catalog: multiple files, interrupted upload, save/reopen, once/lifetime duration, visibility, archive/cancel, original buyer access.
- Test bot: onboarding, existing profile reuse, test order, automatic delivery once, support media and assigned notes/followups.
- Connectivity: disconnect/reconnect, realtime recovery, stale editor conflicts, double-click save, session expiration.

Do not expect a browser exception for every visual defect. Send a screenshot/video and reproduction steps for layout or business-rule mismatches.

## 3. Review evidence

`python scripts/review_diagnostics.py --since <UTC-ISO-time>` summarizes errors and slow operations in `artifacts/diagnostics/*.jsonl*`. Keep rotated files from the session. API operations over 2 seconds are logged; uploads or external services may legitimately take longer. Slow does not automatically mean broken.

Use KPI Experience for aggregate successful/error/slow API and bot counts, and Team Activity for durable staff actions. JSONL diagnostics deliberately do not duplicate all successful requests or retain private message/form content. Browser reports are bounded and best-effort; an offline report cannot arrive until connectivity returns, and closing the app can lose it.

Fix reproducible problems, add a regression check, rerun checks and repeat acceptance. Absence of log errors is not proof of correctness.

## 4. Separate production gate — not enabled by these checks

Only after acceptance: confirm capacity targets (concurrency, response-time budgets, CPU/memory/database connections), run staged load tests against a disposable environment, validate backup restore, TLS/secrets/roles, payment sandbox callbacks and idempotency. Then explicitly configure/authorize the live merchant/domain and production deployment. No production credentials, real charge, Git merge or server purchase is implied by test success.
