from app.services.broadcasts import AUDIENCE_SQL, audience_args
from app.services.catalog import purchase_terms, validate_product
from app.services.staff import can
import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from app.services import deliveries, broadcasts, fulfillment
from app import broadcast_api


def test_broadcast_audience_is_bounded_and_leader_only():
    assert 'NOT EXISTS(SELECT 1 FROM staff_accounts' not in AUDIENCE_SQL
    assert audience_args({'purchase_state':'active','product_ids':[2,3],'age_min':18,'age_max':35,'gender':'زن','orders_min':1})[:12] == ('active',[2,3],18,35,'زن',None,1,None,None,None,None,None)
    assert audience_args({'search':'  @client  '})[11]=='client'
    assert audience_args({'height_min':170,'weight_max':90,'profile_keyword':'  health  ','has_photo':False,'payment_method':'zarinpal','message_state':'chatted'})[12:] == (170,None,None,90,'health',None,False,None,'zarinpal',None,'chatted',None)
    assert audience_args({'purchased_only':True,'product_ids':[2,3],'active_only':True})[:2] == ('active',[2,3])
    for invalid in ({'product_ids':[2,2]},{'active_only':True},{'age_min':70,'age_max':20},
                    {'product_ids':['2']},{'purchased_only':'yes'},{'purchase_state':'never','product_ids':[2]},
                    {'purchase_state':'never','orders_min':1},{'spent_min':100,'spent_max':50},
                    {'joined_within_days':0},{'orders_min':True},{'gender':'unknown'},{'search':'x'*81},
                    {'height_min':200,'height_max':150},{'weight_min':True},{'profile_keyword':'x'*81},{'has_phone':1},
                    {'payment_method':'mock'},{'message_state':'never','last_message_within_days':7},{'unrecognized_filter':'x'}):
        try:
            audience_args(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)
    assert can({'role':'leader'},'broadcast.manage')
    assert not can({'role':'staff','permissions':['chats.reply']},'broadcast.manage')


def test_broadcast_body_accepts_maximum_length_persian_message():
    message='پ' * 4000
    class Request:
        def clone(self, *, client_max_size):
            assert client_max_size >= len(json.dumps({'message':message}, ensure_ascii=False).encode('utf-8'))
            return self
        async def json(self):
            return {'message':message,'audience':{}}
    _, parsed, _ = asyncio.run(broadcast_api._body(Request()))
    assert parsed == message


def test_ready_product_preserves_multiple_links_in_purchase_snapshot():
    body=dict(title='Video',description='',response_text='Start here',content_url='',content_urls=['https://example.org/a','https://example.org/b'],
        price_irr=1500,duration_days=30,sort_order=0,duration_unit='days',delivery_mode='content',form_fields=[],questions=[],asset_ids=[],channel_id=None,active=True)
    product=validate_product(body)
    assert product['content_urls']==body['content_urls']
    assert purchase_terms(product)['content_urls']==body['content_urls']
    body['content_urls']=['http://example.org/a']
    try:
        validate_product(body)
    except ValueError as exc:
        assert str(exc)=='content_urls'
    else:
        raise AssertionError('Insecure link accepted')


def test_manual_delivery_sends_each_bundle_part_once(monkeypatch):
    class Connection:
        @asynccontextmanager
        async def transaction(self):
            yield
        async def fetchrow(self,sql,*args):
            if 'FROM orders o' in sql: return {'id':7,'status':'ready','telegram_id':99}
            if 'FROM manual_deliveries' in sql: return {'status':'queued'}
            raise AssertionError(sql)
        async def fetch(self,sql,*args):
            return [{'id':1,'kind':'text','body':'Hello','sent_at':None,'asset_id':None},
                    {'id':2,'kind':'link','body':'https://example.org','sent_at':None,'asset_id':None}]
        async def execute(self,sql,*args):
            writes.append((sql,args))
    writes=[];connection=Connection()
    @asynccontextmanager
    async def acquire():
        yield connection
    monkeypatch.setattr(deliveries.db,'acquire',acquire)
    bot=type('Bot',(),{'send_message':AsyncMock()})()
    asyncio.run(deliveries.deliver_manual_order(bot,7))
    assert [call.args for call in bot.send_message.call_args_list]==[(99,'Hello'),(99,'https://example.org')]
    assert sum('SET sent_at=NOW()' in sql for sql,_ in writes)==2
    assert any("status='completed'" in sql for sql,_ in writes)


def test_manual_bundle_accepts_multiple_telegram_sized_files(monkeypatch):
    from app import webapp
    limits=[]
    async def store(part, max_bytes):
        limits.append(max_bytes)
        return part.filename[0]*48,part.filename,42
    class Reader:
        def __init__(self): self.parts=iter([type('Part',(),{'name':'file','filename':name})() for name in ('a.mp4','b.pdf')])
        async def next(self): return next(self.parts,None)
    class Connection:
        @asynccontextmanager
        async def transaction(self): yield
        async def fetchrow(self,*args): return {'id':7,'status':'ready'}
        async def fetchval(self,sql,*args):
            if 'manual_deliveries' in sql: return None
            if 'product_assets' in sql: return 1
            raise AssertionError(sql)
        async def execute(self,*args): pass
    @asynccontextmanager
    async def acquire(): yield Connection()
    class Request:
        async def multipart(self): return Reader()
        def __getitem__(self,key): return {'staff_id':1}
    monkeypatch.setattr(webapp,'store_upload',store)
    monkeypatch.setattr(webapp.db,'acquire',acquire)
    monkeypatch.setattr(webapp.staff,'audit',AsyncMock())
    result=asyncio.run(webapp._upload_plan(Request(),{'id':7}))
    assert result.status==200
    assert limits==[50*1024*1024]*2


