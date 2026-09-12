"""Password-only HTTP boundaries, with no real accounts or Telegram traffic."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app import webapp


@pytest.mark.parametrize("scenario", ["success", "origin", "missing_header", "ip_limit", "account_limit", "oversize", "chunked", "malformed", "ingress", "untrusted"])
def test_password_login_boundary(monkeypatch, scenario):
    async def run():
        monkeypatch.setattr(webapp.settings, 'web_trust_ingress', scenario != 'untrusted')
        redis = AsyncMock()
        redis.incr.side_effect = [31] if scenario == 'ip_limit' else [1, 11] if scenario == 'account_limit' else None
        redis.incr.return_value = 1
        authenticate = AsyncMock(return_value={'id': 9, 'session_version': 4})
        monkeypatch.setattr(webapp.staff, 'authenticate', authenticate)
        app = web.Application(middlewares=[webapp.security_headers, webapp.errors])
        app['redis'], app['password_slots'] = redis, asyncio.Semaphore(2)
        app.router.add_post('/api/auth/password', webapp.password_login)
        async with TestClient(TestServer(app)) as client:
            headers = {'X-Login-Request':'1', 'X-Coach-Client-IP':'192.0.2.1', 'Content-Type':'application/json'}
            body = json.dumps({'username':'Example', 'password':'Example1!'})
            expected = 200
            if scenario == 'origin':
                headers['Origin'] = 'https://attacker.invalid'
                expected = 403
            elif scenario == 'missing_header':
                headers.pop('X-Login-Request')
                expected = 403
            elif scenario == 'ingress':
                headers.pop('X-Coach-Client-IP')
                headers['X-Forwarded-For'] = '192.0.2.99'
                expected = 403
            elif scenario in {'ip_limit','account_limit'}:
                expected = 429
            elif scenario in {'oversize','chunked'}:
                body = 'x' * 4097
                expected = 413
            elif scenario == 'malformed':
                body = '[]'
                expected = 400
            async def chunks():
                yield b'x' * 2048
                yield b'x' * 2049
            result = await client.post('/api/auth/password',data=chunks() if scenario == 'chunked' else body,headers=headers)
            assert result.status == expected
            if expected == 200:
                authenticate.assert_awaited_once()
                data = json.loads(redis.setex.await_args.args[2])
                assert data['staff_id'] == 9 and data['auth_method'] == 'password'
                assert result.cookies['sensi_session']['httponly']
                assert result.cookies['sensi_session']['samesite'] == 'Strict'
            else:
                authenticate.assert_not_awaited()
            keys = [call.args[0] for call in redis.incr.await_args_list]
            if scenario == 'success':
                assert ':ip:192.0.2.1:' in keys[0]
                assert ':account:' in keys[1] and 'Example' not in keys[1]
            elif scenario == 'untrusted':
                assert all('192.0.2.1' not in key for key in keys)
    asyncio.run(run())


def test_telegram_and_test_login_routes_are_removed():
    from pathlib import Path
    source = Path('app/webapp.py').read_text(encoding='utf-8')
    assert '/api/auth/password' in source
    for route in ('/api/auth/telegram', '/api/auth/dev', '/api/auth/bot', '/auth/telegram'):
        assert route not in source
    assert 'web_login_router' not in Path('app/main.py').read_text(encoding='utf-8')


def test_staff_cannot_create_accounts_or_reset_superiors():
    from app.services import staff
    actor = {'role':'staff','staff_id':9,'version':1}
    with pytest.raises(web.HTTPForbidden):
        asyncio.run(staff.team_change(actor, {'action':'create'}, asyncio.Semaphore(2)))
