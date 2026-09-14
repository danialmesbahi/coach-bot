"""Run in the app container: creates and drops its own disposable PostgreSQL DB.

Telegram calls are faked. No customer, payment, channel, or production record is changed.
"""
import asyncio
import json
import os
import subprocess
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import AsyncMock

import asyncpg


async def main():
    original=os.environ['DATABASE_URL']
    name='catalog_test_'+uuid.uuid4().hex[:12]
    admin=await asyncpg.connect(original)
    await admin.execute(f'CREATE DATABASE {name}')
    parts=urlsplit(original)
    os.environ['DATABASE_URL']=urlunsplit((parts.scheme,parts.netloc,'/'+name,parts.query,parts.fragment))
    try:
        subprocess.run(['alembic','upgrade','head'],check=True)
        from app.db.core import db
        from app.db import repositories as repo
        from app.services import staff, fulfillment
        from app.catalog_api import catalog_save, catalog_archive, catalog
        await db.connect()
        try:
            await staff.bootstrap()
            async with db.acquire() as c:
                actor=dict(await c.fetchrow("SELECT * FROM staff_accounts WHERE role='platform' LIMIT 1"))
                actor['staff_id']=actor['id']
                channel_id=-10099900001
                await c.execute('INSERT INTO managed_channels(chat_id,title) VALUES($1,$2)',channel_id,'Fake test channel')
            class Request(dict):
                def __init__(self,body=None,product_id=None):
                    super().__init__(actor=actor)
                    self.body=body
                    self.app={'read_cache':{}}
                    self.match_info={} if product_id is None else {'product_id':str(product_id)}
                    self.query={}
                async def json(self): return self.body
            body=dict(title='Three-month channel',description='Test',price_irr=250000,duration_days=90,
                      sort_order=20,delivery_mode='channel',form_fields=[],questions=[],response_text='Welcome',
                      content_url='',channel_id=channel_id,asset_id=None,active=True)
            result=await catalog_save(Request(body)); assert result.status==200,result.text
            pid=json.loads(result.text)['id']
            tg=SimpleNamespace(id=991234567,username='catalog_test',first_name='Test',last_name=None)
            await repo.upsert_user(tg)
            p=await repo.get_product(pid)
            order=await repo.create_order(tg.id,p,{},'zarinpal')
            oid=order['id']
            await repo.mark_zarinpal_paid(oid,'test-ref-1')
            assert await repo.mark_zarinpal_paid(oid,'test-ref-1') is None
            bot=SimpleNamespace(send_message=AsyncMock(),unban_chat_member=AsyncMock(),
                create_chat_invite_link=AsyncMock(return_value=SimpleNamespace(invite_link='https://t.me/+fake-test-1')),
                approve_chat_join_request=AsyncMock(),decline_chat_join_request=AsyncMock(),revoke_chat_invite_link=AsyncMock(),
                get_chat_member=AsyncMock(return_value=SimpleNamespace(status='member',user=SimpleNamespace(is_bot=False))),
                ban_chat_member=AsyncMock(),send_document=AsyncMock(return_value=SimpleNamespace(document=SimpleNamespace(file_id='fake-file'))))
            await fulfillment.fulfill_order(bot,oid)
            await fulfillment.fulfill_order(bot,oid)
            assert bot.send_message.await_count==1,'duplicate fulfillment'
            actual=await repo.get_user_order(oid,tg.id)
            assert actual['status']=='delivered' and actual['days_remaining']==90
            # Product edits never change the already purchased amount, title or term.
            body.update(title='Changed title',duration_days=30,price_irr=500000,version=p['version'])
            assert (await catalog_save(Request(body,pid))).status==200
            assert (await catalog_save(Request(body,pid))).status==409,'lost update was not rejected'
            actual=await repo.get_user_order(oid,tg.id)
            assert actual['amount']==250000 and actual['duration_days']==90 and actual['product_title']=='Three-month channel'
            event=SimpleNamespace(chat=SimpleNamespace(id=channel_id),from_user=SimpleNamespace(id=77),invite_link=SimpleNamespace(invite_link='https://t.me/+fake-test-1'))
            await fulfillment.join_request(event,bot)
            bot.decline_chat_join_request.assert_awaited_once_with(channel_id,77)
            event.from_user.id=tg.id
            await fulfillment.join_request(event,bot)
            bot.approve_chat_join_request.assert_awaited_once_with(channel_id,tg.id)
            await fulfillment.join_request(event,bot)
            assert bot.approve_chat_join_request.await_count==1,'consumed invite reused'
            await fulfillment.check_member(bot,channel_id,tg.id)
            bot.ban_chat_member.assert_not_awaited()
            async with db.acquire() as c:
                await c.execute("UPDATE channel_access SET expires_at=NOW()-INTERVAL '1 second' WHERE order_id=$1",oid)
                await c.execute("UPDATE orders SET subscription_expires_at=NOW()-INTERVAL '1 second' WHERE id=$1",oid)
            await fulfillment.check_member(bot,channel_id,tg.id)
            bot.ban_chat_member.assert_awaited_once_with(channel_id,tg.id)
            assert await fulfillment.channel_link(bot,oid,77) is None
            # Renewal is a new purchase at the current terms.
            new=await repo.create_order(tg.id,await repo.get_product(pid),{},'card_to_card',oid)
            await repo.submit_receipt(new['id'],'fake-receipt','photo')
            assert await repo.approve_card_payment(new['id'],actor)
            bot.create_chat_invite_link.return_value=SimpleNamespace(invite_link='https://t.me/+fake-test-2')
            await fulfillment.fulfill_order(bot,new['id'])
            assert (await repo.get_user_order(new['id'],tg.id))['days_remaining']==30
            # Ready-made files are captured by asset ID, delivered once, and retain access after archive.
            async with db.acquire() as c:
                asset=await c.fetchval("INSERT INTO product_assets(filename,payload) VALUES('test.pdf',$1) RETURNING id",b'%PDF-1.4 test')
            body.update(title='Instant PDF',delivery_mode='content',asset_id=asset,channel_id=None)
            response=await catalog_save(Request(body)); pdf_id=json.loads(response.text)['id']
            pdf_order=await repo.create_order(tg.id,await repo.get_product(pdf_id),{},'zarinpal')
            await fulfillment.fulfill_order(bot,pdf_order['id'])
            bot.send_document.assert_not_awaited()
            await repo.mark_zarinpal_paid(pdf_order['id'],'test-ref-pdf')
            await fulfillment.fulfill_order(bot,pdf_order['id'])
            await fulfillment.fulfill_order(bot,pdf_order['id'])
            assert bot.send_document.await_count==1
            assert (await catalog_archive(Request(product_id=pdf_id))).status==200
            assert (await repo.get_order(pdf_order['id']))['plan_file_id']=='fake-file'
            assert all(p['id']!=pdf_id for p in await repo.get_products())
            assert (await catalog(Request())).status==200
            # Exercise all duration-dependent production SQL against PostgreSQL.
            await repo.get_products_for_user(tg.id)
            await repo.active_courses(tg.id)
            await repo.renewable_orders(tg.id)
            await repo.sensi_dashboard_counts()
            await repo.list_sensi_orders()
            await repo.get_user_orders(tg.id)
            print('PASS: catalog CRUD, immutable terms, payment idempotency, file fulfillment, account-bound invite, expiry, renewal and archive; fake Telegram, isolated DB')
        finally:
            await db.close()
    finally:
        await admin.execute(f'DROP DATABASE {name} WITH (FORCE)')
        await admin.close()


asyncio.run(main())
