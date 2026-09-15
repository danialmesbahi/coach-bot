# Analytics / KPI

## Access

`/analytics` → `GET /api/analytics`. Leader and platform accounts can select platform or personal scope. Staff need `analytics.self` and can only see their own activity, even if they forge `scope=platform` or permission names. Identity comes from the authenticated session, not a query parameter. Personal responses omit all financial, team and telemetry fields. Migration 0022 grants existing staff the personal permission; managers can revoke it or assign it to new accounts.

## Definitions

All windows are rolling 7, 30 or 90 days, ending at the snapshot time, with inclusive start and exclusive end. Calendar grouping uses Asia/Tehran; first and last chart days are partial. Financial amounts are **Toman**, matching the current orders/sales implementation despite legacy `price_irr` names.

| Metric | Source and meaning |
|---|---|
| Paid revenue | Sum of `orders.amount` whose `paid_at` is in the window; before development share, not profit or refund-adjusted net revenue. |
| Revenue change | Current revenue versus the preceding equally long window. Undefined when the preceding revenue is zero. |
| Invoice conversion | Paid invoices among all invoices **created** in the current window. This is a cohort ratio, not current payments divided by current invoices. New invoices may still convert. |
| Daily trend | Verified paid orders grouped by payment date; zeros for empty days. Sum reconciles to the paid-revenue card. |
| Buyers / repeat buyers | Distinct paying users in the window; repeat requires an earlier paid order (including an earlier payment within the same window). |
| New users | Accounts created in the window; not daily active users. |
| Custom delivery | Median payment-to-delivery hours for manual orders delivered in the window; nonnegative intervals only. Includes sample size; excludes instant content/channel access. |
| Open work / unseen follow-ups | Current snapshot, not a window event count. |
| Replies / deliveries / notes | Recorded outgoing messages and attributed audit actions. Legacy events without staff attribution cannot be assigned retrospectively. Activity volume does not measure service quality. |
| Checkout steps | Interactions that kept or changed a purchase FSM step. Staying may mean adding photos or validation, not necessarily abandonment. |
| Technical metrics | Instrumented web API/bot/payment requests, service failures, rejected requests, mean elapsed time and requests over two seconds. Not unique users. |

Activity trail includes sign-ins, message-send metadata and stored audit actions. It excludes message/notes bodies and arbitrary audit metadata. Up to 25 events per page (maximum page 200); team summary shows up to 50 active accounts alphabetically. No invented performance targets or rankings.

## Cost and privacy

- No new dependencies or external tracking services.
- Business metrics query durable business tables in a read-only repeatable-read transaction.
- Read cache: 60 seconds, shared for platform scope and isolated per staff ID for personal scope; existing bounded cache/single-flight implementation reused.
- At most two cold analytics queries at a time per web process; 200 ms queue deadline, 9 s total query budget, 7 s statement limit; authenticated limit 20 requests/minute.
- Browser refresh: once per minute while visible; previous fetch aborted on filter changes/unmount. No per-event analytics recalculation from SSE.
- Technical counters aggregate in memory by hour/source/route/outcome, at most 2,048 keys, up to 256 keys flushed per five seconds. They never store IPs, identities, full URLs, bodies or raw exceptions.
- Best-effort counters can be lost on process crashes or database outages; they are **not** the financial/audit source of truth. Dropped events are counted when possible. Retention is 100 days with bounded cleanup batches.
- Browser error reports contain only one allowed view name, at most one per minute locally and six/minute server-side. CSRF/session protection applies; body limit 256 bytes.

## Coverage limits

Telemetry begins at deployment; older sales/audit data remains available. Step counts are not user-session funnels or proven abandonment. There is no CPU/RAM metric, external uptime probe, cross-device attribution, replay of customer screens, or alert-delivery service. Complete host/network outages cannot be measured by a process running on that host. Use independent infrastructure monitoring if those guarantees are required.

## Checks

`python -m pytest tests/test_analytics.py -q` checks authorization, bounds and privacy. `scripts/verify_analytics.py` runs migrations and reconciliation/isolation queries in its own disposable PostgreSQL database. Pipe it to a one-off app container with `python -`; it drops only the database it created. `web/tests/analytics-ui.mjs` uses mocked API responses for FA/EN, light/dark, scope/filter transitions and widths 375/820/1440. These checks are not a concurrent-user load test or physical iPhone test.
