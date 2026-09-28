import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from scripts.load_smoke import run


@pytest.mark.parametrize("url,requests", [
    ("https://example.com", 1),
    ("http://127.0.0.1:8090", 151),
])
def test_smoke_check_refuses_remote_or_excessive_load(url, requests):
    with pytest.raises(ValueError):
        asyncio.run(run(url, requests, 1, Path("unused-credentials.json")))


def test_smoke_check_uses_password_login(tmp_path):
    async def check():
        credentials = tmp_path / "credentials.json"
        credentials.write_text(json.dumps({"username": "test", "password": "Test123!"}), encoding="utf-8")

        async def login(request):
            assert request.headers["X-Login-Request"] == "1"
            assert request.headers["Origin"] == str(server.make_url("/")).rstrip("/")
            assert await request.json() == {"username": "test", "password": "Test123!"}
            result = web.Response()
            result.set_cookie("sensi_session", "fake-session")
            return result

        async def listing(request):
            assert request.cookies["sensi_session"] == "fake-session"
            return web.Response()

        app = web.Application()
        app.router.add_post("/api/auth/password", login)
        app.router.add_get("/api/dashboard", listing)
        app.router.add_get("/api/orders", listing)
        async with TestServer(app) as server:
            assert await run(str(server.make_url("/")).rstrip("/"), 2, 1, credentials) == 0

    asyncio.run(check())
