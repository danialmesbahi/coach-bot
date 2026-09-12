import time
import logging
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis):
        self.redis = redis

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)
        key = f"rl:{user.id}:{int(time.time() // 60)}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, 65)
            if count > settings.rate_limit_per_minute:
                # One warning per bucket; spam must not amplify outbound Telegram traffic.
                if isinstance(event, Message) and count == settings.rate_limit_per_minute + 1:
                    await event.answer('⏳ درخواست‌های زیادی فرستادی. یک دقیقه صبر کن و دوباره تلاش کن.')
                elif isinstance(event, CallbackQuery) and count == settings.rate_limit_per_minute + 1:
                    await event.answer('⏳ کمی صبر کن و دوباره تلاش کن.', show_alert=True)
                return None
        except Exception:
            # Redis is also the FSM backend. Fail closed instead of silently
            # disabling the abuse-control layer when Redis is unavailable.
            log.exception('Rate limiter unavailable; rejecting update')
            if isinstance(event, CallbackQuery):
                await event.answer('⏳ سرویس موقتاً در دسترس نیست. دوباره تلاش کن.', show_alert=True)
            elif isinstance(event, Message):
                await event.answer('⏳ سرویس موقتاً در دسترس نیست. دوباره تلاش کن.')
            return None
        return await handler(event, data)
