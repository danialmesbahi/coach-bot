# Staff access

Single coach business; no tenant IDs, no Telegram management panel.

## Authority

| Role | Scope |
| --- | --- |
| platform | All business capabilities; create/manage platform, leader and staff accounts |
| leader | All business capabilities; create/manage staff, but not platform or other leaders |
| staff | Explicit read/action permissions only; templates are conveniences, not roles |

There is at most one leader. Self-disable through team management is rejected. At least one active platform owner must remain. Platform is an application role, **not** a remote shell or permission to expose infrastructure secrets.

`PLATFORM_TEAM_IDS` bootstraps platform owners; `SENSI_ID` bootstraps a leader unless that ID is a platform owner. `ADMIN_TEAM_IDS` bootstraps restricted legacy finance staff, never platform owners. Insert-on-conflict does nothing: restarting does not undo disabled accounts or edited permissions. If the same person is initially configured as both Sensi and platform, platform wins and appoints the leader from the web panel.

## Onboarding and recovery

1. Existing configured owner signs in with browser-bound Telegram approval.
2. Open the profile/team icon in the top bar → Members → Add member.
3. Set display name, login username, numeric Telegram ID, role and permissions. Send the generated invitation and username privately to that person.
4. Invitation opens the Staff account form. The member sets a 12–128 character password and approves the matching code with **their bound Telegram account**.
5. New staff log in with username/password **and** Telegram approval. Telegram-only entry and legacy signed Telegram endpoints cannot bypass their password requirement.

Invitation secrets are hashed in PostgreSQL, single-use and expire after 24 hours. The browser URL uses a fragment and clears it after reading. Password hashes use stdlib scrypt (N=32768, r=8, p=3), random salt, following an [OWASP password-storage configuration](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html); hashing runs off the event loop with two concurrent slots per API process. Public starts are IP-rate-limited and request bodies capped at 4 KiB, including chunked bodies.

Invite/reset revokes existing sessions and disables the old password until the new invitation is redeemed. Disable, enable, permission changes and explicit session revocation increment `session_version`. Every request checks the active database account/version; SSE checks on events and every 20-second heartbeat. No password is returned to the manager.

## Collaboration

- Each outgoing chat message stores staff ID and display-name snapshot. Renaming does not relabel history; old un-attributed messages are explicitly labelled legacy.
- Chat and order details contain Team handoff: current assignee and internal notes. Notes never invoke Telegram delivery.
- Staff can claim unassigned work or release their own work; managers can reassign. Version checks reject stale concurrent claims.
- Assignments coordinate work; they are not private visibility boundaries. Everyone with a module's read permission sees that module's records. A client-record permission includes that client's historical order details; task workflow access is separate.
- Final program delivery is serialized per order across API processes; uploads have bounded concurrency and timeout. A Telegram timeout after remote acceptance is still ambiguous: check the conversation before retrying, not a claim of distributed exactly-once delivery.

Account operations and notes/assignment audit write in the same SQL transaction. Operational audit/messages retain stable staff IDs and names. Activity has cursor pagination; team has 20 rows/page. API policy is fail-closed for unlisted handlers and covers media and SSE. Cached dashboard aggregates are copied and filtered before returning to each actor.

## Deployment and checks

Back up PostgreSQL, run Alembic through `0017_staff`, then rebuild/restart **both bot and web-api**, plus Next.js. The bot approval code and API must be from the same revision. Older Redis browser sessions lack staff identity/version and require a fresh login. Never reset volumes.

Checks:

```sh
python -m pytest -q
PYTHONPATH=. python scripts/check_services.py
cd web
pnpm lint
pnpm typecheck
pnpm build
node --test tests/chat-viewport.test.mjs
node tests/staff-ui.mjs
```

`check_services.py` uses temporary SQL tables and rolls back; it verifies invitation activation/one-use, disable and audit without Telegram sends. The optional UI test requires a local Playwright runtime (`PLAYWRIGHT_MODULE`) and browser (`BROWSER_CHANNEL` if using installed Edge/Chrome). It intercepts all API requests with synthetic fixtures and checks FA/EN at 390/820/1440 px; it does **not** certify iPhone hardware or the live Telegram approval interaction.

Real deployment still requires HTTPS, working Telegram connectivity and real merchant configuration. This feature does not turn mock payments into live payments and is not a load-capacity certification.
