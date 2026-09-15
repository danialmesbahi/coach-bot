import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from app.analytics_api import options, change, client_error
from app.services import telemetry


def test_scopes_and_bounded_input():
    actor={'role':'staff','staff_id':23,'permissions':['analytics.self','analytics.platform']}
    assert options(actor,{})==('personal',30,'all',1)
    with pytest.raises(web.HTTPForbidden): options(actor,{'scope':'platform'})
    with pytest.raises(web.HTTPForbidden): options({'role':'staff','permissions':[]},{})
    for query in ({'days':'365'},{'page':'9'*5000},{'category':'private_metadata'},{'scope':'unknown'}):
        with pytest.raises(web.HTTPBadRequest): options(actor,query)
    assert options({'role':'leader'},{})[0]=='platform'
    assert change(20,10)==100 and change(0,10)==-100 and change(10,0) is None


def test_bounded_private_telemetry(monkeypatch):
    monkeypatch.setattr(telemetry,'_buckets',{})
    monkeypatch.setattr(telemetry,'_dropped',0)
    monkeypatch.setattr(telemetry,'MAX_KEYS',2)
    for _ in range(1000): telemetry.record('web','request','orders',elapsed=.1)
    telemetry.record('web','request','password_login','client_error')
    telemetry.record('web','request','overflow')
    telemetry.record('web','request','/secret/token')
    assert len(telemetry._buckets)==2 and telemetry._dropped==1
    assert sum(row[0] for row in telemetry._buckets.values())==1001
    state=SimpleNamespace(get_state=AsyncMock(return_value='PurchaseForm:weight'))
    asyncio.run(telemetry.BotMetrics()(AsyncMock(),object(),{'raw_state':'PurchaseForm:height','state':state}))
    assert telemetry._dropped==3


def test_client_error_rejects_unbounded_payload(monkeypatch):
    from app import webapp
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    for body in ({'view':[]},{'view':'messages','error':'private content'},{'view':'secret'}):
        request=SimpleNamespace(content_length=20,clone=lambda **kwargs:SimpleNamespace(json=AsyncMock(return_value=body)))
        with pytest.raises(web.HTTPBadRequest): asyncio.run(client_error(request))


def test_http_telemetry_size_limit_and_metadata_only(monkeypatch):
    from aiohttp.test_utils import TestClient,TestServer
    from app import webapp
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    monkeypatch.setattr(telemetry,'_buckets',{})
    async def check():
        app=web.Application(middlewares=[webapp.errors])
        app.router.add_post('/error',client_error)
        async with TestClient(TestServer(app)) as client:
            assert (await client.post('/error',json={'view':'messages'})).status==200
            assert (await client.post('/error',json={'view':[]})).status==400
            assert (await client.post('/error',json={'view':'x'*300})).status==413
        assert sum(row[0] for row in telemetry._buckets.values())==1
    asyncio.run(check())


def test_personal_handler_uses_session_identity(monkeypatch):
    from app import webapp,analytics_api
    keys=[]
    async def cached(request,key,ttl,load):
        keys.append(key)
        return await load()
    monkeypatch.setattr(webapp,'_cached',cached)
    monkeypatch.setattr(webapp,'_rate_limited',AsyncMock(return_value=False))
    snapshot=AsyncMock(return_value={'scope':'personal'})
    monkeypatch.setattr(analytics_api,'snapshot',snapshot)
    class Request(dict):
        query={'staff_id':'999','scope':'personal'}
        app={}
    async def check():
        for identity in (1,2):
            await analytics_api.analytics(Request(actor={'role':'staff','staff_id':identity,'permissions':['analytics.self']}))
    asyncio.run(check())
    assert [call.args[0] for call in snapshot.await_args_list]==[1,2]
    assert keys==['analytics:1:30:all:1','analytics:2:30:all:1']