def test_ready_delivery_sends_every_configured_link(monkeypatch):
    sent=AsyncMock()
    monkeypatch.setattr(fulfillment,'send_message_once',sent)
    order={'id':12,'telegram_id':99}
    asyncio.run(fulfillment.send_content(None,object(),order,{'content_urls':['https://example.org/a','https://example.org/b'],'asset_ids':[]}))
    assert [call.args[2:] for call in sent.call_args_list]==[('url:0','https://example.org/a'),('url:1','https://example.org/b')]


def test_broadcast_ambiguous_failure_pauses_recipient(monkeypatch):
    class Connection:
        @asynccontextmanager
        async def transaction(self):
            yield
        async def fetch(self,sql,*args):
            return [{'broadcast_id':4,'user_id':7,'telegram_id':99,'message':'Hello'}]
        async def fetchrow(self,sql,*args):
            return {'status':'pending'}
        async def execute(self,sql,*args):
            writes.append((sql,args))
    writes=[];connection=Connection()
    @asynccontextmanager
    async def acquire():
        yield connection
    monkeypatch.setattr(broadcasts.db,'acquire',acquire)
    bot=type('Bot',(),{'send_message':AsyncMock(side_effect=RuntimeError('unknown'))})()
    asyncio.run(broadcasts.process_broadcasts(bot))
    assert bot.send_message.await_count==1
    assert any("status='paused'" in sql and args==(4,7) for sql,args in writes)


def test_broadcast_serialization_checks_latest_committed_campaign(monkeypatch):
    isolation=[];insert=[]
    class Connection:
        @asynccontextmanager
        async def transaction(self,**kwargs):
            isolation.append(kwargs['isolation'])
            yield
        async def execute(self,sql,*args):
            if 'INSERT INTO broadcast_recipients' in sql:insert.append((sql,args))
        async def fetchval(self,sql,*args):
            if 'FROM broadcasts WHERE status' in sql: return None
            if 'COUNT(*)' in sql: return 1
            if 'INSERT INTO broadcasts' in sql: return 42
            raise AssertionError(sql)
    @asynccontextmanager
    async def acquire(): yield Connection()
    monkeypatch.setattr(broadcast_api.db,'acquire',acquire)
    monkeypatch.setattr(broadcast_api.staff,'require',lambda *args:None)
    monkeypatch.setattr(broadcast_api.staff,'audit',AsyncMock())
    from app import webapp
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    monkeypatch.setattr(broadcast_api,'_body',AsyncMock(return_value=(
        {'audience':{},'expected_count':1},'Hello',audience_args({}))))
    result=asyncio.run(broadcast_api.broadcast_send({'actor':{'staff_id':1}}))
    assert result.status==200
    assert isolation==['read_committed']
    assert len(insert)==1
    assert 'SELECT $25::bigint,u.id,u.telegram_id' in insert[0][0]
    assert insert[0][1][-1]==42


def test_broadcast_preview_includes_matching_profiles_without_message(monkeypatch):
    class Connection:
        async def fetchval(self,sql,*args):
            assert 'COUNT(*)' in sql and args[11]=='client'
            return 1
        async def fetch(self,sql,*args):
            assert 'ORDER BY u.id DESC LIMIT 13' in sql and args[11]=='client'
            return [{'id':7,'name':'Client','first_name':None,'last_name':None,'username':'client','has_paid_order':True}]
    @asynccontextmanager
    async def acquire(): yield Connection()
    class Request:
        async def json(self): return {'audience':{'search':'client'}}
        def clone(self,**kwargs): return self
        def __getitem__(self,key): return {'role':'leader'}
    monkeypatch.setattr(broadcast_api.db,'acquire',acquire)
    monkeypatch.setattr(broadcast_api.staff,'require',lambda *args:None)
    from app import webapp
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    result=asyncio.run(broadcast_api.broadcast_preview(Request()))
    assert result.status==200
    assert b'"count": 1' in result.body and b'"username": "client"' in result.body
    assert b'"next_cursor": null' in result.body


def test_broadcast_preview_pages_without_hiding_matching_users(monkeypatch):
    class Connection:
        async def fetchval(self, sql, *args): return 13
        async def fetch(self, sql, *args):
            assert 'ORDER BY u.id DESC LIMIT 13' in sql
            if len(args) == 25:
                assert 'u.id<$25::bigint' in sql and args[-1] == 2
                return [{'id':1}]
            return [{'id':id} for id in range(13,0,-1)]

    @asynccontextmanager
    async def acquire(): yield Connection()

    class Request:
        def __init__(self, after_id=None): self.after_id=after_id
        async def json(self): return {'audience':{}, 'after_id':self.after_id}
        def clone(self, **kwargs): return self
        def __getitem__(self, key): return {'role':'leader'}

    monkeypatch.setattr(broadcast_api.db,'acquire',acquire)
    monkeypatch.setattr(broadcast_api.staff,'require',lambda *args:None)
    from app import webapp
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    first=json.loads(asyncio.run(broadcast_api.broadcast_preview(Request())).body)
    second=json.loads(asyncio.run(broadcast_api.broadcast_preview(Request(first['next_cursor']))).body)
    assert len(first['recipients']) == 12 and first['next_cursor'] == 2
    assert second['recipients'] == [{'id':1}] and second['next_cursor'] is None
