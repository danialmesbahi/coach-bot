import asyncio
import json
import logging
import sys
from types import SimpleNamespace
from contextlib import asynccontextmanager, nullcontext
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from app.services.catalog import validate_product, purchase_terms
from app.services.content import store_upload, inspect_file
from app.services.diagnostics import DiagnosticFormat


def product(**extra):
    return dict(title='Course',description='',price_irr=1500,duration_days=30,
        duration_unit='days',sort_order=0,delivery_mode='content',form_fields=[],questions=[],
        response_text='Welcome',content_url='',asset_id=None,channel_id=None,active=True,**extra)


@pytest.mark.parametrize('unit,days',[('days',2),('weeks',14),('months',90),('years',730),('lifetime',0),('once',-1)])
def test_duration_and_assets_are_snapshotted(unit,days):
    body=product();body.update(duration_unit=unit,duration_days=days,asset_ids=[3,7])
    result=validate_product(body)
    assert purchase_terms(result)['asset_ids']==[3,7]
    assert result['duration_days']==days and result['duration_unit']==unit
    body['duration_days']=3 if unit=='weeks' else -9
    with pytest.raises(ValueError): validate_product(body)


def test_once_cannot_create_channel_subscription():
    body=product();body.update(duration_unit='once',duration_days=-1,delivery_mode='channel')
    with pytest.raises(ValueError,match='once_content_only'): validate_product(body)


def test_upload_streams_past_old_limit_and_preserves_storage(tmp_path,monkeypatch):
    from app.services import content
    monkeypatch.setenv('CATALOG_STORAGE',str(tmp_path))
    monkeypatch.setattr(content.shutil,'disk_usage',lambda _:SimpleNamespace(free=8*1024**3,total=10*1024**3))
    class Part:
        filename='../course.pdf'
        remaining=13
        async def read_chunk(self,size):
            if not self.remaining:return b''
            self.remaining-=1
            return (b'%PDF-1.4\n' if self.remaining==12 else b'')+b'x'*size
    key,name,size=asyncio.run(store_upload(Part()))
    assert name=='course.pdf' and size>10*1024**2
    assert (tmp_path/key).stat().st_size==size
    assert inspect_file(tmp_path/key,name)
    monkeypatch.setattr(content.shutil,'disk_usage',lambda _:SimpleNamespace(free=100,total=10*1024**3))
    with pytest.raises(web.HTTPInsufficientStorage):asyncio.run(store_upload(Part()))
    assert len(list(tmp_path.iterdir()))==1,'failed upload left partial file'


def test_diagnostics_exclude_messages_secrets_and_traceback_locals():
    secret='password=SuperSecret42!'
    try: raise ValueError(secret)
    except ValueError:
        record=logging.LogRecord('test',logging.ERROR,__file__,1,secret,(),sys.exc_info())
        record.order_id=54
        result=DiagnosticFormat().format(record)
    assert secret not in result and 'SuperSecret' not in result
    assert json.loads(result)['exception']=='ValueError'
    assert json.loads(result)['order_id']==54
    assert json.loads(result)['frames'][-1]['function']=='test_diagnostics_exclude_messages_secrets_and_traceback_locals'


