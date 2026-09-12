# Coach Telegram Bot

بات برای **یک سنسی و فقط یک بات روی یک سرور** طراحی شده است.

## نقش‌ها

- `customer`: خرید برنامه، پروفایل، سفارش‌ها و «پیام به مربی».
- `sensi`: فقط یک Telegram ID از طریق `SENSI_ID`. مدیریت سفارش‌ها، مشاهده اطلاعات سفارش و ارسال برنامه.
- `admin_team`: یک یا چند Telegram ID از طریق `ADMIN_TEAM_IDS` برای ورود به پنل وب. سهم تیم توسعه با `DEVELOPMENT_TEAM_PERCENT` محاسبه می‌شود و پیش‌فرض ۵۰٪ است. ربات تلگرام هیچ پنل مدیریتی ندارد.

هیچ انتخاب یا تعویض سنسی وجود ندارد و multi-tenant نیست.

## محصولات

- 🥗 برنامه تغذیه — 399,000 تومان placeholder
- 🏋️ برنامه تمرینی — 499,000 تومان placeholder
- 🔥 برنامه غذایی + تمرینی — 799,000 تومان placeholder

قیمت‌ها در دیتابیس هستند و بعداً قابل تغییرند. واحد ذخیره و نمایش «تومان» است؛ نام قدیمی ستون `price_irr` فقط برای سازگاری حفظ شده و سرویس زرین‌پال هنگام request/verify آن را به ریال تبدیل می‌کند.

## راه‌اندازی

1. `.env.example` را به `.env` و `.env.live.example` را به `.env.live` کپی کن؛ مقادیر واقعی را فقط در فایل‌های بدون پسوند example بنویس.
2. `BOT_TOKEN`، `SENSI_ID`، `ADMIN_TEAM_IDS`، passwordهای PostgreSQL/Redis و URLهای آن‌ها را تنظیم کن.
3. برای توسعه:

```bash
docker compose up -d --build
```

پنل مدیریت جدید روی `http://127.0.0.1:8090` اجرا می‌شود. این پنل با Next.js، React، TypeScript و Node.js ساخته شده و API امن، دیتابیس و منطق بات فعلی را بدون دوپلیکیت‌کردن منطق کسب‌وکار استفاده می‌کند.

برای توسعهٔ مستقل رابط کاربری:

```bash
cd web
pnpm install
pnpm dev
```

در این حالت Next.js روی پورت 3000 اجرا می‌شود و درخواست‌های `/api`، `/auth` و `/media` را به `BACKEND_URL` (پیش‌فرض `http://127.0.0.1:8090`) پروکسی می‌کند.

پنل به‌صورت PWA نصب‌شدنی است، حالت روشن/تیره و فارسی/انگلیسی دارد و تغییرات سفارش، پیام و مشتری را از جریان رویدادهای سمت سرور بدون refresh دریافت می‌کند.

راهنمای معماری، تست و تنظیم امن پروکسی: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). فایل‌های `.env` و بکاپ‌ها نباید به GitHub فرستاده شوند.

Migration به‌صورت پیش‌فرض در startup اجرا می‌شود (`MIGRATE_ON_START=true`). اگر ترجیح می‌دهی migration دستی باشد:

```env
MIGRATE_ON_START=false
```

و سپس:

```bash
docker compose run --rm bot alembic upgrade head
docker compose up -d --build bot
```

## توسعه در برابر Production

در development:

```env
APP_ENV=development
PAYMENT_MODE=mock
```

در production:

```env
APP_ENV=production
PAYMENT_MODE=card_to_card  # یا zarinpal / both
PUBLIC_BASE_URL=https://your-domain.example
WEBHOOK_SECRET=<at-least-32-random-characters>
```

Production با Mock Payment بالا نمی‌آید. برای زرین‌پال باید `ZARINPAL_MERCHANT_ID` و برای کارت‌به‌کارت باید `CARD_TO_CARD_BANK_INFO` واقعی تنظیم شود.

Production از Telegram Webhook با HTTPS و Secret Token استفاده می‌کند. پورت داخلی bot فقط روی localhost منتشر شده و PostgreSQL/Redis هیچ port عمومی ندارند.

## امنیت

