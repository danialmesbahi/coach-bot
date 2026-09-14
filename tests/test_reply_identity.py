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
    connection = SimpleNamespace(fetchrow=AsyncMock(return_value={'id': 9}), execute=AsyncMock())

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
