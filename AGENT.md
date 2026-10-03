# Coach Telegram Bot — Agent Context

> Fast context: read `PROJECT_MAP.md` first, then open only the route-specific files it names. This document remains the authoritative product and safety contract.

Current client workflow: `docs/CLIENT_WORKFLOW_PLAN.md` records the 2026-10-03 implementation and verification. Gateway-only payments, independent per-order measurements/photos, explicit record-edit destinations and durable order information requests supersede older behavior.

## Project purpose

This is a production-oriented Telegram bot for **one Sensi / coach only**. The bot sells three products:

1. 🥗 Nutrition plan
2. 🏋️ Training plan
3. 🔥 Combined nutrition + training plan

The bot runs on one server and one database. There is exactly one Sensi per bot.

Catalog update: the three products above are initial data, not a fixed catalog. Leaders/platform accounts can manage custom programs, ready-made content and private-channel subscriptions. `docs/PRODUCT_CATALOG.md` defines current product, duration, form and delivery behavior. Purchase terms are snapshotted; archiving never deletes purchase history.

## Roles

Web-panel update: the current web roles are **platform**, **leader** and **staff**, stored in PostgreSQL. Platform manages all levels; leader manages staff only; staff has explicit capabilities. `docs/STAFF_ACCESS.md` supersedes the historical web-role restrictions below. `Settings.role()` and the descriptions below remain historical bot compatibility, not web API authorization. Never use environment role checks to authorize staff API/media/SSE requests.

Historical Telegram roles:

### 1. Customer
A normal Telegram user who buys plans, submits personal data, pays, receives status updates, receives the final plan, and can message the Sensi.

### 2. Sensi
The single coach associated with this bot.

The Sensi can:
- view actionable orders
- review client information after server-verified gateway payments
- manage order status
- request more information
- send plans to customers
- send and receive customer messages
- view sales statistics

The Sensi uses the web panel, including sales and the development-team share. Telegram exposes only customer flows. Staff login is username/password only; recovery is through a managing superior.

### 3. Admin Team
The admin team manages only the sales/financial side of this single Sensi.

The admin team can:
- view sales statistics
- view monthly and total sales
- view the development-team share (50% by default)
- view buyers and their complete stored information
- paginate buyers 10 per page

The admin team must NOT be able to access the Sensi panel through generic callbacks.

## Admin commission

The development team receives **50% by default**, configured by `DEVELOPMENT_TEAM_PERCENT`. Stored role name `admin_team` is retained for compatibility.

Monthly invoice/report must show at least:
- current month total sales
- current month order count
- each successful sale for the month
- configured development-team commission
- Sensi net share
- historical total sales
- historical successful order count

Financial records must not be silently deleted just because a customer cancels an unpaid order.

## Customer profile model

The customer should not repeatedly enter static information.

### Stored profile information
- first/last name as available
- Telegram ID
- Telegram username
- phone number
- gender
- current age
- current height
- current weight
- current body measurements in cm (abdomen, waist, arm, thigh, shoulder width, chest)
- goal
- training experience
- food allergy
- food restriction
- supplements
- notes
- profile/body photos

### Reuse behavior for later purchases
For a subsequent purchase, reuse stored profile data whenever possible.

Do NOT ask again for static data such as:
- name
- phone number
- gender

For every new purchase, ask again for changeable/current information when appropriate:
- age
- height
- weight
- body measurements when required by the product
- new body photos

Reuse other profile information such as goal, training history, allergy, restriction, supplements, notes unless missing or clearly required for the selected product.

Every completed questionnaire/order creates an independent snapshot. Profile edits update the current profile only. Authorized staff can explicitly edit a particular order; its previous version is preserved in `record_revisions`. Never silently rewrite a past order from a profile edit.

## Customer purchase forms

### Nutrition plan
Collect only what is useful:
- profile/shared data
- age
- height
- weight
- number of training sessions if still required by the current implementation
- food allergy
- food restriction
- supplements
- notes
- up to 6 body photos

### Training plan
Collect:
- profile/shared data
- age
- height
- weight
- goal
- training history
- notes
- up to 6 body photos

The old field "number of available training days per week" was explicitly removed and must NOT be reintroduced.

### Combined plan
Collect the union of the necessary nutrition + training fields without duplicating shared fields or asking the same question twice.

## Photos

Customers can submit **up to 6 body photos per order**.

For body-assessment products, each purchase/renewal starts with no photos. Men must submit four directions (front, back, right, left); women can explicitly continue without photos. The bot requests fresh submissions but cannot prove capture age. Measurements refresh for each purchase; historical photos and measurements remain attached to their original order. Ready-made/channel products without assessment fields are exempt.

