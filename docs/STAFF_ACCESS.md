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

1. The local operator initializes the seeded development owner's username/password once, using `scripts/setup_staff_password.py --telegram-id ID --credentials-file /path/to/private.json`. The file contains `username` and `password`, belongs outside Git and Docker build contexts, and should be removed after the initial password is changed. This script refuses to overwrite an existing password.
2. Sign in with username and password. No Telegram approval, signed widget, test login or invitation endpoint exists.
3. Profile/team → Members → Add member: set name, username, initial password, role and permissions. No Telegram ID is required. Share credentials through a private channel.
4. Every member can change their own password in My profile, supplying the current password.
5. Forgotten passwords are reset by a managing superior in Members → Reset password. There is no public recovery endpoint, no self-reset through team management, and leaders cannot reset platform accounts or other leaders.

New passwords require 8–128 characters, an ASCII uppercase letter, a digit and a non-word, non-whitespace symbol (for example !). Existing hashes remain verifiable. Password hashes use stdlib scrypt (N=32768, r=8, p=3) and a random salt. At most two hashing jobs run per API process; cancellation retains the slot until the worker finishes. Public login bodies are capped at 4 KiB, including chunked requests. Redis limits all attempts to 30 per source IP and 10 per normalized username in a five-minute window; unknown accounts use a dummy hash and the same failure response.

Password changes/resets, disable/enable, permission changes and explicit session revocation increment `session_version`. Each request resolves the stable staff ID and version from PostgreSQL; SSE also checks on events and its 20-second heartbeat. Resetting a disabled account does not enable it. Passwords are never returned by APIs or put in audit metadata. Managers choose an initial/new password; existing passwords cannot be retrieved.

## Collaboration

- Each outgoing chat message stores staff ID and display-name snapshot. Renaming does not relabel history; old un-attributed messages are explicitly labelled legacy.
- Chat and order details contain Team handoff: current assignee and internal notes. Notes never invoke Telegram delivery.
- Staff can claim unassigned work or release their own work; managers can reassign. Version checks reject stale concurrent claims.
- Assignments coordinate work; they are not private visibility boundaries. Everyone with a module's read permission sees that module's records. A client-record permission includes that client's historical order details; task workflow access is separate.
- Final program delivery is serialized per order across API processes; uploads have bounded concurrency and timeout. A Telegram timeout after remote acceptance is still ambiguous: check the conversation before retrying, not a claim of distributed exactly-once delivery.

Account operations and notes/assignment audit write in the same SQL transaction. Operational audit/messages retain stable staff IDs and names. Activity has cursor pagination; team has 20 rows/page. API policy is fail-closed for unlisted handlers and covers media and SSE. Cached dashboard aggregates are copied and filtered before returning to each actor.

## Deployment and checks

Back up PostgreSQL, run Alembic through `0018_password_login`, then rebuild/restart bot, web-api and Next.js. Stop the old bot/API while applying the migration. Previous Telegram/test sessions are rejected. Existing passwordless accounts become unconfigured; initialize the platform owner locally before handing over. Never reset volumes.

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

`check_services.py` uses temporary SQL tables and rolls back; it verifies password creation/login/change/reset, hierarchy enforcement, disable and attribution without Telegram identities without Telegram sends. The optional UI test requires a local Playwright runtime (`PLAYWRIGHT_MODULE`) and browser (`BROWSER_CHANNEL` if using installed Edge/Chrome). It intercepts all API requests with synthetic fixtures and checks FA/EN at 390/820/1440 px; it does **not** certify iPhone hardware or real-device rendering.

Real deployment still requires HTTPS, working Telegram connectivity and real merchant configuration. This feature does not turn mock payments into live payments and is not a load-capacity certification.
