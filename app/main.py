import asyncio, logging
import hashlib, re
from aiohttp import web
from app import payment_pages as pages
from app.services.payment import payment
from app.db import repositories as repo
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.types import BotCommand
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from redis.asyncio import Redis
from app.config import get_settings
from app.db.core import db
from app.handlers.user import router as user_router
from app.handlers.edit import router as edit_router
from app.middlewares.security import RateLimitMiddleware
from app.services.fulfillment import router as channel_router, run_fulfillment_loop
from app.services.telemetry import BotMetrics, run_telemetry_loop, record
from app.utils.text import money

settings=get_settings(); bot=Bot(settings.bot_token)

async def build_dispatcher(redis):
    dp=Dispatcher(storage=RedisStorage(redis=redis))
    # Check the destination before any child router reads private data or changes FSM state.
    dp.message.filter(F.chat.type == 'private')
    dp.callback_query.filter(F.message.chat.type == 'private')
    dp.message.middleware(RateLimitMiddleware(redis))
    dp.callback_query.middleware(RateLimitMiddleware(redis))
    dp.message.middleware(BotMetrics())
    dp.callback_query.middleware(BotMetrics())
    # Telegram can approve a web login, but exposes no management panel.
    dp['login_redis'] = redis
    dp.include_router(channel_router); dp.include_router(edit_router); dp.include_router(user_router)
    return dp

async def zarinpal_callback(request):
    authority=request.query.get('Authority','')
    status=request.query.get('Status','')
    if not authority or len(authority) > 128 or status.upper() not in {'OK','NOK'}:
        return web.Response(text='اطلاعات پرداخت ناقص است.',status=400)
    # One attempt per authority per 20s, including failures. Fail closed if Redis is down.
    key='payment:verify:' + hashlib.sha256(authority.encode()).hexdigest()
    try:
        acquired=await request.app['redis'].set(key,'1',nx=True,ex=20)
    except Exception:
        return web.Response(text='بررسی پرداخت موقتاً در دسترس نیست.',status=503)
    if not acquired:
        return web.Response(text='بررسی این پرداخت در حال انجام است؛ کمی بعد دوباره تلاش کنید.',status=429,headers={'Retry-After':'20'})
    if request.app['payment_slots'].locked():
        return web.Response(text='درگاه مشغول است؛ کمی بعد دوباره تلاش کنید.',status=503,headers={'Retry-After':'20'})
    try:
        async with asyncio.timeout(18), request.app['payment_slots']:
            result=await _verify_payment_callback(authority,status)
            record('payment','request','verify','server_error' if result.status>=500 else 'client_error' if result.status>=400 else 'ok')
            return result
    except TimeoutError:
        record('payment','request','verify','server_error')
        logging.getLogger(__name__).warning('Payment verification timed out',exc_info=True)
        return web.Response(text='بررسی پرداخت زمان برد؛ کمی بعد دوباره تلاش کنید.',status=503,headers={'Retry-After':'20'})


def _back(label: str, start: str = ''):
    """The bot link resumes the right step."""
    return (label, f'https://t.me/{settings.bot_username}' + (f'?start={start}' if start else ''))


def _order_rows(order, *extra):
    return [('دوره',order.get('product_title')),('مبلغ',money(order['amount']) if order.get('amount') is not None else ''),*extra]


REFUND_NOTE='اگه مبلغی از حسابت کم شده، طبق قوانین بانکی حداکثر تا ۷۲ ساعت بعد به حسابت برمی‌گرده.'
_AUTHORITY=re.compile(r'[A-Za-z0-9_-]{8,128}')


