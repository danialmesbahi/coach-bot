"""Run in the app container: creates and drops its own disposable PostgreSQL DB.

Telegram calls are faked. No customer, payment, channel, or production record is changed.
"""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import AsyncMock, patch

import asyncpg


async def main():
    original=os.environ['DATABASE_URL']
    name='catalog_test_'+uuid.uuid4().hex[:12]
    admin=await asyncpg.connect(original)
    await admin.execute(f'CREATE DATABASE {name}')
    parts=urlsplit(original)
    os.environ['DATABASE_URL']=urlunsplit((parts.scheme,parts.netloc,'/'+name,parts.query,parts.fragment))
    os.environ['PUBLIC_BASE_URL']='https://downloads.example.test'
    try:
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True)
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
                def clone(self, **_kwargs): return self
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
            assert (await repo.list_sensi_orders(status='paid'))[1]==0,'automatic purchase leaked into manual review'
            rows,total=await repo.list_sensi_orders(status='automatic')
            assert total==1 and rows[0]['delivery_mode']=='channel'
            counts=await repo.sensi_dashboard_counts()
            assert counts['automatic']==1 and counts['new_orders']==0
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
            new=await repo.create_order(tg.id,await repo.get_product(pid),{},'zarinpal',oid)
            assert await repo.mark_zarinpal_paid(new['id'],'test-renewal-ref')
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
            # New terms propagate through purchase, fulfillment, active lists and renewals.
            body.update(title='Lifetime bundle',duration_days=0,duration_unit='lifetime',asset_ids=[asset],asset_id=asset)
            result=await catalog_save(Request(body)); lifetime_id=json.loads(result.text)['id']
            lifetime=await repo.create_order(tg.id,await repo.get_product(lifetime_id),{},'zarinpal')
            await repo.mark_zarinpal_paid(lifetime['id'],'lifetime-ref')
            await fulfillment.fulfill_order(bot,lifetime['id'])
            actual=await repo.get_user_order(lifetime['id'],tg.id)
            assert actual['days_remaining'] is None and not actual['renewal_eligible']
            assert any(o['id']==lifetime['id'] for o in await repo.active_courses(tg.id))
            # Telegram accepts WEBP through sendDocument but may return a sticker.
            # Successful sends must not become an endless automatic redelivery.
            body.update(title='WEBP response regression')
            result=await catalog_save(Request(body)); sticker_product_id=json.loads(result.text)['id']
            sticker_order=await repo.create_order(tg.id,await repo.get_product(sticker_product_id),{},'zarinpal')
            await repo.mark_zarinpal_paid(sticker_order['id'],'sticker-ref')
            sent_before=bot.send_document.await_count
            normal_document=bot.send_document.return_value
            bot.send_document.return_value=SimpleNamespace(document=None,sticker=SimpleNamespace(file_id='sticker-id'))
            await fulfillment.fulfill_order(bot,sticker_order['id'])
            await fulfillment.fulfill_order(bot,sticker_order['id'])
            assert bot.send_document.await_count==sent_before+1
            assert (await repo.get_order(sticker_order['id']))['fulfillment_done']
            bot.send_document.return_value=normal_document
            async with db.acquire() as c:
                second_asset=await c.fetchval("INSERT INTO product_assets(filename,payload,byte_size) VALUES('second.txt',$1,5) RETURNING id",b'hello')
            body.update(title='Two-file bundle',duration_days=14,duration_unit='weeks',asset_ids=[asset,second_asset])
            result=await catalog_save(Request(body)); bundle_id=json.loads(result.text)['id']
            bundle=await repo.create_order(tg.id,await repo.get_product(bundle_id),{},'zarinpal')
            await repo.mark_zarinpal_paid(bundle['id'],'bundle-ref')
            sent_before=bot.send_document.await_count
            bot.send_document.side_effect=[SimpleNamespace(document=SimpleNamespace(file_id='first-checkpoint')),RuntimeError('simulated transport failure')]
            try: await fulfillment.fulfill_order(bot,bundle['id'])
            except RuntimeError: pass
            else: raise AssertionError('test transport failure did not happen')
            bot.send_document.side_effect=None
            await fulfillment.fulfill_order(bot,bundle['id'])
            assert bot.send_document.await_count==sent_before+3,'bundle retry resent the successful first file'
            assert (await repo.get_user_order(bundle['id'],tg.id))['days_remaining']==14
            body.update(title='One-time bundle',duration_days=-1,duration_unit='once',asset_ids=[asset,second_asset],content_url='https://example.test/private')
            result=await catalog_save(Request(body)); once_id=json.loads(result.text)['id']
            once=await repo.create_order(tg.id,await repo.get_product(once_id),{},'zarinpal')
            await repo.mark_zarinpal_paid(once['id'],'once-ref')
            sent_before=bot.send_document.await_count
            await fulfillment.fulfill_order(bot,once['id'])
            await fulfillment.fulfill_order(bot,once['id'])
            assert bot.send_document.await_count==sent_before+2,'one-time bundle did not send both files exactly once'
            await fulfillment.resend_content(bot,await repo.get_user_order(once['id'],tg.id),tg.id)
            assert bot.send_document.await_count==sent_before+2,'completed one-time bundle was sent again'
            assert all(o['id']!=once['id'] for o in await repo.active_courses(tg.id))
            assert not next(p for p in await repo.get_products_for_user(tg.id) if p['id']==once_id)['purchased_before']
            assert not (await repo.get_user_order(once['id'],tg.id))['renewal_eligible']
            from app.services.content import content_link,purchased_content
            from aiohttp import web, CookieJar
            from aiohttp.test_utils import TestClient,TestServer
            async with db.acquire() as c:
                first=await content_link(c,once['id'],second_asset)
                other=await content_link(c,once['id'],second_asset)
            app=web.Application()
            app.router.add_route('*','/content/{token}',purchased_content)
            async with TestClient(TestServer(app),cookie_jar=CookieJar(unsafe=True)) as client:
                path=urlsplit(first).path
                assert (await client.get(path)).status==200,'preview must not consume content'
                assert (await client.get(path+'?download=1')).status==403
                opened=await client.post(path)
                assert opened.status==200 and await opened.read()==b'hello'
                assert (await client.get(path+'?download=1')).status==200,'retry within redemption session'
                assert (await client.post(urlsplit(other).path)).status==410,'second token bypassed one-use rule'
            async with db.acquire() as c:
                assert await content_link(c,once['id'],second_asset) is None,'redeemed grant was reissued'
                # Reordering uses the same list order seen in Telegram, and bumps versions.
                from app.catalog_api import move_product
                async with c.transaction(): await move_product(c,lifetime_id,pid)
                ranked=await c.fetch('SELECT id FROM products WHERE NOT archived ORDER BY sort_order,id')
                ids=[r['id'] for r in ranked]
                assert ids.index(lifetime_id)+1==ids.index(pid)
            # Exercise all duration-dependent production SQL against PostgreSQL.
            await repo.get_products_for_user(tg.id)
            await repo.active_courses(tg.id)
            await repo.renewable_orders(tg.id)
            await repo.sensi_dashboard_counts()
            await repo.list_sensi_orders()
            await repo.get_user_orders(tg.id)
            # Real HTTP multipart -> private storage -> PostgreSQL -> product update.
            # Browser fixtures alone cannot catch upload/API integration errors.
            from aiohttp import FormData
            from tempfile import TemporaryDirectory
            from app import catalog_api,webapp
            @web.middleware
            async def test_actor(request,handler):
                request['actor']={**actor,'role':request.headers.get('Test-Role','platform'),'permissions':[]}
                return await handler(request)
            app=web.Application(middlewares=[webapp.errors,test_actor],client_max_size=10*1024**2)
            app['catalog_upload_slots']=asyncio.Semaphore(2)
            app['read_cache']={}
            app['redis']=SimpleNamespace(incr=AsyncMock(return_value=1),expire=AsyncMock())
            app.add_routes(catalog_api.routes())
            app.router.add_post('/api/orders/{order_id}/action',webapp.order_action)
            # The fixture writes < 20 MB; emulate a roomy test volume without changing the production reserve.
            with TemporaryDirectory() as storage, patch('app.services.content.shutil.disk_usage',return_value=SimpleNamespace(total=100*1024**3,free=90*1024**3)):
                os.environ['CATALOG_STORAGE']=storage
                catalog_api.get_settings().public_base_url=''
                async with TestClient(TestServer(app)) as client:
                    asset_ids=[]
                    for filename,payload in [('large.pdf',b'%PDF-1.4\n'+b'x'*(12*1024**2)),('second.txt',b'hello'),
                                             ('gallery.MOV',b'\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  ')]:
                        form=FormData();form.add_field('file',payload,filename=filename)
                        result=await client.post('/api/catalog-assets',data=form)
                        assert result.status==200,await result.text()
                        asset_ids.append((await result.json())['id'])
                    config=dict(body,title='HTTP multi-file course',duration_days=0,duration_unit='lifetime',content_url='',asset_ids=asset_ids)
                    result=await client.post('/api/catalog',json=config)
                    assert result.status==200,await result.text()
                    http_id=(await result.json())['id']
                    listing=await (await client.get('/api/catalog')).json()
                    saved=next(p for p in listing['items'] if p['id']==http_id)
                    assert len(saved['assets'])==3 and saved['assets'][0]['byte_size']>10*1024**2
                    saved['title']='Updated HTTP course'
                    assert (await client.post(f'/api/catalog/{http_id}',json=saved)).status==200
                    once_config=dict(config,duration_days=-1,duration_unit='once')
                    result=await client.post('/api/catalog',json=once_config)
                    assert result.status==200,await result.text()
                    once_http_id=(await result.json())['id']
                    once_http=await repo.create_order(tg.id,await repo.get_product(once_http_id),{},'zarinpal')
                    await repo.mark_zarinpal_paid(once_http['id'],'http-once-ref')
                    sent_before=bot.send_document.await_count
                    await fulfillment.fulfill_order(bot,once_http['id'])
                    await fulfillment.fulfill_order(bot,once_http['id'])
                    assert bot.send_document.await_count==sent_before+3,'direct delivery incorrectly depends on public base URL'
                    assert (await client.post('/api/catalog',json=dict(once_config,active=False))).status==200
                    assert (await client.post('/api/catalog',json=config,headers={'Test-Role':'staff'})).status==403
                    form=FormData();form.add_field('file',b'not-a-pdf',filename='invalid.pdf')
                    result=await client.post('/api/catalog-assets',data=form)
                    assert result.status==400 and (await result.json())['error']=='invalid_file_type'
                    pending=await repo.create_order(tg.id,await repo.get_product(http_id),{},'zarinpal')
                    await repo.mark_zarinpal_paid(pending['id'],'http-ref')
                    await fulfillment.record_delivery_failure(pending['id'],AttributeError('document'))
                    async with db.acquire() as c:
                        assert await c.fetchval("SELECT fulfillment_next_at='infinity'::timestamptz FROM orders WHERE id=$1",pending['id'])
                    url=f"/api/orders/{pending['id']}/action"
                    assert (await client.post(url,json={'action':'retry_delivery'},headers={'Test-Role':'staff'})).status==403
                    assert (await client.post(url,json={'action':'retry_delivery'})).status==200
                    assert (await client.post(url,json={'action':'retry_delivery'})).status==409
            print('PASS: catalog CRUD, immutable terms, payment idempotency, file fulfillment, channel identity/expiry/renewal, lifetime, one-time redemption/retry, reorder and archive; fake Telegram, isolated DB')
            print('PASS: real HTTP 12 MB + second upload, file validation, create/list/update, role denial and paused-delivery recovery')
        finally:
            await db.close()
    finally:
        await admin.execute(f'DROP DATABASE {name} WITH (FORCE)')
        await admin.close()


asyncio.run(main())
