import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError,TelegramUnauthorizedError


def test_polling_startup_recovers_with_capped_backoff(monkeypatch):
    from app import main
    network=TelegramNetworkError(method='deleteWebhook',message='offline')
    bot=SimpleNamespace(get_webhook_info=AsyncMock(return_value=SimpleNamespace(url='')),delete_webhook=AsyncMock(side_effect=[network]*6+[True]),me=AsyncMock())
    sleep=AsyncMock()
    monkeypatch.setattr(main,'bot',bot)
    monkeypatch.setattr(main.asyncio,'sleep',sleep)
    asyncio.run(main.prepare_polling())
    assert [call.args[0] for call in sleep.await_args_list]==[5,10,20,40,60,60]
    bot.me.assert_awaited_once()
    assert all(call.kwargs=={'drop_pending_updates':False} for call in bot.delete_webhook.await_args_list)


def test_polling_startup_does_not_retry_credentials_or_cancellation(monkeypatch):
    from app import main
    for error in (TelegramUnauthorizedError(method='deleteWebhook',message='invalid'),asyncio.CancelledError()):
        bot=SimpleNamespace(get_webhook_info=AsyncMock(return_value=SimpleNamespace(url='')),delete_webhook=AsyncMock(side_effect=error),me=AsyncMock())
        monkeypatch.setattr(main,'bot',bot)
        with pytest.raises(type(error)):asyncio.run(main.prepare_polling())
        bot.delete_webhook.assert_awaited_once()


def test_polling_refuses_the_production_bot(monkeypatch):
    from app import main
    bot=SimpleNamespace(get_webhook_info=AsyncMock(return_value=SimpleNamespace(url='https://sensibot.ir/telegram/webhook')),delete_webhook=AsyncMock(),me=AsyncMock())
    monkeypatch.setattr(main,'bot',bot)
    with pytest.raises(RuntimeError,match='test bot token'):asyncio.run(main.prepare_polling())
    bot.delete_webhook.assert_not_awaited()
    monkeypatch.setattr(main.settings,'allow_webhook_takeover',True)
    asyncio.run(main.prepare_polling())
    bot.delete_webhook.assert_awaited_once()


def test_zarinpal_uses_sandbox_outside_production(monkeypatch):
    from app.services import payment
    settings=payment.get_settings()
    monkeypatch.setattr(settings,'app_env','development')
    assert payment.ZarinpalGateway().REQUEST_URL.startswith('https://sandbox.zarinpal.com/')
    assert payment.ZarinpalGateway().START_URL.startswith('https://sandbox.zarinpal.com/')
    monkeypatch.setattr(settings,'app_env','production')
    assert payment.ZarinpalGateway().REQUEST_URL.startswith('https://payment.zarinpal.com/')
