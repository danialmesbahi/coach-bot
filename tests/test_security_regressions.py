import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message, Chat, User, CallbackQuery
from aiohttp.test_utils import make_mocked_request

from app import main, webapp
from app.handlers import user
from app.utils.media import BoundedBuffer


def test_private_chat_boundary_blocks_groups_and_inline_callbacks(monkeypatch):
    async def run():
        redis = AsyncMock()
        redis.incr.return_value = 1
        dispatcher = await main.build_dispatcher(redis)
        profile = AsyncMock()
        monkeypatch.setattr(user, 'show_profile', profile)
        monkeypatch.setattr(user.repo, 'get_user', AsyncMock(return_value={'id': 1}))
        monkeypatch.setattr(user.repo, 'upsert_user', AsyncMock())

        async def finish(_message, work):
            return await work

        monkeypatch.setattr(user, '_finish_deep_link', finish)
        actor = User(id=123, is_bot=False, first_name='Customer')
        for kind in ('group', 'supergroup', 'private'):
            message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=123 if kind == 'private' else -123, type=kind), from_user=actor, text='/start profile')
            await dispatcher.propagate_event('message', message, state=AsyncMock(), bot=SimpleNamespace())
            assert profile.await_count == int(kind == 'private')
        for kind in ('group', 'supergroup'):
            message = Message(message_id=2, date=datetime.now(timezone.utc), chat=Chat(id=-123, type=kind), from_user=actor)
            callback = CallbackQuery(id='callback', from_user=actor, chat_instance='chat', message=message, data='profile')
            await dispatcher.propagate_event('callback_query', callback, state=AsyncMock())
        callback = CallbackQuery(id='inline', from_user=actor, chat_instance='chat', inline_message_id='inline', data='profile')
        await dispatcher.propagate_event('callback_query', callback, state=AsyncMock())
        assert profile.await_count == 1
        user.repo.get_user.assert_awaited_once()
    asyncio.run(run())


def test_payment_replays_and_gateway_concurrency_are_bounded(monkeypatch):
    async def run():
        seen = set()

        async def acquire(key, _value, **options):
            assert options == {'nx': True, 'ex': 20}
            if key in seen:
                return False
            seen.add(key)
            return True

        order = {'id': 42, 'amount': 100, 'telegram_id': 7}
        monkeypatch.setattr(main.repo, 'get_order_by_authority', AsyncMock(return_value=order))
        audit = AsyncMock()
        monkeypatch.setattr(main.repo, 'add_audit', audit)
        verify = AsyncMock(return_value=SimpleNamespace(success=False))
        monkeypatch.setattr(main.payment, 'verify_zarinpal', verify)
        app = {'redis': SimpleNamespace(set=acquire), 'payment_slots': asyncio.Semaphore(4)}
        request = SimpleNamespace(query={'Authority': 'known', 'Status': 'OK'}, app=app)
        results = await asyncio.gather(*(main.zarinpal_callback(request) for _ in range(50)))
        assert sum(r.status == 400 for r in results) == 1
        assert sum(r.status == 429 for r in results) == 49
        verify.assert_awaited_once_with('known', 100)
        request.query = {'Authority': 'cancelled', 'Status': 'NOK'}
        assert (await main.zarinpal_callback(request)).status == 200
        audit.assert_not_awaited()
        app['payment_slots'] = asyncio.Semaphore(0)
        request.query = {'Authority': 'another', 'Status': 'OK'}
        assert (await main.zarinpal_callback(request)).status == 503
    asyncio.run(run())


def test_established_stream_stops_after_logout(monkeypatch):
    class Subscribers(set):
        def add(self, queue):
            super().add(queue)
            queue.put_nowait('{"id":1}')
            queue.put_nowait('{"id":2}')

    async def run():
        actor = {'telegram_id':webapp.settings.sensi_id, 'role':'leader', 'staff_id':1, 'version':1, 'auth_method':'password', 'csrf':'test'}
        monkeypatch.setattr(webapp.staff, 'by_id', AsyncMock(return_value={'id':1,'telegram_id':webapp.settings.sensi_id,'username':'leader','display_name':'Leader','role':'leader','permissions':[],'status':'active','auth_mode':'password','session_version':1}))
        redis = SimpleNamespace(get=AsyncMock(side_effect=[json.dumps(actor), None]))
        stream = SimpleNamespace(prepare=AsyncMock(), write=AsyncMock())
        monkeypatch.setattr(webapp.web, 'StreamResponse', lambda **kwargs: stream)
        request = make_mocked_request('GET', '/api/events', headers={'Cookie':'sensi_session=example'})
        subscribers = Subscribers()
        request.app['redis'] = redis
        request.app['realtime_subscribers'] = subscribers
        await webapp.realtime_events(request)
        writes = b''.join(call.args[0] for call in stream.write.await_args_list)
        assert b'{"id":1}' in writes and b'{"id":2}' not in writes
        assert not subscribers
    asyncio.run(run())


@pytest.mark.parametrize('payload,valid', [(b'\x89PNG\r\n\x1a\nimage', True), (b'MZfake', False)])
def test_receipt_documents_validate_actual_bytes(payload, valid):
    async def download(_document, *, destination, timeout):
        destination.write(payload)

    message = SimpleNamespace(document=SimpleNamespace(file_name='receipt.png', file_size=len(payload)), bot=SimpleNamespace(download=download))
    assert asyncio.run(user._valid_image_document(message)) is valid


def test_media_buffer_rejects_oversize_before_retaining_it():
    buffer = BoundedBuffer(4)
    buffer.write(b'1234')
    with pytest.raises(ValueError):
        buffer.write(b'5')
    assert buffer.getvalue() == b'1234'
