"""Bounded event bursts and catalog trust boundaries; no Telegram/DB writes."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from app import catalog_api, webapp


def test_stream_burst_is_bounded_and_permission_filtered(monkeypatch):
    async def run():
        actor = {'role':'staff','staff_id':2,'permissions':['chats.read']}
        check = AsyncMock(side_effect=[actor, None])
        monkeypatch.setattr(webapp, '_session_actor', check)
        app = {'read_cache':{}}
        class Subscribers(set):
            def add(self, queue):
                super().add(queue)
                for i in range(1000):
                    webapp._broadcast_update(app, json.dumps({'table':'support_messages','id':i}))
                webapp._broadcast_update(app, '{"table":"orders","id":42}')
                assert queue.qsize() == 32
        app['realtime_subscribers'] = Subscribers()
        async def write(payload):
            if b'event: update' in payload:
                next(iter(app['realtime_subscribers'])).put_nowait('{"table":"support_messages","id":9999}')
        stream = SimpleNamespace(prepare=AsyncMock(),write=AsyncMock(side_effect=write))
        monkeypatch.setattr(webapp.web,'StreamResponse',lambda **kwargs:stream)
        await webapp.realtime_events(SimpleNamespace(app=app))
        payload = b''.join(call.args[0] for call in stream.write.await_args_list)
        assert check.await_count == 2  # once per batch, including the revoked batch
        assert b'"resync":true' in payload
        assert b'"orders"' not in payload and b'9999' not in payload
        assert b'session-expired' in payload and not app['realtime_subscribers']
        assert payload.count(b'event: update') <= 32
    asyncio.run(run())


def test_catalog_input_size_and_channel_backpressure(monkeypatch):
    async def run():
        @web.middleware
        async def actor(request, handler):
            request['actor'] = {'role':'leader','staff_id':1}
            return await handler(request)
        app = web.Application(middlewares=[actor])
        app.router.add_post('/catalog',catalog_api.catalog_save)
        async with TestClient(TestServer(app)) as client:
            assert (await client.post('/catalog',json={'title':'x'*40000})).status == 413
            assert (await client.post('/catalog',json={'title':''})).status == 400
        monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0
        async def get_chat(_id):
            nonlocal calls
            calls += 1
            if calls == 2: started.set()
            await release.wait()
            raise RuntimeError('fixture: unreachable Telegram')
        class Request(dict):
            def clone(self, *, client_max_size):
                assert client_max_size == 256
                return SimpleNamespace(json=AsyncMock(return_value={'chat_id':-100123}))
        request = Request(actor={'role':'leader','staff_id':1})
        request.app = {'channel_slots':asyncio.Semaphore(2),'bot':SimpleNamespace(get_chat=get_chat)}
        pending = [asyncio.create_task(catalog_api.catalog_channel(request)) for _ in range(2)]
        await asyncio.wait_for(started.wait(),1)
        assert (await catalog_api.catalog_channel(request)).status == 503
        release.set()
        assert all(result.status == 400 for result in await asyncio.gather(*pending))
        assert calls == 2
        monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=True))
        assert (await catalog_api.catalog_channel(request)).status == 429
        assert calls == 2
    asyncio.run(run())
