"""Exercise payment/work transitions without sending real Telegram messages."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from app import webapp


class Request(dict):
    def __init__(self, body, role="leader"):
        super().__init__(actor={"role": role, "telegram_id": 123})
        self.body = body
        self.match_info = {"order_id": "42"}
        self.app = {"bot": SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=7))), "read_cache": {"orders": "stale"}}

    async def json(self):
        return self.body


@pytest.fixture
def repo(monkeypatch):
    from app.services import client_records
    mocks = {}
    mocks['request_information']=AsyncMock(return_value=12)
    monkeypatch.setattr(client_records,'request_information',mocks['request_information'])
    @asynccontextmanager
    async def acquire():
        yield SimpleNamespace(execute=AsyncMock())
    monkeypatch.setattr(webapp.db,'acquire',acquire)
    for name in ("get_order", "update_order_status", "approve_card_payment", "reject_card_payment", "add_audit", "add_support_message"):
        mocks[name] = AsyncMock(return_value={"id": 42})
        monkeypatch.setattr(webapp.repo, name, mocks[name])
    mocks["get_order"].return_value = {"id":42, "telegram_id":999, "status":"paid", "payment_method":"zarinpal", "payment_status":"paid"}
    return mocks


@pytest.mark.parametrize("message", ["", "  ", None, 13, [], "x" * 1001])
def test_info_validation_happens_before_any_state_change(repo, message):
    request = Request({"action":"needs_info", "message":message})
    result = asyncio.run(webapp.order_action(request))
    assert result.status == 400
    repo["update_order_status"].assert_not_awaited()
    request.app["bot"].send_message.assert_not_awaited()


@pytest.mark.parametrize("action", ["approve_receipt", "reject_receipt"])
def test_gateway_payment_cannot_be_manually_approved_or_rejected(repo, action):
    result = asyncio.run(webapp.order_action(Request({"action":action})))
    assert result.status == 409
    repo["approve_card_payment"].assert_not_awaited()
    repo["reject_card_payment"].assert_not_awaited()


def test_verified_order_can_start_design(repo):
    request = Request({"action":"in_progress"})
    result = asyncio.run(webapp.order_action(request))
    assert result.status == 200
    repo["update_order_status"].assert_awaited_once_with(42, "in_progress")
    assert repo["add_audit"].await_args.args[0] is request["actor"]
    assert request.app["read_cache"] == {}


def test_information_request_is_order_bound_and_not_a_chat_message(repo):
    request = Request({"action":"needs_info", "message":"  Please send your injury history.  "})
    result = asyncio.run(webapp.order_action(request))
    assert json.loads(result.text)["notification_sent"] is True
    repo['request_information'].assert_awaited_once_with(request['actor'],42,'Please send your injury history.')
    repo['add_support_message'].assert_not_awaited()
    markup=request.app['bot'].send_message.await_args.kwargs['reply_markup']
    assert markup.inline_keyboard[0][0].callback_data=='info:12'


def test_failed_notification_reports_saved_state_instead_of_retrying_transition(repo):
    request = Request({"action":"needs_info", "message":"Send photos"})
    request.app["bot"].send_message.side_effect = RuntimeError("Telegram unavailable")
    result = asyncio.run(webapp.order_action(request))
    assert json.loads(result.text) == {"ok":True, "notification_sent":False}
    repo['request_information'].assert_awaited_once()
    repo["add_support_message"].assert_not_awaited()


def test_duplicate_transition_does_not_send_duplicate_notifications(repo):
    repo["update_order_status"].return_value = None
    request = Request({"action":"in_progress"})
    assert asyncio.run(webapp.order_action(request)).status == 409
    request.app["bot"].send_message.assert_not_awaited()


@pytest.mark.parametrize("status", ["awaiting_payment", "paid", "needs_info", "delivered"])
def test_delivery_requires_design_stage(repo, status):
    repo["get_order"].return_value["status"] = status
    assert asyncio.run(webapp.upload_plan(Request({}))).status == 409


def test_team_cannot_execute_coach_actions(repo):
    with pytest.raises(web.HTTPForbidden):
        asyncio.run(webapp.order_action(Request({"action":"in_progress"}, role="admin_team")))


def test_zarinpal_callback_verifies_before_routing_to_information_review(monkeypatch):
    from app import main
    order = {"id":42,"telegram_id":999,"amount":499000,"payment_status":"pending"}
    monkeypatch.setattr(main.repo, "get_order_by_authority", AsyncMock(return_value=order))
    verify = AsyncMock(return_value=SimpleNamespace(success=True, reference_id="verified-42"))
    mark = AsyncMock(return_value={"id":42,"status":"paid"})
    monkeypatch.setattr(main.payment, "verify_zarinpal", verify)
    monkeypatch.setattr(main.repo, "mark_zarinpal_paid", mark)
    monkeypatch.setattr(main.repo, "add_audit", AsyncMock())
    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(main, "bot", bot)
    request = SimpleNamespace(query={"Authority":"test-authority","Status":"OK"}, app={"redis":SimpleNamespace(set=AsyncMock(return_value=True)), "payment_slots":asyncio.Semaphore(4)})
    assert asyncio.run(main.zarinpal_callback(request)).status == 200
    verify.assert_awaited_once_with("test-authority",499000)
    mark.assert_awaited_once_with(42,"verified-42")
    bot.send_message.assert_not_awaited()  # Durable worker uses the purchased delivery mode.
    verify.return_value = SimpleNamespace(success=False)
    mark.reset_mock()
    assert asyncio.run(main.zarinpal_callback(request)).status == 400
    mark.assert_not_awaited()
    order["payment_status"] = "paid"
    verify.reset_mock()
    assert asyncio.run(main.zarinpal_callback(request)).status == 200
    verify.assert_not_awaited()