- Roleها فقط بر اساس Telegram numeric ID هستند.
- Callbackهای حساس role-check و مالکیت سفارش check می‌شوند.
- PostgreSQL و Redis private هستند.
- Redis با password اجرا می‌شود.
- bot با user غیر-root، `cap_drop: ALL` و `no-new-privileges` اجرا می‌شود.
- filesystem bot read-only است و `/tmp` به‌صورت tmpfs است.
- Rate limiting با Redis انجام می‌شود.
- فایل برنامه روی پسوند، MIME، حجم و magic bytes بررسی می‌شود و روی Telegram File ID نگهداری می‌شود؛ فایل روی filesystem دائمی bot ذخیره نمی‌شود.
- اطلاعات سفارش به‌صورت snapshot نگهداری می‌شود تا تغییر پروفایل سفارش‌های قدیمی را خراب نکند.
- مشتری فقط سفارش‌های خودش را می‌تواند مشاهده/دریافت کند.
- تیم توسعه فقط از پنل وب به آمار مالی و جزئیات خریداران دسترسی دارد؛ در تلگرام هیچ callback مدیریتی ثبت نمی‌شود.
- اقدامات حساس سنسی Audit Log می‌شوند.

## Backup

روزانه backup PostgreSQL بگیر و حداقل یک نسخه خارج از VPS نگه دار:

```bash
docker compose exec -T postgres pg_dump -U coach -d coach > backup.sql
```

قبل از migrationهای مهم backup بگیر.

## Nginx

نمونه reverse proxy در `deploy/nginx.conf.example` است. فقط `/telegram/webhook` و `/payment/zarinpal/callback` به bot proxy شوند و سایر مسیرها 404 شوند.

## محدودیت امنیتی

هیچ نرم‌افزاری «غیرقابل هک» نیست. قبل از launch واقعی باید provider پرداخت واقعی، VPS firewall، HTTPS، backup خارج از سرور، monitoring/alerting و تست نفوذ انجام شود.

## v1.2.3 changes
- One shared `notes` field for nutrition/training.
- Removed workout-days question from training form.
- Up to 6 body photos per order.
- Card-to-card receipt review by Sensi.
- Zarinpal request/verify flow with Telegram webhook callback.
- Sensi can deliver PDF/DOCX or an image as the plan.
- Customer notifications for payment approval/rejection and Sensi status changes.

### Payment environment
`PAYMENT_MODE=both`
`ZARINPAL_MERCHANT_ID=...`
`PUBLIC_BASE_URL=https://your-domain.example`
`ZARINPAL_CALLBACK_URL=https://your-domain.example/payment/zarinpal/callback` (optional; defaults from PUBLIC_BASE_URL)
`CARD_TO_CARD_BANK_INFO=...`

For production, HTTPS is required and the webhook must be reachable from Telegram. Do not enable mock payment in production.

### Live activation checklist

- Edit `.env.live` for management IDs, the domain, and gateway credentials. Both Python and Docker load it after `.env`; it is excluded from Git and Docker build contexts. Database/Redis credentials remain in `.env`.
- Set `APP_ENV=production`, `PAYMENT_MODE=zarinpal`, `WEB_DEV_LOGIN=false` in `.env.live` only after completing the configuration.
- Set the actual `ZARINPAL_MERCHANT_ID` privately in `.env.live`, the publicly reachable HTTPS `PUBLIC_BASE_URL`, and a random `WEBHOOK_SECRET` of at least 32 characters.
- The main login button creates a three-minute, single-use browser-bound request. Open the bot, compare the six-digit code, explicitly approve, then return to the same browser/PWA. Only `SENSI_ID` / `ADMIN_TEAM_IDS` can approve; Telegram has no management panel. This flow also works on a local/private panel while the bot uses polling. Deploy both `bot` and `web-api` together.
- The legacy signed widget endpoint `/auth/telegram` still requires registering the panel domain in BotFather; the new bot-approval login does not depend on that widget.
- The Next.js entry point forwards `/payment/zarinpal/callback` and `/telegram/webhook` to `bot:8080`. In production the bot listens there in webhook mode. A private Tailscale Serve address alone is not a public webhook endpoint.
- Rebuild/recreate `bot`, `web-api`, and `web` after activation. Old unverified/test sessions require a fresh Telegram login once test login is disabled.
- Verify login with the actual permitted Telegram account and one real purchase/callback before opening sales. Existing demo orders are not deleted or converted into real payments automatically.
