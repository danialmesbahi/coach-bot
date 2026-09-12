# Release review — 2026-09-12

## Scope and result

This is a reviewed baseline, not certification of a bug-free or production-capacity system. The security pass covered 49 primary authored paths; not every historical handler, migration, stylesheet or UI state was audited exhaustively.

Security review used the boundary-first `security-scan` / `fix-finding` workflow, an independent pre-patch investigation, and one independent post-patch bypass/regression review. The latter found two payment lifecycle races, corrected and checked against real PostgreSQL temporary tables.

## Changes and evidence

| Boundary | Change | Validation |
| --- | --- | --- |
| Private Telegram data | Root message and callback filters deny group destinations before customer routers/FSM | Dispatcher tests block groups, supergroups and inline callbacks; private profile remains allowed |
| Web login | Isolated ingress overwrites client identity; only explicit edge peers can supply real IP | Unit tests reject/ignore untrusted identity; nginx config test passes; proxy/tunnel client-IP validation still required per deployment |
| Payment replay | Redis authority throttle, four in-flight verification slots, timeout, no persistent audit for unauthenticated cancellation returns | 50 concurrent duplicate callbacks produce one verification attempt; saturated and malformed paths tested |
| Payment integrity | Retain all saved retry authorities; refuse publication if order state changed; settlement cannot rewrite paid/cancelled orders | Real SQL integration checks both authorities, one-time settlement and paid-then-cancelled replay |
| Media and input | Shared signature validation, bounded reads, upload concurrency and caption limits | File-validation tests; oversized buffer fails; malformed auth input rejected |
| Sessions and resource lifetime | Revalidate SSE session; cap subscribers/cache bytes; release unused locks | Logout invalidation test, syntax/type checks; no 10k-user claim |
| Delivery artifacts | Explicit Docker copy scope, ignore private runtime data, staged-content secret guard | Guard passes; real credentials/backups/browser profiles excluded |

## Completed checks

- `python -m pytest -q`: 152 passed.
- `scripts/check_services.py` against running PostgreSQL/Redis: passed. Temporary SQL tables rolled back; only own test Redis challenge removed; no customer messages sent.
- Next ESLint, TypeScript, viewport check and Linux Docker production build passed during this review.
- `nginx -t`: passed (expected harmless non-root master warning).
- Migration `0016_payment_attempts` applied after local PostgreSQL backup. Backup archive is excluded from Git.
- New containers started. UI and health: 200; unauthenticated private API: 401; development login: 404.
- GitHub checks are configured to run tests plus full migrations/integration on disposable PostgreSQL/Redis and build the frontend.

## Not certified / release prerequisites

- Real merchant payment, webhook/public HTTPS configuration and an actual staff Telegram/browser login round trip need acceptance testing. Current local runtime is not automatically switched to production by these changes.
- An HTTPS proxy/tunnel must have a verified trustworthy client-IP path. Otherwise clients intentionally share a limiter bucket; never solve that by trusting arbitrary forwarding headers.
- Load testing with representative orders/messages and multiple authenticated sessions remains outstanding. Bounded requests protect resources but do not prove 10,000 simultaneous users.
- Real iPhone PWA keyboard, safe-area, attachment and navigation checks remain outstanding.
- Gateway reconciliation for duplicate actual charges, guaranteed notification delivery after process failure, and off-host backup/restore drills remain operational work.
- Signature allowlists are not antivirus scanning. Dependency/secret automation supplements, not replaces, code review.
- The codebase still contains large repository/API/UI modules and unused legacy admin code. This pass corrected affected shared boundaries; it did not rewrite the entire project or remove unreviewed legacy paths.

## Review trace

Pre-fix scan ID: `e1fceeb4-b977-471a-b08a-1b7a67a778cf`. Its sealed local report describes findings before remediation; it must not be interpreted as post-fix verification.

The scan tool reported aggregate thread usage of 13,397,436 tokens (13,361,528 input; 35,908 output; 12,576,512 cached input) across four threads. This is the tool's cumulative accounting scope, not a measurement of this final continuation or incremental billed cost.
