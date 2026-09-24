# Runtime diagnostics for test sessions

Local Docker runs persist bounded JSONL files in `artifacts/diagnostics/`:

- `bot.jsonl`: bot, fulfillment, payment and channel runtime warnings/errors.
- `web-api.jsonl`: API failures and authenticated browser error reports.
- Each service rotates at 5 MiB with four backups (25 MiB per service). The queue is bounded to 1,000 entries and drops excess entries during error storms rather than blocking business requests. These are diagnostic records, not an exact audit ledger.

After reproducing a problem, give the reviewer this directory, the approximate time, the page and the steps you performed. Include rotated `.jsonl.1`–`.jsonl.4` files if relevant. These files and database backups are excluded from Git. Do not send `.env`, database dumps, user photos or catalog files as diagnostics.

Records contain UTC time, severity, service/logger, source file/line, exception type, stack frame locations and a request ID. API 500 responses include that ID. The browser reports only page, standard exception type and bundle filename/line/column: no exception message, URL query, form input, chat body, password, token, SQL parameters or local-variable values. Frontend reports are throttled locally and server-side.

Slow API/bot operations (at least 2 seconds) now include the server-defined route/state, duration in milliseconds, HTTP status/method and request ID where available. Timings measure handler execution, not the full streamed media transfer. Browser API network/timeout/5xx and slow-response issues also report metadata through the existing authenticated endpoint, at most once per minute per mounted session and six reports/minute server-side. One offline report is held in memory for reconnect; closing/reloading the app can lose it. Cancelled searches do not count as failures. Slow browser reports are not counted as server errors. The queue emits `diagnostics_dropped` after it can accept records again; a process crash may prevent this notice. Startup is recorded as `service_started`.

Successful request/checkout activity remains aggregated in `analytics_buckets` (KPI Experience), and staff mutations are recorded in `audit_logs` (Team Activity). Do not log every keystroke, chat body or successful poll into diagnostic files: doing so adds server load and exposes private data. Diagnostic files, KPI and the audit ledger serve different purposes.

Run `python scripts/review_diagnostics.py --since 2026-09-22T08:30:00Z` for a read-only grouped report of the session, including rotated files, counts, last-seen times, slowest recorded durations and dropped/malformed records. See `docs/TESTING_RELEASE.md` for automated and real-device test gates before enabling live payments/deployment.

Infrastructure/process failures (Next.js server, ingress, PostgreSQL, Redis, startup before diagnostics initialization) additionally live in Docker's rotated service logs, configured at 10 MiB × 3 per container. Inspect them locally using `docker compose ps` and scoped `docker compose logs --since ... <service>`; do not share raw infrastructure logs without redaction. A stopped host cannot log its own outage; external uptime monitoring is a production-deployment requirement, not supplied by these application files.

Review 2026-09-22 after 08:30 UTC: repeated bot polling failures were classified from Docker as `TelegramNetworkError`; a read-only `getMe` probe also timed out after 12 seconds. This is unresolved network reachability to Telegram, not evidence that delivery or polling succeeded. Check host/container internet and VPN/proxy routing before end-to-end Telegram acceptance. Future aiogram poll records retain the allow-listed exception class (without raw exception text).

Follow-up 2026-09-22: connectivity subsequently recovered and a read-only `getMe` probe succeeded. Polling startup now retries transient connection failures with capped backoff instead of restarting the container. See `REVIEW_2026-09-22.md` for the later log window, fixes and verification; recovery does not guarantee future network availability.

Delivery failures include `order_id`; catalog validation/upload failures include a fixed `error_code`. Uncertain or non-retryable delivery errors pause the order (`delivery_paused`) instead of repeatedly sending to the buyer. Check the recipient's actual messages and logs before using **Retry delivery** in order details. Only Telegram flood-limit rejections retry automatically, for at most six failed attempts. A process crash between an accepted Telegram send and the database checkpoint can still leave an ambiguous delivery; Telegram provides no exactly-once send key.

Incident 2026-09-22: `sendDocument` returned a sticker for a WEBP upload. Dereferencing `sent.document.file_id` failed after the send, causing repeat fulfillment. The response kind is now checked and successful files are checkpointed regardless of Telegram's returned media type. Order 54 / asset 3 had five failed completion attempts; receipt of the repeated sticker was reported by the operator. Its missing per-asset checkpoint was restored (no payment edits), then normal fulfillment completed after deploying the fix.

These logs capture runtime failures, not every possible visual or logical bug. Expected validation failures do not produce stack traces; counts remain in KPI telemetry. Include a screenshot and reproduction steps for problems that produce no runtime exception. Browser bundle hashes help identify the deployed build; keep the corresponding source revision.

On this checkout the files are at `C:\Users\Danial\Desktop\coach_bot\artifacts\diagnostics\`. A production host must grant the application UID write access to the mounted diagnostics directory. Back up useful test logs before rotation overwrites them. Logging does not send anything to an external service or automatically grant an AI access.
