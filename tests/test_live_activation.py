import asyncio
import json
from contextlib import AbstractAsyncContextManager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from app import webapp
from app.config import Settings
from app.services import payment


def test_live_file_overrides_base_configuration(tmp_path, monkeypatch):
    for key in ("SENSI_ID", "ADMIN_TEAM_IDS", "PAYMENT_MODE", "WEB_DEV_LOGIN"):
        monkeypatch.delenv(key, raising=False)
    base = tmp_path / ".env"
    live = tmp_path / ".env.live"
    base.write_text("SENSI_ID=1\nPAYMENT_MODE=mock\nWEB_DEV_LOGIN=true\n", encoding="utf-8")
    live.write_text("SENSI_ID=2\nADMIN_TEAM_IDS=3,4\nPAYMENT_MODE=zarinpal\nWEB_DEV_LOGIN=false\n", encoding="utf-8")
    settings = Settings(_env_file=(base, live), bot_token="123:token",
                        database_url="postgresql://db", redis_url="redis://cache")
    assert settings.sensi_id == 2 and settings.admin_team == {3, 4}
    assert settings.payment_mode == "zarinpal" and not settings.web_dev_login


@pytest.mark.parametrize("method,expected", [(None, 401), ("development", 401), ("telegram", 401), ("password_telegram", 401), ("password", 200)])
def test_disabling_test_login_revokes_test_and_legacy_sessions(monkeypatch, method, expected):
    monkeypatch.setattr(webapp.settings, "web_dev_login", False)
    actor = {"telegram_id": webapp.settings.sensi_id, "staff_id": 1, "version": 1, "csrf": "test"}
    account = {'id':1,'telegram_id':webapp.settings.sensi_id,'username':'leader','display_name':'Leader','role':'leader','permissions':[],'status':'active','auth_mode':'password','session_version':1}
    monkeypatch.setattr(webapp.staff, 'by_id', AsyncMock(return_value=account))
    if method:
        actor["auth_method"] = method
    redis = AsyncMock()
    redis.get.return_value = json.dumps(actor)
    redis.incr.return_value = 1
    request = make_mocked_request("GET", "/api/session", headers={"Cookie": "sensi_session=test"})
    request.app["redis"] = redis
    result = asyncio.run(webapp.auth(request, webapp.session))
    assert result.status == expected
    assert redis.delete.await_count == (expected == 401)


def test_real_login_session_is_bound_to_staff_id():
    redis = AsyncMock()
    request = SimpleNamespace(app={"redis": redis})
    asyncio.run(webapp._new_session(request, {'id': 8, 'session_version': 3}))
    data = json.loads(redis.setex.await_args.args[2])
    assert data["auth_method"] == "password"
    assert data["staff_id"] == 8 and data["version"] == 3
    assert "telegram_id" not in data


def test_production_rejects_insecure_payment_return_url():
    settings = Settings(_env_file=None, bot_token="123:token", database_url="postgresql://db",
                        redis_url="redis://cache", sensi_id=1, app_env="production",
                        web_dev_login=False, payment_mode="zarinpal", webhook_secret="x" * 32,
                        public_base_url="https://example.com", zarinpal_merchant_id="configured",
                        zarinpal_callback_url="http://example.com/payment/zarinpal/callback")
    with pytest.raises(RuntimeError, match="ZARINPAL_CALLBACK_URL"):
        settings.validate_runtime()


@pytest.mark.parametrize("code,success", [(100, True), (-9, False), (None, False)])
def test_gateway_request_requires_explicit_success_code(monkeypatch, code, success):
    class Context(AbstractAsyncContextManager):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        status = 200

        async def json(self, **kwargs):
            return {"data": {"code": code, "authority": "test-authority"}}

        def post(self, url, *, json):
            assert json["amount"] == 3990000
            return self

    monkeypatch.setattr(payment.aiohttp, "ClientSession", lambda **kwargs: Context())
    gateway = payment.ZarinpalGateway()
    gateway.merchant_id = "test-merchant"
    gateway.callback = "https://example.com/payment/zarinpal/callback"
    assert asyncio.run(gateway.create(42, 399000, "Test")).success is success
