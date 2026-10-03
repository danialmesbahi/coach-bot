from asyncio import Lock
from weakref import WeakValueDictionary
import json

from aiogram.exceptions import TelegramBadRequest


MAX_BODY_PHOTOS = 6

# ponytail: in-process per-user locks are enough for the single bot worker; use a Redis lock if replicas are added.
_locks: WeakValueDictionary[int, Lock] = WeakValueDictionary()


def photo_lock(user_id: int) -> Lock:
    key = int(user_id)
    lock = _locks.get(key)
    if lock is None:
        lock = Lock()
        _locks[key] = lock
    return lock


def append_photo(photos: list, photo: dict) -> tuple[list, bool]:
    """Append one draft photo without ever replacing an earlier one."""
    current = list(photos)
    if len(current) >= MAX_BODY_PHOTOS:
        return current, False
    return current + [photo], True


def normalize_photos(raw) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = [raw]
    result=[]
    for item in raw or []:
        if isinstance(item, dict):
            file_id=item.get('file_id')
            kind=item.get('type', 'photo')
            if (file_id or item.get('client_file_id')) and kind in {'photo', 'document'}:
                result.append({**item, 'file_id': file_id, 'type': kind})
        elif item:
            result.append({'file_id': item, 'type': 'photo'})
        if len(result) == MAX_BODY_PHOTOS:
            break
    return result


def stored_photos(raw) -> list[dict]:
    return [{key:item[key] for key in ('file_id','client_file_id','type','direction','captured_at') if key in item} for item in normalize_photos(raw)]


async def edit_photo_status(bot, chat_id: int, message_id: int | None, text: str) -> bool:
    if not message_id:
        return False
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
        return True
    except TelegramBadRequest as exc:
        return 'message is not modified' in str(exc).lower()


async def delete_photo_message(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass


async def delete_draft_photos(bot, chat_id: int, photos):
    for item in normalize_photos(photos):
        await delete_photo_message(bot, chat_id, item.get('message_id'))