The bot should support photo messages and photo-like Telegram documents where the implementation allows it.

Admins should be able to see:
- all customer body photos associated with the buyer/orders
- historical receipt images separately, with their dedicated permission

Do not confuse body photos with payment receipt photos.

## Navigation / Reply Keyboard rules

### Main customer page
The main customer page shows the main menu.

Do NOT show a "🏠 Main menu" button on the actual home/main page.

### Other customer pages
A "🏠 Main menu" option should be available outside the home page so the customer is not trapped.

### Reply Keyboard
The Reply Keyboard should NOT contain a generic "⬅️ Back" button.

Inline navigation can be used when needed.

Reply Keyboard must not become permanently cluttered with all bot actions. Only show context-appropriate options.

When requesting Telegram contact, use a contact-request keyboard. After the contact is received, explicitly remove/replace that keyboard so it does not remain under the next question.

## Back behavior

Do not globally send the customer to home whenever a back action is used.

When a step-by-step edit/back flow exists, it should return to the correct previous step.

Do not reintroduce a generic Reply Keyboard back button.

## Food allergy / restriction behavior

### Allergy
Question: "حساسیت غذایی داری؟"

Use one optional button:
- `⏭️ ندارم`

Do NOT provide a "دارم" button. If the customer has an allergy, they type it themselves.

The `⏭️ ندارم` path must advance to the next state and must work reliably even if the text is localized/variant, for example `ندارم`, `نه`, or the exact displayed button text.

### Restriction
Same concept:
- one optional button: `⏭️ ندارم`
- no "دارم" button
- if the customer has a restriction, they type it themselves

## Order lifecycle

Typical lifecycle:

`awaiting_payment -> paid -> in_progress -> ready -> delivered`

Information recovery: `paid/in_progress -> needs_info -> paid (new response awaiting review) -> in_progress`. Telegram replies use an owned durable request, not general chat. Starting design while `needs_info` is forbidden. Submitting a response resets the assigned followup's seen state.

Additional states can exist such as:
- rejected
- needs_information
- cancelled

Status transitions should be explicit and validated.

## Awaiting-payment cancellation

If a customer has an unpaid order:

Show:
- 💳 Pay
- ❌ Cancel order

When customer selects Cancel:
1. show a confirmation popup / confirmation inline step
2. ask whether they are sure
3. if confirmed, cancel/delete the unpaid order according to financial-audit rules
4. allow a fresh order afterwards

Do not delete successful payment/financial records just to hide them from UI.

## Payments

Production purchases use ZarinPal only. Card-to-card creation, receipt submission and manual approval/rejection are retired, including legacy callbacks. Never convert an existing unverified transfer to paid or erase its history. Historical receipts are view-only with `payments.review`.

Development mock payment is allowed only through the explicit development setting; production never falls back to mock or card transfer.

### ZarinPal
Use proper request -> redirect -> callback -> verify flow.

Never trust client-side success.

Verify on the server using the order's own amount and Authority.

Payment verification must be idempotent:
- duplicate callbacks must not create duplicate successful sales
- the same transaction must not be counted twice

Persist:
- order id
- amount
- authority
- reference id where available
- gateway status
- timestamps

Do not fall back silently to mock payment in production.

## Sensi messaging

There is a two-way messaging feature between Sensi and customers.

### Customer -> Sensi
Customer sends a message; Sensi can see it and reply.

A verified non-cancelled purchase unlocks chat immediately, including custom catalog products and old locked keyboards. Customer live chat saves each valid text/media message without a second send button or automatic exit. Historical unsent drafts require an explicit send/cancel decision; never send them automatically. Additional-information replies remain on their owned order, not this chat.

### Sensi -> Customer
Before the actual message content, customer must receive:

`📩 پیام جدید از طرف سنسی`

Then the Sensi's message content follows.

After sending a reply, clear any temporary Sensi FSM state that would otherwise block other handlers.

Do not allow a customer support/message state to swallow unrelated Sensi/admin actions.

## Sensi panel

The Sensi panel should NOT show a generic "🏠 Main menu" button as a Sensi navigation option.

Typical Sensi actions:
- 🆕 actionable orders
- 📊 sales statistics
- 💬 messages

Sales statistics should be displayed as an invoice/report showing:
- current month sales
- current month order count
- total historical sales
- total historical order count

## Admin panel

The admin home title should be exactly:

`👥 پنل ادمین`

Do NOT show the previous explanatory text:

