# Product catalog and channel subscriptions

Leaders and platform accounts manage **Products / مدیریت دوره‌ها** (`/catalog`). Staff cannot acquire this permission through custom roles.

## Configure a product

- Set title, description, price in Toman, duration and storefront order. A month means exactly 30 days; choose days for other durations.
- Select the required questionnaire fields. Stored static profile details are reused. Body photos remain optional (up to six). Add up to ten free-text custom questions if needed.
- Choose **Custom program**, **Ready-made content**, or **Private channel**.
- Custom programs enter the coach review/design workflow. Ready-made products send a message, HTTPS link, a validated file up to 10 MB, or a combination. Files are stored privately in PostgreSQL and reused via Telegram file IDs after the first send.
- Activate to publish, or keep inactive as a draft. Archive removes the product from sale without deleting previous orders or entitlements.

An order freezes price, title, duration, selected questions and delivery configuration. Changes affect future purchases only. An in-progress questionnaire must be restarted when its product changes before payment. Existing invoices remain payable at their original terms.

## Connect a private channel

1. Use a private channel dedicated to paid membership. Make the bot an administrator with **Invite users** and **Ban/restrict users** rights.
2. In a channel product, enter the channel's numerical `-100…` ID and select **Verify & connect**.
3. Only a verified payment creates an entitlement. The bot sends a time-limited join-request link, checks the Telegram ID against the buyer, approves that account, and consumes/revokes the link. Forwarding the link does not grant access to another account.
4. Renewals extend the remaining subscription in the same channel. Customers can request another invitation through their order's download/access action if the invitation expired.
5. Membership changes are processed immediately. Tracked members are checked every eight hours; expired members are banned unless another current paid entitlement covers that channel. Admins and bots are exempt.

**Telegram limitation:** Bot API cannot enumerate all existing channel members. Use an empty channel for strict membership control; events received after connection and recorded buyers can be managed. Unknown pre-existing members or events Telegram no longer retains cannot be retrospectively enumerated. Removing bot permissions also prevents enforcement; the panel reports failed checks.

## Delivery reliability

Verified payments are processed from a durable PostgreSQL queue, with bounded batches, per-order locks and retry backoff. The worker lives in the bot process. It does not request gateway verification again or count a second sale. Staff receipt approval only applies to card transfers; gateway verification remains server-side.

Telegram does not provide an idempotency key for message sends. A crash after a Telegram send and before transaction commit can resend content; the order and entitlement remain singular. Internal delivery errors appear on the order, and channel errors appear in product settings. No real channel or purchase is created by the automated tests.

## Checks

- `python -m pytest tests/test_catalog.py tests/test_workflow_actions.py`
- `web/tests/catalog-ui.mjs`: mock API, desktop/tablet/mobile, both languages.
- `scripts/verify_catalog.py`: execute in an app container via stdin; creates an isolated temporary database, migrates it, verifies CRUD, immutable purchases, idempotent fulfillment, identity-bound joining, expiry and renewal with a fake Telegram client, then drops only that database.
