"""Disposable PostgreSQL integration check; Telegram is entirely mocked."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import AsyncMock, patch
import asyncpg
from aiohttp import web, FormData
from aiohttp.test_utils import TestClient, TestServer


async def main():
    original=os.environ['DATABASE_URL']
    name='workflow_test_'+uuid.uuid4().hex[:12]
    admin=await asyncpg.connect(original)
    await admin.execute(f'CREATE DATABASE {name}')
    parts=urlsplit(original)
    os.environ['DATABASE_URL']=urlunsplit((parts.scheme,parts.netloc,'/'+name,parts.query,parts.fragment))
    try:
        subprocess.run([sys.executable,'-m','alembic','upgrade','0024_delivery_and_broadcasts'],check=True)
        legacy=await asyncpg.connect(os.environ['DATABASE_URL'])
        try:
            legacy_user=await legacy.fetchval("INSERT INTO users(telegram_id,name) VALUES(998812346,'Legacy client') RETURNING id")
            legacy_product=await legacy.fetchval('SELECT id FROM products ORDER BY id LIMIT 1')
            legacy_order=await legacy.fetchval("INSERT INTO orders(user_id,product_id,amount,status,paid_at,payment_method,payment_status,form_snapshot) VALUES($1,$2,1000,'needs_info',NOW(),'zarinpal','paid','{}') RETURNING id",legacy_user,legacy_product)
            unpaid_order=await legacy.fetchval("INSERT INTO orders(user_id,product_id,amount,status,payment_method,form_snapshot) VALUES($1,$2,1000,'needs_info','card_to_card','{}') RETURNING id",legacy_user,legacy_product)
            await legacy.execute("INSERT INTO audit_logs(actor_telegram_id,action,target_type,target_id,metadata) VALUES(123456,'web_needs_info','order',$1,'{\"message\":\"Legacy information request\"}')",legacy_order)
        finally: await legacy.close()
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True)
        from app.db.core import db
        from app.db import repositories as repo
        from app.services import staff,client_records,client_archive
        from app.client_records_api import order_information, routes
        await db.connect()
        try:
            async with db.acquire() as c:
                legacy_request=await c.fetchrow('SELECT * FROM order_info_requests WHERE order_id=$1',legacy_order)
                assert legacy_request['body']=='Legacy information request' and not legacy_request['notification_sent']
                assert not await c.fetchval('SELECT 1 FROM order_info_requests WHERE order_id=$1',unpaid_order)
                invalid_request=await c.fetchval("INSERT INTO order_info_requests(order_id,body) VALUES($1,'Unpaid safety fixture') RETURNING id",unpaid_order)
            assert await client_records.owned_request(invalid_request,998812346) is None
            assert not await client_records.append_response(invalid_request,998812346,{'message_id':1,'content_type':'text','content_text':'Not payment'})
            assert not await client_records.submit_response(invalid_request,998812346)
            await staff.bootstrap()
            async with db.acquire() as c:
                actor=dict(await c.fetchrow("SELECT * FROM staff_accounts WHERE role IN ('platform','leader') LIMIT 1"))
                actor['staff_id']=actor['id']
                pid=await c.fetchval("""INSERT INTO products(code,title,description,price_irr,delivery_mode,form_fields)
                    VALUES('workflow-check','Workflow check','Test',10000,'manual','["gender","body_photo","measurements"]') RETURNING id""")
            tg=SimpleNamespace(id=998812345,username='workflow_check',first_name='Test',last_name=None)
            await repo.upsert_user(tg)
            product=await repo.get_product(pid)
            photos=[{'file_id':f'old-{i}','type':'photo'} for i in range(4)]
            from app.utils.measurements import MEASUREMENTS
            snapshot={'gender':'مرد','measurements':{key:90 for key in MEASUREMENTS},'body_photo_file_ids':photos,'notes':'original'}
            # Checkout saves only contact details; the questionnaire opens after a verified payment.
            contact={'name':'Workflow client','phone':'09120000000'}
            order=await repo.create_order(tg.id,product,contact,'zarinpal'); oid=order['id']; uid=order['user_id']
            assert order['form_completed_at'] is None
            try: await repo.complete_order_form(oid,tg.id,snapshot)
            except ValueError as exc: assert str(exc)=='order not paid'
            else: raise AssertionError('Questionnaire accepted before payment')
            assert not await repo.has_course_access(tg.id)
            await repo.mark_zarinpal_paid(oid,'workflow-reference')
            assert await repo.has_course_access(tg.id)
            assert await repo.mark_zarinpal_paid(oid,'workflow-reference') is None
            from app.services.fulfillment import fulfill_order
            sent=AsyncMock()
            await fulfill_order(SimpleNamespace(send_message=sent),oid)
            assert sent.await_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data==f'form:{oid}'
            assert (await repo.get_order(oid))['status']=='paid'
            try: await repo.complete_order_form(oid,tg.id,{**snapshot,'body_photo_file_ids':[]})
            except ValueError: pass
            else: raise AssertionError('Body assessment accepted missing photos')
            try: await repo.complete_order_form(oid,tg.id+1,snapshot)
            except ValueError as exc: assert str(exc)=='order not found'
            else: raise AssertionError('Questionnaire accepted for another customer')
            completed=await repo.complete_order_form(oid,tg.id,snapshot)
            assert completed['form_completed_at'] is not None
            assert json.loads(completed['form_snapshot'])['name']=='Workflow client'
            try: await repo.complete_order_form(oid,tg.id,snapshot)
            except ValueError as exc: assert str(exc)=='form already completed'
            else: raise AssertionError('Questionnaire submitted twice')
            async with db.acquire() as c:
                # The first submission is the order's original record, not a correction.
                assert await c.fetchval('SELECT COUNT(*) FROM record_revisions WHERE order_id=$1',oid)==0
                assert await c.fetchval('SELECT COUNT(*) FROM user_profile_history WHERE order_id=$1',oid)==1
            try: await repo.create_order(tg.id,product,snapshot,'card_to_card')
            except ValueError: pass
            else: raise AssertionError('Retired payment accepted')
            assert await repo.approve_card_payment(oid,actor) is None
            before=await repo.get_user(tg.id)
            await client_records.edit_record(actor,uid,{'notes':'profile only','measurements':{'waist':88}},before['updated_at'].isoformat())
            assert json.loads((await repo.get_order(oid))['form_snapshot'])['notes']=='original'
            try: await client_records.edit_record(actor,uid,{'notes':'stale'},before['updated_at'].isoformat())
            except ValueError as exc: assert str(exc)=='record_changed'
            else: raise AssertionError('Stale overwrite accepted')
            try: await client_records.edit_record({'role':'staff','permissions':['customers.read']},uid,{'notes':'denied'},'version')
            except web.HTTPForbidden: pass
            else: raise AssertionError('Unprivileged edit accepted')
            current=await repo.get_order(oid)
            await client_records.edit_record(actor,uid,{'notes':'order correction'},current['updated_at'].isoformat(),oid)
            async with db.acquire() as c:
                revisions=await c.fetch('SELECT snapshot FROM record_revisions WHERE order_id=$1',oid)
                assert any(json.loads(r['snapshot'])['notes']=='original' for r in revisions)
                assert await c.fetchval("SELECT COUNT(*) FROM record_revisions WHERE user_id=$1 AND origin='staff'",uid)==2
                await c.execute('UPDATE users SET updated_at=NOW() WHERE id=$1',uid)
                assert await c.fetchval("SELECT COUNT(*) FROM record_revisions WHERE user_id=$1 AND origin='staff'",uid)==2
                await c.execute("UPDATE users SET notes='Automatic profile refresh' WHERE id=$1",uid)
                assert await c.fetchval("SELECT COUNT(*) FROM record_revisions WHERE user_id=$1 AND origin='staff'",uid)==2
                assert await c.fetchval("SELECT COUNT(*) FROM client_files WHERE order_id=$1 AND source='assessment'",oid)==4
            rid=await client_records.request_information(actor,oid,'Please send a fresh photo')
            assert rid and await client_records.request_information(actor,oid,'Duplicate') is None
            assert await repo.update_order_status(oid,'in_progress') is None
            assert await client_records.owned_request(rid,tg.id+1) is None
            item={'message_id':50,'content_type':'photo','content_text':'New response','file_id':'fresh-photo'}
            assert not await client_records.append_response(rid,tg.id+1,item)
            assert await client_records.append_response(rid,tg.id,item)
            assert await client_records.append_response(rid,tg.id,item)
            assert len(await client_records.response_summary(rid,tg.id))==1
            async with db.acquire() as c:
                await c.execute("INSERT INTO staff_assignments(target_type,target_id,staff_id,seen_at) VALUES('order',$1,$2,NOW())",oid,actor['staff_id'])
            assert await client_records.submit_response(rid,tg.id)
            assert not await client_records.submit_response(rid,tg.id)
            async with db.acquire() as c:
                assert await c.fetchval('SELECT COUNT(*) FROM order_info_items WHERE request_id=$1',rid)==1
                assert await c.fetchval("SELECT COUNT(*) FROM support_messages WHERE user_id=$1",uid)==0
                assert await c.fetchval("SELECT COUNT(*) FROM client_files WHERE source='information' AND order_id=$1",oid)==1
                assert await c.fetchval("SELECT seen_at IS NULL FROM staff_assignments WHERE target_type='order' AND target_id=$1",oid)
            request=SimpleNamespace(match_info={'order_id':str(oid)})
            response=json.loads((await order_information(request)).text)
            assert response['requests'][0]['status']=='submitted' and response['items'][0]['attachment_id']
            assert 'file_id' not in response['items'][0]
            assert (await repo.update_order_status(oid,'in_progress'))['status']=='in_progress'
            await asyncio.gather(*(repo.add_support_message(tg.id,99,content_type='text',content_text='Hello') for _ in range(3)))
            async with db.acquire() as c:
                assert await c.fetchval('SELECT COUNT(*) FROM support_messages WHERE user_id=$1 AND message_id=99',uid)==1
                # Prepare a renewable first course, then create a separate second photo set.
                await c.execute("UPDATE orders SET status='delivered',delivered_at=NOW()-INTERVAL '31 days' WHERE id=$1",oid)
            second=await repo.create_order(tg.id,product,contact,'zarinpal',oid)
            await repo.mark_zarinpal_paid(second['id'],'workflow-renewal')
            second=await repo.complete_order_form(second['id'],tg.id,{**snapshot,'body_photo_file_ids':[{'file_id':f'new-{i}'} for i in range(4)]})
            assert json.loads((await repo.get_order(oid))['form_snapshot'])['body_photo_file_ids']==photos
            assert json.loads(second['form_snapshot'])['body_photo_file_ids'][0]['file_id']=='new-0'
            for _ in range(20): await client_archive.index_existing()
            bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace(file_size=30*1024*1024)))
            assert await client_archive.archive_one(bot)
            async with db.acquire() as c:
                assert await c.fetchval("SELECT COUNT(*) FROM client_files WHERE status='remote'")==1
                assert await c.fetchval("SELECT COUNT(*) FROM client_files WHERE order_id=$1 AND source='assessment'",second['id'])==4
            # Exercise the real authorization/CSRF middleware on private record routes.
            from app.webapp import auth
            current_actor={**actor,'role':'leader','csrf':'fixture'}
            with tempfile.TemporaryDirectory() as storage, patch.dict(os.environ,{'CATALOG_STORAGE':storage}), \
                 patch('app.webapp._session_actor',AsyncMock(side_effect=lambda request:current_actor)), \
                 patch('app.webapp._rate_limited',AsyncMock(return_value=False)), \
                 patch('app.services.content.shutil.disk_usage',return_value=SimpleNamespace(total=100*1024**3,free=90*1024**3)):
                app=web.Application(middlewares=[auth],client_max_size=1024)
                app['read_cache']={};app['upload_slots']=asyncio.Semaphore(4)
                app.add_routes(routes())
                async with TestClient(TestServer(app)) as client:
                    record=await client.get(f'/api/customers/{uid}/record')
                    result=await record.json()
                    assert record.status==200 and 'telegram_id' not in result['values']
                    assert all('file_id' not in file for file in result['files'])
                    assert (await client.post(f'/api/customers/{uid}/record',json={})).status==403
                    current_actor={**current_actor,'role':'staff','permissions':['customers.read']}
                    assert (await client.post(f'/api/customers/{uid}/record',json={'fields':{'notes':'denied'}},headers={'X-CSRF-Token':'fixture'})).status==403
                    current_actor={**current_actor,'role':'leader'}
                    data=FormData();data.add_field('file',b'%PDF-1.4\n'+b' '*2048,filename='private.pdf',content_type='application/pdf')
                    upload=await client.post(f'/api/customers/{uid}/files?order_id={oid}',data=data,headers={'X-CSRF-Token':'fixture'})
                    assert upload.status==200,await upload.text()
                    attachment=(await upload.json())['id']
                    media=await client.get(f'/media/client-files/{attachment}')
                    assert media.status==200 and (await media.read()).startswith(b'%PDF-')
                    assert media.headers['Cache-Control']=='private, no-store'
                    assert media.headers['X-Content-Type-Options']=='nosniff'
                    assert media.headers['Content-Type'].startswith('application/pdf')
                    download=await client.get(f'/media/client-files/{attachment}?download=1')
                    assert download.headers['Content-Disposition'].startswith('attachment')
                    data=FormData();data.add_field('file',b'\x89PNG\r\n\x1a\n'+b'fixture'*350,filename='body.png',content_type='image/png')
                    upload=await client.post(f'/api/customers/{uid}/files',data=data,headers={'X-CSRF-Token':'fixture'})
                    assert upload.status==200,await upload.text()
                    photo_id=(await upload.json())['id']
                    before=await repo.get_user(tg.id)
                    await client_records.edit_record(current_actor,uid,{'photo_ids':[photo_id]},before['updated_at'].isoformat())
                    assert json.loads((await repo.get_user(tg.id))['body_photo_file_ids'])[0]['client_file_id']==photo_id
                    assert json.loads((await repo.get_order(oid))['form_snapshot'])['body_photo_file_ids']==photos
                    wrong_user=await repo.get_user_by_id(legacy_user)
                    try: await client_records.edit_record(current_actor,legacy_user,{'photo_ids':[photo_id]},wrong_user['updated_at'].isoformat())
                    except ValueError as exc: assert str(exc)=='invalid_photos'
                    else: raise AssertionError('Cross-client photo selection accepted')
                    listing=await client.get(f'/api/customers/{legacy_user}/files')
                    assert all(file['id']!=photo_id for file in (await listing.json())['files'])
                    record=await client.get(f'/api/customers/{uid}/record')
                    record_data=await record.json()
                    assert record_data['values']['photo_ids']==[photo_id]
                    assert len(record_data['revisions'])==3
                    current_actor={**current_actor,'role':'staff','permissions':[]}
                    assert (await client.get(f'/media/client-files/{attachment}')).status==403
                    assert (await client.get(f'/api/orders/{oid}/information')).status==403
                # Duplicate Telegram file IDs reuse stored bytes instead of downloading again.
                from app.services.content import asset_path
                async with db.acquire() as c:
                    key=await c.fetchval('SELECT storage_key FROM client_files WHERE id=$1',attachment)
                    await c.execute("UPDATE client_files SET status='remote' WHERE status IN ('pending','archiving')")
                    await c.execute("INSERT INTO client_files(user_id,source,source_id,file_id,filename,storage_key,status) VALUES($1,'staff',900,'same-telegram-file','private.pdf',$2,'archived')",uid,key)
                    await c.execute("INSERT INTO client_files(user_id,source,source_id,file_id,filename) VALUES($1,'staff',901,'same-telegram-file','private.pdf')",uid)
                assert asset_path(key).is_file()
                no_download=SimpleNamespace(get_file=AsyncMock(side_effect=AssertionError('Duplicate download')))
                assert await client_archive.archive_one(no_download)
                no_download.get_file.assert_not_called()
                async with db.acquire() as c:
                    assert await c.fetchval("SELECT storage_key FROM client_files WHERE source_id=901",)==key
                    await c.execute("INSERT INTO client_files(user_id,source,source_id,file_id,filename) VALUES($1,'staff',902,'historical-png','body-photo.jpg')",uid)
                png=b'\x89PNG\r\n\x1a\n'+b'fixture'
                async def download_png(_remote,destination,timeout):
                    destination.write_bytes(png)
                png_bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace(file_size=len(png),file_path='documents/photo.png')),download_file=AsyncMock(side_effect=download_png))
                assert await client_archive.archive_one(png_bot)
                async with db.acquire() as c:
                    archived=await c.fetchrow("SELECT filename,status,storage_key FROM client_files WHERE source_id=902")
                assert archived['filename']=='body-photo.png' and archived['status']=='archived'
                assert asset_path(archived['storage_key']).read_bytes()==png
            print('PASS: migration, chat access/idempotency, retired payment, versioned edits, private API/CSRF/permissions, request followups/review, independent renewal photos, archive indexing/fallback/deduplication')
        finally: await db.close()
    finally:
        await admin.execute(f'DROP DATABASE {name} WITH (FORCE)')
        await admin.close()


if __name__=='__main__': asyncio.run(main())
