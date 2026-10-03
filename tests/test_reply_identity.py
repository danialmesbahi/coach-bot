"""Web replies retain the authenticated author, including password-only staff."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app import webapp


@pytest.mark.parametrize('telegram_id', [None, 12345])
@pytest.mark.parametrize('attachment', [False, True])
def test_reply_persists_staff_identity(monkeypatch, telegram_id, attachment):
    actor = {'staff_id': 22, 'display_name': 'Admin 2', 'telegram_id': telegram_id}
    connection = SimpleNamespace(fetchrow=AsyncMock(return_value={'id': 9}), execute=AsyncMock(), fetchval=AsyncMock(return_value=None))
    @asynccontextmanager
    async def transaction():
        yield
    connection.transaction=transaction

    @asynccontextmanager
    async def acquire():
        yield connection

    monkeypatch.setattr(webapp.repo.db, 'acquire', acquire)
    monkeypatch.setattr(webapp.repo, 'get_user_by_id', AsyncMock(return_value={'telegram_id': 999}))
    sent = SimpleNamespace(message_id=77, document=SimpleNamespace(file_id='file-id'))
    bot = SimpleNamespace(send_message=AsyncMock(return_value=sent), send_document=AsyncMock(return_value=sent))

    class Request(dict):
        content_type = 'multipart/form-data' if attachment else 'application/json'
        match_info = {'user_id': '9'}
        app = {'bot': bot}

        async def json(self):
            # A client-supplied author must never override the authenticated session.
            return {'message': 'Hello', 'sender_name': 'Someone else'}

        async def multipart(self):
            part = SimpleNamespace(name='file', filename='plan.pdf', read_chunk=AsyncMock(side_effect=[b'%PDF-1.4\n', b'']))
            return SimpleNamespace(next=AsyncMock(side_effect=[part, None]))

    result = asyncio.run(webapp._send_reply(Request(actor=actor)))
    assert result.status == 200
    query, *values = connection.execute.await_args.args
    assert 'sender_staff_id,sender_name' in query
    assert values[3] == telegram_id  # Do not accidentally attribute it to the customer.
    assert values[11:] == [22, 'Admin 2']
    assert values[5] == ('document' if attachment else 'text')
    assert webapp._web_message({'sender_staff_id': values[11], 'sender_name': values[12]})['sender_name'] == 'Admin 2'


@pytest.mark.parametrize('owned',[False,True])
def test_record_attachment_checks_customer_and_keeps_photo_method(monkeypatch,owned):
    from aiohttp import web
    file={'id':7,'user_id':9,'file_id':'photo-id','storage_key':None,'source':'chat','source_id':8,'filename':'photo.jpg','mime_type':'image/jpeg','byte_size':400}
    connection=SimpleNamespace(fetchrow=AsyncMock(return_value=file if owned else None),fetchval=AsyncMock(return_value='photo'))
    @asynccontextmanager
    async def acquire(): yield connection
    monkeypatch.setattr(webapp.db,'acquire',acquire)
    monkeypatch.setattr(webapp.repo,'get_user_by_id',AsyncMock(return_value={'telegram_id':999}))
    save=AsyncMock();monkeypatch.setattr(webapp.repo,'add_support_message',save)
    sent=SimpleNamespace(message_id=77,photo=[SimpleNamespace(file_id='sent-photo')])
    bot=SimpleNamespace(send_message=AsyncMock(),send_photo=AsyncMock(return_value=sent),send_document=AsyncMock())
    class Request(dict):
        content_type='application/json';match_info={'user_id':'9'};app={'bot':bot}
        async def json(self): return {'message':'Caption','record_file_id':7}
    if not owned:
        with pytest.raises(web.HTTPNotFound): asyncio.run(webapp._send_reply(Request(actor={'role':'leader'})))
        bot.send_message.assert_not_awaited();save.assert_not_awaited()
    else:
        result=asyncio.run(webapp._send_reply(Request(actor={'role':'leader'})))
        assert result.status==200
        bot.send_photo.assert_awaited_once_with(999,'photo-id',caption='Caption')
        bot.send_document.assert_not_awaited()
    query,*args=connection.fetchrow.await_args.args
    assert 'user_id=$2' in query and args==[7,9]