def test_catalog_http_upload_bypasses_only_normal_body_limit(tmp_path,monkeypatch):
    from aiohttp import FormData
    from aiohttp.test_utils import TestClient, TestServer
    from app import catalog_api, webapp
    from app.services import content
    monkeypatch.setenv('CATALOG_STORAGE',str(tmp_path))
    monkeypatch.setattr(content.shutil,'disk_usage',lambda _:SimpleNamespace(free=8*1024**3,total=10*1024**3))
    connection=SimpleNamespace(fetchval=AsyncMock(return_value=41),transaction=lambda:nullcontext())
    @asynccontextmanager
    async def acquire():yield connection
    monkeypatch.setattr(catalog_api.db,'acquire',acquire)
    monkeypatch.setattr(catalog_api.staff,'audit',AsyncMock())
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    @web.middleware
    async def actor(request,handler):
        request['actor']={'role':request.headers.get('Test-Role','leader'),'staff_id':1,'permissions':[]}
        return await handler(request)
    async def check():
        app=web.Application(middlewares=[actor],client_max_size=10*1024**2)
        app['catalog_upload_slots']=asyncio.Semaphore(2)
        app.router.add_post('/upload',catalog_api.catalog_asset)
        async with TestClient(TestServer(app)) as client:
            body=FormData();body.add_field('file',b'%PDF-1.4\n'+b'x'*(12*1024**2),filename='course.pdf')
            result=await client.post('/upload',data=body)
            assert result.status==200,await result.text()
            assert (await result.json())['byte_size']>10*1024**2
            for filename,payload in [('IMG_1234.MOV',b'\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  '),
                                     ('photo.HEIC',b'\x00\x00\x00\x18ftypheic'),('lesson.pptx',b'PK\x03\x04'),
                                     ('notes.html',b'<script>alert(1)</script>')]:
                body=FormData();body.add_field('file',payload,filename=filename)
                result=await client.post('/upload',data=body)
                assert result.status==200,await result.text()
                stored=await result.json()
                assert stored['filename']==filename and stored['byte_size']==len(payload)
            body=FormData();body.add_field('file',b'',filename='empty.mov')
            assert (await client.post('/upload',data=body)).status==400
            assert (await client.post('/upload',headers={'Test-Role':'staff'})).status==403
        args=connection.fetchval.await_args.args
        assert 'storage_key' in args[0] and 'payload' not in args[0]
    asyncio.run(check())


def test_successful_sticker_is_checkpointed_and_not_cached_as_document(monkeypatch):
    from app.services import fulfillment
    from aiogram.types import Message, Chat, Sticker
    checkpoint=set()
    async def fetchval(sql,order_id,asset_id):return (order_id,asset_id) in checkpoint
    async def execute(sql,*args):
        assert not sql.startswith('UPDATE product_assets'),'sticker ID cached as document'
        checkpoint.add(args[:2])
    connection=SimpleNamespace(fetchval=fetchval,execute=execute,transaction=lambda:nullcontext(),
        fetchrow=AsyncMock(return_value={'id':3,'filename':'photo.webp','payload':b'RIFF','file_id':None}))
    @asynccontextmanager
    async def acquire():yield connection
    monkeypatch.setattr(fulfillment.db,'acquire',acquire)
    message=Message(message_id=123,date=0,chat=Chat(id=1,type='private'),
        sticker=Sticker(file_id='sticker-id',file_unique_id='unique',type='regular',width=100,height=100,is_animated=False,is_video=False))
    bot=SimpleNamespace(send_document=AsyncMock(return_value=message))
    async def check():
        for _ in range(2):
            await fulfillment.send_content(connection,bot,{'id':54,'telegram_id':1,'duration_days':0},{'asset_ids':[3]})
    asyncio.run(check())
    assert bot.send_document.await_count==1
    assert bot.send_document.await_args.kwargs['disable_content_type_detection'] is True
    assert checkpoint=={(54,3)}


def test_delivery_failure_retries_only_definite_rate_rejection(monkeypatch):
    from app.services import fulfillment
    from aiogram.exceptions import TelegramRetryAfter, TelegramNetworkError
    from aiogram.methods import SendDocument
    connection=SimpleNamespace(execute=AsyncMock())
    @asynccontextmanager
    async def acquire():yield connection
    monkeypatch.setattr(fulfillment.db,'acquire',acquire)
    method=SendDocument(chat_id=1,document='file')
    async def check():
        for exc,retry in [(AttributeError('document'),False),(TelegramNetworkError(method=method,message='timeout'),False),
                          (TelegramRetryAfter(method=method,message='flood',retry_after=90),True)]:
            await fulfillment.record_delivery_failure(54,exc)
            sql,oid,allowed,delay=connection.execute.await_args.args
            assert oid==54 and allowed is retry
            assert 'fulfillment_attempts<5' in sql and "'infinity'" in sql
            assert delay==(90 if retry else 0)
    asyncio.run(check())


