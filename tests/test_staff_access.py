"""Authorization boundaries and cryptographic login checks (no network)."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from app import webapp
from app.services import staff


def account():
    return dict(id=7, telegram_id=7, username='support', display_name='Support', role='staff',
                permissions=['chats.read', 'chats.reply'], status='active', auth_mode='password', session_version=4)


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
    first = staff.hash_password('Correct horse battery1!')
    assert first != staff.hash_password('Correct horse battery1!')
    assert staff.verify_password('Correct horse battery1!', first)
    assert not staff.verify_password('inCorrect horse battery1!', first)
    assert not staff.verify_password('Correct horse battery1!', 'malformed')
    with pytest.raises(ValueError):
        staff.hash_password('short')


@pytest.mark.parametrize("password", ["short", "abcdefgh1!", "ABCDEFGH!", "Abcdefg1", "Aa1!   ", "A1!" * 44])
def test_password_policy_rejects_weak_passwords(password):
    with pytest.raises(ValueError):
        staff.hash_password(password)


def test_eight_character_password_and_bounded_hashing():
    assert staff.verify_password("Abcdef1!", staff.hash_password("Abcdef1!"))
    with pytest.raises(web.HTTPTooManyRequests):
        asyncio.run(staff.password_work(asyncio.Semaphore(0), staff.hash_password, "Abcdef1!"))


def test_cancelled_hash_keeps_its_slot_until_thread_finishes():
    import threading
    async def run():
        started, release = threading.Event(), threading.Event()
        def worker():
            started.set()
            release.wait(2)
        slots = asyncio.Semaphore(1)
        task = asyncio.create_task(staff.password_work(slots, worker))
        assert await asyncio.to_thread(started.wait, 1)
        try:
            task.cancel()
            await asyncio.sleep(0)
            assert slots.locked()
            with pytest.raises(web.HTTPTooManyRequests):
                await staff.password_work(slots, lambda: None)
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not slots.locked()
    asyncio.run(run())


def test_session_revocation_and_media_permission_enforced(monkeypatch):
    async def run():
        current = account()
        monkeypatch.setattr(staff, 'by_id', AsyncMock(return_value=current))
        redis = AsyncMock()
        redis.get.return_value=json.dumps({'telegram_id':7,'staff_id':7,'version':4,'csrf':'test','auth_method':'password'})
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


def test_customer_reader_can_leave_and_claim_profile_followup(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def transaction():
        yield

    connection = SimpleNamespace(
        transaction=transaction,
        fetchval=AsyncMock(return_value=9),
        fetchrow=AsyncMock(return_value=None),
        fetch=AsyncMock(return_value=[]),
        execute=AsyncMock(),
    )

    @asynccontextmanager
    async def acquire():
        yield connection

    class Request(dict):
        method = 'POST'
        match_info = {'kind': 'customer', 'target_id': '9'}

        def __init__(self, body):
            super().__init__(actor=dict(role='staff', staff_id=4, display_name='Designer', permissions=['customers.read']))
            self.body = body

        async def json(self):
            return self.body

    monkeypatch.setattr(webapp.db, 'acquire', acquire)
    assert asyncio.run(webapp.collaboration(Request({'action': 'note', 'text': 'Check posture'}))).status == 200
    assert any('INSERT INTO staff_notes' in call.args[0] for call in connection.execute.await_args_list)
    connection.fetchrow.side_effect = [
        {'id': 4, 'role': 'staff', 'permissions': ['customers.read']},
        {'staff_id': None, 'version': 1},
        {'staff_id': 4, 'version': 2, 'display_name': 'Designer'},
    ]
    assert asyncio.run(webapp.collaboration(Request({'action': 'assign', 'staff_id': 4, 'version': 1}))).status == 200


def test_followup_seen_only_updates_current_assignee(monkeypatch):
    from contextlib import asynccontextmanager
    connection = SimpleNamespace(fetchval=AsyncMock(side_effect=[9, None]))

    @asynccontextmanager
    async def acquire():
        yield connection

    class Request(dict):
        match_info = {'kind': 'thread', 'target_id': '9'}

        def __init__(self):
            super().__init__(actor=dict(role='staff', staff_id=4, permissions=['chats.read']))

    monkeypatch.setattr(webapp.db, 'acquire', acquire)
    assert asyncio.run(webapp.followup_seen(Request())).status == 200
    assert connection.fetchval.await_args.args[-1] == 4
    with pytest.raises(web.HTTPNotFound):
        asyncio.run(webapp.followup_seen(Request()))
