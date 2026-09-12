"""Opt-in integration checks: temporary SQL tables + our own expiring Redis keys.

Never sends Telegram messages, changes real orders or creates browser sessions.
Run inside the API container with PYTHONPATH=/app.
"""
import asyncio
from contextlib import asynccontextmanager

import asyncpg
from redis.asyncio import Redis

from app.config import get_settings
from app.db import repositories as repo
from app.services import web_login, staff


async def main():
    settings = get_settings()
    connection = await asyncpg.connect(settings.database_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    original_db = repo.db
    original_staff_db = staff.db
    challenge = None

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
        for table in ('staff_accounts', 'audit_logs'):
            await connection.execute(f'CREATE TEMP SEQUENCE test_{table}_ids START 100')
            await connection.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('test_{table}_ids')")
        await connection.execute("INSERT INTO staff_accounts(id,telegram_id,username,display_name,role,status,auth_mode) VALUES(1,$1,'test_owner','Owner','platform','active','telegram')", settings.sensi_id)
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
        challenge, proof, _ = await web_login.create(redis)
        assert not await web_login.approve(redis, challenge, -1)
        assert await web_login.approve(redis, challenge, settings.sensi_id)
        assert not await web_login.approve(redis, challenge, settings.sensi_id)
        results = await asyncio.gather(*(web_login.consume(redis, f'{challenge}.{proof}') for _ in range(10)))
        assert results.count(('approved', settings.sensi_id)) == 1
        assert results.count(('expired', None)) == 9
        owner = dict(await connection.fetchrow('SELECT * FROM staff_accounts WHERE id=1'))
        owner['staff_id'] = owner['id']
        created = await staff.team_change(owner, {'action':'create','role':'staff','username':'new_support','display_name':'Support','telegram_id':9000000001,'permissions':['chats.reply']})
        assert 'chats.read' in created['account']['permissions']
        context = await staff.login_context({'username':'new_support','password':'example password only','invite':created['invite']}, asyncio.Semaphore(1))
        active = await staff.finish_login(context, 9000000001)
        assert active['status'] == 'active' and staff.verify_password('example password only', active['password_hash'])
        assert await staff.finish_login(context, 9000000001) is None
        await staff.team_change(owner, {'action':'disable','id':active['id'],'version':active['session_version']})
        assert (await staff.by_telegram(9000000001))['status'] == 'disabled'
        assert await connection.fetchval("SELECT COUNT(*) FROM audit_logs WHERE actor_staff_id=1") == 2
        print('PASS: both payment attempts resolve; settlement once; latest-message SQL; Redis approval/one-use redemption')
        print('PASS: staff creation, permission dependencies, invitation + password activation, one-use redemption, disable and audit')
    finally:
        repo.db = original_db
        staff.db = original_staff_db
        await transaction.rollback()
        await connection.close()
        if challenge:
            await redis.delete(web_login.key(challenge))
        await redis.aclose()


if __name__ == '__main__':
    asyncio.run(main())
