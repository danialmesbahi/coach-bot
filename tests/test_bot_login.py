import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import make_mocked_request

from app import webapp
from app.handlers.web_login import login_request
from app.services import web_login


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, *, ex):
        assert ex == 180
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)

    async def getdel(self, key):
        return self.values.pop(key, None)


def test_browser_binding_expiry_and_single_redemption():
    async def exercise():
        redis = MemoryRedis()
        challenge, proof, code = await web_login.create(redis)
        assert len(code) == 6 and code.isdigit() and len(f"login_{challenge}") <= 64
        cookie = f"{challenge}.{proof}"
        assert await web_login.consume(redis, cookie) == ("pending", None)
        data = json.loads(redis.values[web_login.key(challenge)])
        data["telegram_id"] = webapp.settings.sensi_id
        redis.values[web_login.key(challenge)] = json.dumps(data)
        assert await web_login.consume(redis, f"{challenge}.{'x' * 43}") == ("expired", None)
        results = await asyncio.gather(web_login.consume(redis, cookie), web_login.consume(redis, cookie))
        assert results.count(("approved", webapp.settings.sensi_id)) == 1
        assert results.count(("expired", None)) == 1
        assert await web_login.consume(redis, "bad-cookie") == ("expired", None)
    asyncio.run(exercise())


@pytest.mark.parametrize("state", [{"denied": True}, {"telegram_id": -1}])
def test_denial_or_revoked_role_never_creates_session(state):
    async def exercise():
        redis = MemoryRedis()
        challenge, proof, _ = await web_login.create(redis)
        data = json.loads(redis.values[web_login.key(challenge)])
        data.update(state)
        redis.values[web_login.key(challenge)] = json.dumps(data)
        assert await web_login.consume(redis, f"{challenge}.{proof}") == ("denied", None)
    asyncio.run(exercise())


def test_only_authorized_telegram_sender_can_approve():
    redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    assert not asyncio.run(web_login.approve(redis, "a" * 32, -1))
    redis.eval.assert_not_awaited()
    assert asyncio.run(web_login.approve(redis, "a" * 32, webapp.settings.sensi_id))
    assert "KEEPTTL" in redis.eval.await_args.args[0]
    assert not asyncio.run(web_login.approve(redis, "bad-key", webapp.settings.sensi_id))


def test_start_link_does_not_approve_automatically():
    redis = SimpleNamespace(get=AsyncMock(return_value=json.dumps({"code": "123456"})), eval=AsyncMock())
    message = SimpleNamespace(from_user=SimpleNamespace(id=webapp.settings.sensi_id), answer=AsyncMock())
    asyncio.run(login_request(message, SimpleNamespace(args="login_" + "a" * 32), redis))
    redis.eval.assert_not_awaited()
    assert "123456" in message.answer.await_args.args[0]
    assert len(message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0]) == 2


def test_cross_site_form_and_rate_spam_are_rejected():
    request = make_mocked_request("POST", "/api/auth/bot/start")
    assert asyncio.run(webapp.bot_login(request)).status == 403
    request = make_mocked_request("POST", "/api/auth/bot/start", headers={"X-Login-Request": "1"})
    redis = AsyncMock()
    redis.incr.return_value = 21
    request.app["redis"] = redis
    assert asyncio.run(webapp.bot_login(request)).status == 429
    redis.set.assert_not_awaited()