async def payment_redirect(request):
    """Hand the browser to ZarinPal from our own domain; the gateway rejects visitors referred from elsewhere."""
    authority=request.match_info.get('authority','')
    if not _AUTHORITY.fullmatch(authority):
        return pages.page('info','لینک پرداخت نامعتبره','از ربات دوباره «💳 ادامه پرداخت» رو بزن.',action=_back('بازگشت به ربات'),status=404)
    try:
        order=await repo.get_order_by_authority(authority)
    except Exception:
        logging.getLogger(__name__).exception('Payment hand-off lookup failed')
        return pages.page('info','درگاه موقتاً در دسترس نیست','چند لحظه بعد دوباره همین لینک رو باز کن.',status=503,headers={'Retry-After':'20'})
    if not order:
        return pages.page('info','لینک پرداخت پیدا نشد','از ربات دوباره «💳 ادامه پرداخت» رو بزن.',action=_back('بازگشت به ربات'),status=404)
    if order.get('payment_status')=='paid' or order.get('paid_at'):
        return pages.page('success','این سفارش قبلاً پرداخت شده','برای ادامه به ربات برگرد.',rows=_order_rows(order),action=_back('بازگشت به ربات',f"form_{order['id']}"))
    if order.get('status')!='awaiting_payment' or order.get('payment_authority')!=authority:
        # Every new attempt replaces the authority, so an older link can never be paid twice.
        return pages.page('info','این لینک پرداخت منقضی شده','از ربات دوباره «💳 ادامه پرداخت» رو بزن تا لینک تازه ساخته بشه.',
                          rows=_order_rows(order),action=_back('دریافت لینک تازه از ربات',f"pay_{order['id']}"),status=410)
    target=payment.start_url(authority)
    # The navigation from this page carries our origin as the referrer ZarinPal checks.
    return pages.page('redirect','در حال انتقال به درگاه پرداخت','چند لحظه صبر کن؛ خودکار منتقل می‌شی.',
                      rows=_order_rows(order),action=('ورود به درگاه امن پرداخت',target),redirect=target,
                      note='پرداخت از طریق زرین‌پال و شبکه شاپرک انجام می‌شه. اگه درگاه باز نشد، فیلترشکن رو خاموش کن.',
                      headers={'Referrer-Policy':'origin'})


_notices=set()


def _notify_payment_failed(order, authority):
    """Tell the customer once per gateway attempt, off the callback's time budget; a failed attempt never changes the order."""
    if order.get('status')!='awaiting_payment' or not order.get('telegram_id'):
        return
    task=asyncio.create_task(_send_payment_failed(order,authority))
    _notices.add(task); task.add_done_callback(_notices.discard)


async def _send_payment_failed(order, authority):
    try:
        from app.keyboards import payment_failed_kb
        from app.services.fulfillment import send_message_once
        key='failed:'+hashlib.sha256(authority.encode()).hexdigest()[:24]
        await send_message_once(bot,order,key,
            '❌ پرداخت ناموفق بود.\n\nاگر مبلغی از حسابت کم شده، طبق قوانین بانکی حداکثر تا ۷۲ ساعت بعد به حسابت برمی‌گردد. '
            'سفارشت محفوظ است و می‌تونی دوباره پرداخت کنی.',reply_markup=payment_failed_kb(order['id']))
    except Exception:
        logging.getLogger(__name__).warning('Could not send payment failure notice',exc_info=True)


async def _verify_payment_callback(authority, status):
    order=await repo.get_order_by_authority(authority)
    if not order: return pages.page('info','سفارش پیدا نشد','اطلاعات این پرداخت در سامانه پیدا نشد.',action=_back('بازگشت به ربات'),status=404)
    form=f"form_{order['id']}"
    next_step=('برای تکمیل فرم ثبت‌نام به ربات برگرد.' if repo.form_required(repo._json_object(order.get('product_snapshot')))
               else 'دوره‌ت فعال شد؛ ادامه کار توی ربات.')
    retry=_back('بازگشت به ربات و پرداخت دوباره',f"pay_{order['id']}")
    if order.get('payment_status')=='paid' or order.get('paid_at'):
        return pages.page('success','پرداخت قبلاً تأیید شده',next_step,rows=_order_rows(order),action=_back('بازگشت به ربات',form))
    if status.upper()!='OK':
        # A browser return is not proof of cancellation. Never persist attacker-controlled replays.
        _notify_payment_failed(order,authority)
        return pages.page('fail','پرداخت ناموفق بود','پرداخت انجام نشد؛ سفارشت محفوظه و می‌تونی دوباره پرداخت کنی.',rows=_order_rows(order),action=retry,note=REFUND_NOTE)
    try:
        result=await payment.verify_zarinpal(authority,int(order['amount']))
    except Exception:
        logging.getLogger(__name__).exception('Zarinpal verify failed')
        return pages.page('info','بررسی پرداخت انجام نشد','چند دقیقه بعد وضعیت سفارش رو از ربات ببین؛ اگه پرداخت شده باشه خودکار تأیید می‌شه.',
                          rows=_order_rows(order),action=_back('بازگشت به ربات',f"order_{order['id']}"),status=502)
    if not result.success:
        _notify_payment_failed(order,authority)
        return pages.page('fail','پرداخت ناموفق بود','درگاه این پرداخت رو تأیید نکرد؛ سفارشت محفوظه و می‌تونی دوباره پرداخت کنی.',rows=_order_rows(order),action=retry,note=REFUND_NOTE,status=400)
    paid=await repo.mark_zarinpal_paid(order['id'],result.reference_id or authority)
    if paid:
        await repo.add_audit(order['telegram_id'],'zarinpal_paid','order',order['id'],{'reference_id':result.reference_id})
        # The durable fulfillment worker sends the configured response, including on retries.
    return pages.page('success','پرداخت با موفقیت انجام شد',next_step,
                      rows=_order_rows(order,('کد پیگیری',result.reference_id or '-')),action=_back('بازگشت به ربات',form),
                      note='کد پیگیری رو برای پیگیری‌های بعدی نگه دار.')

