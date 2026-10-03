import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.services.catalog import validate_product
from app.services.staff import can
from app.handlers.user import purchase_route, advance_after, finish_questionnaire
from app.services import fulfillment


def product(**changes):
    return dict(title='Course',description='',price_irr=100000,duration_days=90,sort_order=0,delivery_mode='manual',active=True,**changes)


def test_catalog_boundary_and_configurable_questionnaire():
    assert validate_product(product(form_fields=['weight','name']))['form_fields']==['name','weight']
    assert purchase_route('new_course',{'name':'Saved name'},['name','weight'])==['weight']
    assert purchase_route('new_course',{},[])==[]
    assert not can({'role':'staff','permissions':['catalog.manage']},'catalog.manage')
    assert can({'role':'leader'},'catalog.manage')
    for bad in ({'duration_days':0},{'duration_days':True},{'price_irr':-1},{'content_url':'javascript:alert(1)'},
                {'delivery_mode':'channel'},{'delivery_mode':'content'},{'form_fields':['password']},{'questions':['x'*201]}):
        data=product();data.update(bad)
        with pytest.raises(ValueError): validate_product(data)


def test_empty_or_short_questionnaire_reaches_confirmation(monkeypatch):
    from app.handlers import user
    summary=AsyncMock();monkeypatch.setattr(user,'show_summary',summary)
    state=SimpleNamespace(get_data=AsyncMock(return_value={'product_code':'new','active_steps':['notes']}),set_state=AsyncMock())
    asyncio.run(advance_after(state,object(),'notes'))
    summary.assert_awaited_once()
    state.get_data.return_value={'questions':['What do you need?'],'question_index':0}
    message=SimpleNamespace(answer=AsyncMock())
    asyncio.run(finish_questionnaire(message,state))
    assert 'What do you need?' in message.answer.await_args.args[0]


def test_channel_join_rejects_wrong_identity_and_consumes_valid_link(monkeypatch):
    @asynccontextmanager
    async def transaction(): yield
    connection=SimpleNamespace(fetchval=AsyncMock(return_value=True),fetchrow=AsyncMock(return_value=None),execute=AsyncMock(),transaction=transaction)
    @asynccontextmanager
    async def acquire(): yield connection
    monkeypatch.setattr(fulfillment.db,'acquire',acquire)
    bot=SimpleNamespace(decline_chat_join_request=AsyncMock(),approve_chat_join_request=AsyncMock(),revoke_chat_invite_link=AsyncMock())
    event=SimpleNamespace(chat=SimpleNamespace(id=-1001),from_user=SimpleNamespace(id=7),invite_link=SimpleNamespace(invite_link='private'))
    asyncio.run(fulfillment.join_request(event,bot))
    bot.decline_chat_join_request.assert_awaited_once_with(-1001,7)
    bot.approve_chat_join_request.assert_not_awaited()
    assert connection.fetchrow.await_args.args[1:]==(-1001,7,'private')
    connection.fetchrow.return_value={'order_id':9}
    asyncio.run(fulfillment.join_request(event,bot))
    bot.approve_chat_join_request.assert_awaited_once_with(-1001,7)
    bot.revoke_chat_invite_link.assert_awaited_once_with(-1001,'private')


def test_public_catalog_exposes_only_storefront_fields_and_caches(monkeypatch):
    import json
    from app import catalog_api
    row={'id':3,'title':'Plan','description':None,'price_irr':399000,'duration_days':30,'duration_unit':'days',
         'delivery_mode':'manual','form_fields':'["age","weight"]','response_text':'secret','content_urls':'["https://x"]','channel_id':-100}
    connection=SimpleNamespace(fetch=AsyncMock(return_value=[row]),fetchval=AsyncMock(return_value=False))
    @asynccontextmanager
    async def acquire(): yield connection
    monkeypatch.setattr(catalog_api.db,'acquire',acquire)
    monkeypatch.setitem(catalog_api._public_cache,'body',None)
    body=json.loads(asyncio.run(catalog_api.public_catalog(SimpleNamespace())).text)
    assert body=={'items':[{'id':3,'title':'Plan','description':'','price_toman':399000,'duration_days':30,'duration_unit':'days',
                            'delivery_mode':'manual','form_fields':['age','weight']}],'sales_open':False}
    query=connection.fetch.await_args.args[0]
    assert 'active AND NOT archived' in query and 'response_text' not in query and 'content_url' not in query
    asyncio.run(catalog_api.public_catalog(SimpleNamespace()))
    assert connection.fetch.await_count==1


def test_public_catalog_route_needs_no_session():
    import inspect
    from app import webapp
    assert '"/api/public/catalog"' in inspect.getsource(webapp.auth)
