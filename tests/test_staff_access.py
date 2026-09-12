"""Authorization boundaries and cryptographic login checks (no network)."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from app import webapp
from app.services import staff, web_login


def account():
    return dict(id=7, telegram_id=7, username='support', display_name='Support', role='staff',
                permissions=['chats.read', 'chats.reply'], status='active', auth_mode='password_telegram', session_version=4)


def test_delivery_does_not_send_when_another_worker_holds_order(monkeypatch):
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def transaction():
        yield
    c = SimpleNamespace(transaction=transaction, fetchval=AsyncMock(return_value=False))
    @asynccontextmanager
    async def acquire():
        yield c
    monkeypatch.setattr(webapp.db, 'acquire', acquire)
    monkeypatch.setattr(webapp.repo, 'get_order', AsyncMock(return_value={'id':42,'status':'in_progress'}))
    send=AsyncMock()
    monkeypatch.setattr(webapp, '_upload_plan', send)
    request=make_mocked_request('POST','/api/orders/42/plan', match_info={'order_id':'42'})
    request['actor']={'role':'leader'}
    request.app['upload_slots']=asyncio.Semaphore(4)
    assert asyncio.run(webapp.upload_plan(request)).status == 409
    send.assert_not_awaited()


def test_role_hierarchy_and_capability_dependencies():
    support = account()
    assert staff.can(support, 'chats.reply') and not staff.can(support, 'team')
    assert not staff.can(support, 'orders.deliver') and not staff.can(support, 'sales.read')
    assert staff.can({'role': 'leader'}, 'orders.deliver')
    assert not staff.manageable({'role': 'leader'}, 'platform')
    assert not staff.manageable({'role': 'leader'}, 'leader')
    assert staff.manageable({'role': 'platform'}, 'leader')
    assert staff.validate_permissions(['orders.deliver']) == ['orders.deliver', 'orders.read']
    for invalid in (['team'], ['platform'], ['unknown'], [None], 'sales.read'):
        with pytest.raises(ValueError):
            staff.validate_permissions(invalid)


def test_password_hashes_are_salted_and_fail_closed():
    first = staff.hash_password('correct horse battery')
    assert first != staff.hash_password('correct horse battery')
    assert staff.verify_password('correct horse battery', first)
    assert not staff.verify_password('incorrect horse battery', first)
    assert not staff.verify_password('correct horse battery', 'malformed')
    with pytest.raises(ValueError):
        staff.hash_password('short')


def test_password_accounts_cannot_bypass_password_via_telegram(monkeypatch):
    monkeypatch.setattr(staff, 'by_telegram', AsyncMock(return_value=account()))
    assert not asyncio.run(web_login.allowed(7, {'context': {}}))
    assert not asyncio.run(web_login.allowed(7, {'context': {'target': 8, 'version':4}}))
    assert not asyncio.run(web_login.allowed(7, {'context': {'target': 7, 'version':3}}))
    assert asyncio.run(web_login.allowed(7, {'context': {'target': 7, 'version':4}}))
    with pytest.raises(web.HTTPForbidden):
        asyncio.run(webapp._new_session(SimpleNamespace(app={'redis':AsyncMock()}), 7))


def test_session_revocation_and_media_permission_enforced(monkeypatch):
    async def run():
        current = account()
        monkeypatch.setattr(staff, 'by_telegram', AsyncMock(return_value=current))
        redis = AsyncMock()
        redis.get.return_value=json.dumps({'telegram_id':7,'staff_id':7,'version':4,'csrf':'test','auth_method':'password_telegram'})
        redis.incr.return_value=1
        request=make_mocked_request('GET','/media/orders/1/receipt',headers={'Cookie':'sensi_session=test'})
        request.app['redis']=redis
        with pytest.raises(web.HTTPForbidden):
            await webapp.auth(request, webapp.order_receipt)
        current['session_version']=5
        assert await webapp._session_actor(request) is None
        redis.delete.assert_awaited()
    asyncio.run(run())


def test_all_authenticated_handlers_have_explicit_policy():
    # New handlers must be added to the allowlist before they can serve staff data.
    assert staff.ROUTE_PERMISSIONS['support_message_media'] == 'chats.read'
    assert staff.ROUTE_PERMISSIONS['upload_plan'] == 'orders.deliver'
    assert staff.ROUTE_PERMISSIONS['staff_team'] == 'team'
    assert 'unknown_handler' not in staff.ROUTE_PERMISSIONS
