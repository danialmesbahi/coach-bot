"""Opt-in integration checks: temporary SQL tables + our own expiring Redis keys.

Never sends Telegram messages, changes real orders or creates browser sessions.
Run inside the API container with PYTHONPATH=/app.
"""
import asyncio
from contextlib import asynccontextmanager

import asyncpg
from aiohttp import web
from redis.asyncio import Redis

from app.config import get_settings
from app.db import repositories as repo
from app.services import staff


async def main():
    settings = get_settings()
    connection = await asyncpg.connect(settings.database_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    assert await redis.ping()
    original_db = repo.db
    original_staff_db = staff.db

    class TemporaryDatabase:
        @asynccontextmanager
        async def acquire(self):
            yield connection

    transaction = connection.transaction()
    await transaction.start()
    try:
        # Temporary tables shadow public names only on this dedicated connection.
        # Explicit IDs avoid consuming production sequences from copied defaults.
        for table in ('users', 'products', 'orders', 'support_messages', 'staff_accounts', 'staff_invites', 'audit_logs'):
            await connection.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING INDEXES) ON COMMIT DROP')
        # Test inserts never advance public sequences.
        for table in ('staff_accounts', 'audit_logs', 'support_messages'):
            await connection.execute(f'CREATE TEMP SEQUENCE test_{table}_ids START 1000')
            await connection.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('test_{table}_ids')")
        await connection.execute("INSERT INTO staff_accounts(id,telegram_id,username,display_name,role,status,auth_mode) VALUES(1,$1,'test_owner','Owner','platform','active','password')", settings.sensi_id)
        await connection.execute('CREATE TEMP TABLE payment_attempts(authority TEXT PRIMARY KEY, order_id BIGINT NOT NULL) ON COMMIT DROP')
        await connection.execute("INSERT INTO users(id,telegram_id,name) VALUES(1,1,'Integration test')")
        await connection.execute("INSERT INTO products(id,code,title,description,price_irr) VALUES(1,'test','Test','Test',100)")
        await connection.execute("INSERT INTO orders(id,user_id,product_id,amount,status,form_snapshot,payment_method,payment_status) VALUES(1,1,1,100,'awaiting_payment','{}','zarinpal','pending')")
        await connection.execute("INSERT INTO support_messages(id,user_id,message_id,sender_telegram_id,content_text,direction) SELECT n,1,n,1,n::text,'customer' FROM generate_series(1,100) n")
        repo.db = TemporaryDatabase()
        staff.db = TemporaryDatabase()
        await repo.set_zarinpal_authority(1, 'first-test-attempt')
        await repo.set_zarinpal_authority(1, 'second-test-attempt')
        assert (await repo.get_order_by_authority('first-test-attempt'))['id'] == 1
        assert (await repo.get_order_by_authority('second-test-attempt'))['id'] == 1
        rows, total = await repo.support_threads()
        assert total == 1 and rows[0]['message_count'] == 100
        assert rows[0]['last_content_text'] == '100'
        assert await repo.mark_zarinpal_paid(1, 'test-reference')
        assert await repo.mark_zarinpal_paid(1, 'test-reference') is None
        await connection.execute("UPDATE orders SET status='cancelled' WHERE id=1")
        assert await repo.mark_zarinpal_paid(1, 'different-reference') is None
        assert await connection.fetchval('SELECT gateway_ref FROM orders WHERE id=1') == 'test-reference'
        try:
            await repo.set_zarinpal_authority(1, 'late-test-attempt')
        except ValueError:
            pass
        else:
            raise AssertionError('A settled order must not publish another payment link')
        slots = asyncio.Semaphore(2)
        owner = dict(await connection.fetchrow('SELECT * FROM staff_accounts WHERE id=1'))
        owner.update(staff_id=owner['id'], version=owner['session_version'])
        created = await staff.team_change(owner, {'action':'create','role':'staff','username':'new_support','display_name':'Support','password':'Example1!','permissions':['chats.reply']}, slots)
        leader_result = await staff.team_change(owner, {'action':'create','role':'leader','username':'new_leader','display_name':'Leader','password':'Leader1!','permissions':[]}, slots)
        leader = leader_result['account']
        leader.update(staff_id=leader['id'], version=leader['session_version'])
        for target in (owner, leader):
            try:
                await staff.team_change(leader, {'action':'reset_password','id':target['id'],'version':target['session_version'],'password':'Resetpass3!'}, slots)
            except web.HTTPForbidden:
                pass
            else:
                raise AssertionError('Leaders may not reset themselves or platform owners')
        assert 'chats.read' in created['account']['permissions']
        assert created['account']['telegram_id'] is None
        active = await staff.authenticate({'username':'NEW_SUPPORT','password':'Example1!'}, slots)
        assert active['status'] == 'active'
        active.update(staff_id=active['id'], version=active['session_version'])
        await repo.add_support_message(1, 101, direction='sensi', sender_telegram_id=active, content_text='Staff reply')
        message = await connection.fetchrow('SELECT * FROM support_messages WHERE message_id=101')
        assert message['sender_telegram_id'] is None and message['sender_staff_id'] == active['id']
        assert message['sender_name'] == 'Support'
        await repo.add_audit(active, 'test_action', 'order', 1)
        log = await connection.fetchrow("SELECT * FROM audit_logs WHERE action='test_action'")
        assert log['actor_staff_id'] == active['id'] and log['actor_telegram_id'] is None
        try:
            await staff.change_password(active, {'current_password':'wrong','password':'Newpass2!'}, slots)
        except web.HTTPUnauthorized:
            pass
        else:
            raise AssertionError('Changing a password requires the current password')
        await staff.change_password(active, {'current_password':'Example1!','password':'Newpass2!'}, slots)
        current = await staff.by_id(active['id'])
        assert current['session_version'] == active['session_version'] + 1
        assert not staff.verify_password('Example1!', current['password_hash'])
        current.update(staff_id=current['id'], version=current['session_version'])
        for target in (owner, current):
            try:
                await staff.team_change(current, {'action':'reset_password','id':target['id'],'version':target['session_version'],'password':'Resetpass3!'}, slots)
            except web.HTTPForbidden:
                pass
            else:
                raise AssertionError('Staff may not reset any account')
        reset = await staff.team_change(leader, {'action':'reset_password','id':current['id'],'version':current['session_version'],'password':'Resetpass3!'}, slots)
        assert reset['account']['session_version'] == current['session_version'] + 1
        try:
            await staff.team_change(leader, {'action':'reset_password','id':current['id'],'version':current['session_version'],'password':'Stale1!!'}, slots)
        except web.HTTPConflict:
            pass
        else:
            raise AssertionError('Stale password resets must not overwrite the new password')
        logged_in = await staff.authenticate({'username':'new_support','password':'Resetpass3!'}, slots)
        await staff.team_change(owner, {'action':'disable','id':logged_in['id'],'version':logged_in['session_version']}, slots)
        disabled = await staff.by_id(logged_in['id'])
        reset_disabled = await staff.team_change(leader, {'action':'reset_password','id':disabled['id'],'version':disabled['session_version'],'password':'Resetpass3!'}, slots)
        assert reset_disabled['account']['status'] == 'disabled'
        try:
            await staff.authenticate({'username':'new_support','password':'Resetpass3!'}, slots)
        except web.HTTPUnauthorized:
            pass
        else:
            raise AssertionError('Disabled accounts cannot log in')
        assert await connection.fetchval("SELECT COUNT(*) FROM audit_logs WHERE actor_staff_id=1") == 3
        assert not await connection.fetchval("SELECT EXISTS(SELECT 1 FROM audit_logs WHERE metadata::text LIKE '%pass3%')")
        print('PASS: payment idempotency; latest-message SQL; password-only creation/login/change/reset/disable; stable attribution without Telegram')
    finally:
        repo.db = original_db
        staff.db = original_staff_db
        await transaction.rollback()
        await connection.close()
        await redis.aclose()


if __name__ == '__main__':
    asyncio.run(main())