async def _stop_task(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def run_polling(dp, redis, background_tasks):
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            tasks_concurrency_limit=settings.bot_concurrency,
        )
    finally:
        await _stop_task(background_tasks)
        await redis.aclose(); await db.close(); await bot.session.close()


async def prepare_polling():
    # Retry only transient connection failures; keep the process (and migrations) out of a restart loop.
    delay=5
    while True:
        try:
            info=await bot.get_webhook_info()
            if info.url and not settings.allow_webhook_takeover:
                # deleteWebhook here would silently cut the live bot off from Telegram.
                raise RuntimeError('This BOT_TOKEN has a live webhook, so it is the production bot. '
                                   'Put a separate test bot token in the local .env (see docs/LOCAL_DEV.md).')
            await bot.delete_webhook(drop_pending_updates=False)
            await bot.me()
            return
        except (TelegramNetworkError,TelegramServerError):
            logging.getLogger(__name__).warning('Telegram startup connection unavailable',exc_info=True,extra={'event':'telegram_startup_retry'})
            await asyncio.sleep(delay)
            delay=min(delay*2,60)

async def run_webhook(dp, redis, background_tasks):
    path='/telegram/webhook'
    webhook_url=settings.public_base_url.rstrip('/') + path
    await bot.set_webhook(webhook_url, secret_token=settings.webhook_secret, drop_pending_updates=False, max_connections=40, allowed_updates=dp.resolve_used_update_types())
    app=web.Application()
    app['redis']=redis
    app['payment_slots']=asyncio.Semaphore(4)
    app.router.add_get('/payment/zarinpal/callback', zarinpal_callback)
    app.router.add_get(pages.FONT_URL, pages.font)
    app.router.add_get('/pay/{authority}', payment_redirect)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret, handle_in_background=False).register(app, path=path)
    setup_application(app, dp, bot=bot)
    runner=web.AppRunner(app, access_log=None)
    await runner.setup()
    site=web.TCPSite(runner, host='0.0.0.0', port=8080)
    await site.start()
    logging.getLogger(__name__).info('Webhook server listening on :8080')
    try:
        await asyncio.Event().wait()
    finally:
        await _stop_task(background_tasks)
        await runner.cleanup(); await redis.aclose(); await db.close(); await bot.session.close()

async def main():
    from app.services.diagnostics import configure
    logging.basicConfig(level=getattr(logging,settings.log_level.upper(),logging.INFO),format='%(asctime)s %(levelname)s %(name)s %(message)s')
    configure('bot')
    await db.connect()
    redis=Redis.from_url(settings.redis_url, encoding='utf-8', decode_responses=True)
    await redis.ping()
    production=settings.app_env.lower() == 'production'
    if not production:
        # Before anything touches the bot, so a production token is refused untouched.
        await prepare_polling()
    try:
        await bot.set_my_commands([
            BotCommand(command='start',description='شروع و نمایش پنل'),
            BotCommand(command='menu',description='بازگشت به منوی اصلی'),
            BotCommand(command='help',description='راهنمای کوتاه کار با بات'),
        ])
    except Exception:
        logging.getLogger(__name__).warning('Could not refresh Telegram command menu',exc_info=True)
    dp=await build_dispatcher(redis)
    from app.services.client_archive import run_client_archive_loop
    background_tasks=asyncio.gather(run_fulfillment_loop(bot),run_telemetry_loop('bot'),run_client_archive_loop(bot))
    if production:
        await run_webhook(dp,redis,background_tasks)
    else:
        await run_polling(dp,redis,background_tasks)

if __name__=='__main__': asyncio.run(main())
