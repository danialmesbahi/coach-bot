import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from app.config import get_settings
from app.db import repositories as repo

log=logging.getLogger(__name__)

MOTIVATIONAL_MESSAGES=(
    '🏆 امروز فقط یک قدم کوچک بردار؛ استمرار از انگیزه مهم‌تره.',
    '💪 بدنت با تمرین‌های کوچک و پیوسته تغییر می‌کند. ادامه بده.',
    '🌱 لازم نیست کامل باشی؛ فقط از دیروزت یک قدم جلوتر باش.',
    '🔥 یک تمرین خوب می‌تواند حال کل روزت را عوض کند. شروع کن.',
    '🎯 هدفت را به یاد بیاور؛ امروز هم برایش وقت بگذار.',
)


def message_for(user_id: int, day: int, name: str | None = None) -> str:
    message=MOTIVATIONAL_MESSAGES[(user_id + day) % len(MOTIVATIONAL_MESSAGES)]
    return f'{name.strip()} عزیز، {message}' if name and name.strip() else message


async def send_due_motivation(bot):
    settings=get_settings()
    if not settings.motivation_enabled: return 0
    privileged={settings.sensi_id,*settings.admin_team}
    users=await repo.due_motivation_users(settings.motivation_interval_days,settings.motivation_batch_size,privileged)
    day=datetime.now(ZoneInfo(settings.timezone)).toordinal()
    for user in users:
        try:
            await bot.send_message(user['telegram_id'],message_for(user['id'],day,user.get('name') or user.get('first_name')))
        except Exception:
            log.exception('Failed to send motivational message to user=%s',user['id'])
        finally:
            await repo.mark_motivation_sent(user['telegram_id'])
    return len(users)


async def run_motivation_loop(bot):
    settings=get_settings()
    while True:
        try:
            await send_due_motivation(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Motivational-message loop failed')
        await asyncio.sleep(settings.motivation_check_minutes*60)