def test_once_bundle_is_sent_directly_and_not_reissued(monkeypatch):
    from app.services import fulfillment
    checkpoint=set()
    async def fetchval(sql,order_id,asset_id): return (order_id,asset_id) in checkpoint
    async def execute(sql,*args):
        if sql.startswith('INSERT'): checkpoint.add(args[:2])
    connection=SimpleNamespace(fetchval=fetchval,execute=execute,transaction=lambda:nullcontext(),
        fetchrow=AsyncMock(return_value={'filename':'gallery.mov','payload':b'video','byte_size':27*1024**2,'file_id':None}))
    @asynccontextmanager
    async def acquire(): yield connection
    monkeypatch.setattr(fulfillment.db,'acquire',acquire)
    monkeypatch.setattr(fulfillment,'content_link',AsyncMock(side_effect=AssertionError('Unexpected public download dependency')))
    bot=SimpleNamespace(send_document=AsyncMock(return_value=SimpleNamespace(document=SimpleNamespace(file_id='video-document'))),send_message=AsyncMock())
    order={'id':56,'telegram_id':1,'duration_days':-1,'paid_at':True,'status':'delivered'}
    async def check():
        for _ in range(2): await fulfillment.send_content(connection,bot,order,{'asset_ids':[4,5]})
        assert bot.send_document.await_count==2
        assert checkpoint=={(56,4),(56,5)}
        assert await fulfillment.resend_content(bot,order,1)
        assert bot.send_document.await_count==2
    asyncio.run(check())


def test_catalog_previews_are_private_validated_and_range_capable(tmp_path,monkeypatch):
    from aiohttp.test_utils import TestClient,TestServer
    from app import catalog_api,webapp
    from app.services import content,staff
    assert staff.ROUTE_PERMISSIONS['catalog_asset_preview']=='catalog.manage'
    monkeypatch.setenv('CATALOG_STORAGE',str(tmp_path))
    key='a'*48; payload=b'\x00\x00\x00\x14ftypqt  '+b'x'*100
    (tmp_path/key).write_bytes(payload)
    asset={'filename':'gallery.MOV','storage_key':key,'payload':None}
    connection=SimpleNamespace(fetchrow=AsyncMock(side_effect=lambda *args:asset))
    @asynccontextmanager
    async def acquire(): yield connection
    monkeypatch.setattr(catalog_api.db,'acquire',acquire)
    async def actor(request):
        role=request.headers.get('Test-Role')
        return {'role':role,'staff_id':1,'permissions':[],'csrf':'test'} if role else None
    monkeypatch.setattr(webapp,'_session_actor',actor)
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    async def check():
        app=web.Application(middlewares=[webapp.security_headers,webapp.auth])
        app.add_routes(catalog_api.routes())
        async with TestClient(TestServer(app)) as client:
            url='/api/catalog-assets/4/preview'
            assert (await client.get(url)).status==401
            assert (await client.get(url,headers={'Test-Role':'staff'})).status==403
            headers={'Test-Role':'leader','Range':'bytes=0-19'}
            result=await client.get(url,headers=headers)
            assert result.status==206 and await result.read()==payload[:20]
            assert result.headers['Content-Type']=='video/quicktime'
            assert result.headers['X-Content-Type-Options']=='nosniff'
            assert 'no-store' in result.headers['Cache-Control']
            asset.update(filename='attack.html',storage_key=None,payload=b'<script>bad()</script>')
            assert (await client.get(url,headers=headers)).status==415
            asset['filename']='spoof.mov'
            assert (await client.get(url,headers=headers)).status==415
            asset.update(filename='photo.png',payload=b'\x89PNG\r\n\x1a\nrest')
            result=await client.get(url,headers={'Test-Role':'platform'})
            assert result.status==200 and result.headers['Content-Type']=='image/png'
    asyncio.run(check())