`دسترسی شما فقط به آمار مالی همین سنسی محدود است.`

Admin panel actions include:
- 📊 sales statistics
- 👥 buyers
- 🏠 main menu (where contextually needed)

### Buyers list
Show only a compact inline list first.

Each page contains max **10 buyer buttons**.

Button label should initially contain:
- name
- gender
- age

When a buyer is clicked, show complete information and all relevant stored files/photos.

Buyer detail may include:
- name
- phone
- Telegram ID
- username
- age
- gender
- height
- weight
- goal
- training history
- allergy
- restriction
- supplements
- notes
- all successful orders
- order amounts
- payment method
- payment reference
- order status
- order timestamps
- historical snapshots
- all body photos
- card-to-card receipt image(s)

Do not expose this detailed data before the buyer button is selected.

## Order time

Store and display order creation time.

Use the configured application timezone for human-readable display while storing timestamps in a consistent database timezone.

## Database rules

PostgreSQL is the source of truth for permanent data.

Redis is for:
- FSM/state
- rate limits
- cache
- short-lived jobs/session data

Do not use Redis as the only storage for important customer/order/payment records.

Historical orders must remain stable even if profile values change.

Every schema change must use Alembic migration.

Never require `docker compose down -v` for normal upgrades because that destroys customer data.

## Security requirements

Production hardening must include:
- role-based authorization
- strict callback ownership checks
- Telegram user ID checks
- rate limiting
- secure file validation
- size limits
- safe filenames / private file storage
- PostgreSQL not publicly exposed
- Redis not publicly exposed
- non-root bot container
- dropped Linux capabilities
- no-new-privileges
- read-only filesystem where practical
- HTTPS for production callbacks/webhooks
- Telegram webhook secret validation
- secure environment secrets
- audit logging for sensitive actions
- idempotent payment handling
- robust exception handling
- no silent mock payment fallback in production
- database backups

Never claim "unhackable". Security should be treated as layered risk reduction.

## Docker / deployment

Expected services:
- bot
- postgres
- redis

Use Docker Compose for local/production-like deployment.

Common upgrade command:

```bash
docker compose down
docker compose up -d --build
```

Never tell the operator to use `docker compose down -v` unless they explicitly want to erase the database.

After deployment, inspect:

```bash
docker compose ps
docker compose logs --tail=100 bot
```

## Debugging rules for future agents

When a bug is reported:

1. Reproduce or inspect the exact failing handler/callback/state path.
2. Fix the root cause, not just the visible symptom.
3. Preserve all existing working behavior unless the user explicitly asks to change it.
4. Avoid rewriting unrelated routers/handlers.
5. Check handler ordering and FSM state collisions carefully.
6. Verify role-specific callbacks before generic callbacks.
7. Test second purchase and repeated purchase flows, not only first-time users.
8. Test payment callbacks more than once to ensure idempotency.
9. Test customer/sensi/admin message routing independently.
10. Add or update regression tests for every fixed bug.
11. Run Python compile checks and automated tests before packaging.
12. Never state that a full runtime Telegram/Docker test was performed unless it actually was.

## Known historical bug patterns to watch

### Handler ordering
A generic customer FSM handler previously swallowed Sensi messages. Role-specific handlers must be registered/filtered correctly.

### Profile reuse / second purchase
A second purchase previously broke because previous state/profile data leaked into the new purchase flow. Every purchase must begin from a clean purchase FSM state while selectively reusing profile data.

### Contact keyboard persistence
Telegram contact-request keyboards can remain visible unless explicitly removed/replaced.

### Allergy/restriction skip buttons
The skip button must update state and advance the FSM. Do not rely only on a generic text handler if an explicit state handler is safer.

### Admin/Sensi callback collisions
Generic callback names such as `home` have previously routed Admin users into the Sensi panel. Use role-specific callback namespaces, e.g. `admin:*`, `sensi:*`, `customer:*`.

### Database startup
The bot must not assume tables exist before migrations. Run Alembic migrations as part of controlled startup/deployment.

## Product prices

Prices are placeholders until the owner supplies final prices.

Current placeholder values may exist in the code, but they must be configurable and not hardcoded into business logic.

## Language / UX

User-facing messages are primarily Persian.

Keep UX simple, fast, and low-friction.

Avoid asking customers for information that is already stored and still valid.

## Important implementation principle

This is a single-Sensi bot, not a multi-tenant platform. Do not add unnecessary multi-Sensi abstractions unless explicitly requested. Keep all role authorization and reporting scoped to the single Sensi configured for the bot.
