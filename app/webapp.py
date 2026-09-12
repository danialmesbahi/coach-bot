from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from datetime import date, datetime
from decimal import Decimal
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import parse_qsl, quote
from zoneinfo import ZoneInfo
from weakref import WeakValueDictionary

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile
from aiohttp import web
import asyncpg
from redis.asyncio import Redis

from app.config import get_settings
from app.db import repositories as repo
from app.db.core import db
from app.utils.photos import normalize_photos
from app.services import web_login, staff
from app.utils.media import BoundedBuffer, _inspect_upload, _sniff_download


settings = get_settings()
STATIC = Path(__file__).with_name("web")
SESSION_COOKIE = "sensi_session"
LOG = logging.getLogger(__name__)

SALES_PERIODS = {
    "day": ("paid_at >= date_trunc('day', NOW())", "date_trunc('hour', paid_at)", "date_trunc('day', NOW())", "date_trunc('hour', NOW())", "1 hour"),
    "week": ("paid_at >= date_trunc('week', NOW())", "date_trunc('day', paid_at)", "date_trunc('week', NOW())", "date_trunc('day', NOW())", "1 day"),
    "month": ("paid_at >= date_trunc('month', NOW())", "date_trunc('day', paid_at)", "date_trunc('month', NOW())", "date_trunc('day', NOW())", "1 day"),
    "all": ("paid_at IS NOT NULL", "date_trunc('month', paid_at)", "COALESCE((SELECT date_trunc('month', MIN(paid_at)) FROM orders WHERE paid_at IS NOT NULL), date_trunc('month', NOW()))", "COALESCE((SELECT date_trunc('month', MAX(paid_at)) FROM orders WHERE paid_at IS NOT NULL), date_trunc('month', NOW()))", "1 month"),
}

ASSET_FILES = {
    "app.css", "app.js", "IRANYekanXVFaNumVF.woff2", "InterVariable.woff2",
    "offline.html", "icon-180.png", "icon-192.png", "icon-512.png",
}



def _default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def response(data, status=200):
    return web.json_response(data, status=status, dumps=lambda value: json.dumps(value, ensure_ascii=False, default=_default))


def validate_telegram_auth(raw: str | dict, *, webapp: bool, now: int | None = None) -> dict | None:
    if not isinstance(raw, (str, dict)):
        return None
    data = dict(parse_qsl(raw, keep_blank_values=True)) if isinstance(raw, str) else dict(raw)
    received = data.pop("hash", "")
    if not isinstance(received, str) or not re.fullmatch(r"[0-9a-f]{64}", received) or "auth_date" not in data:
        return None
    check = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    if webapp:
        secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    else:
        secret = hashlib.sha256(settings.bot_token.encode()).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    try:
        fresh = abs((now or int(time.time())) - int(data["auth_date"])) <= 300
    except (TypeError, ValueError):
        return None
    if not fresh or not hmac.compare_digest(received, expected):
        return None
    if webapp:
        try:
            user = json.loads(data.get("user", "{}"))
        except (json.JSONDecodeError, TypeError):
            return None
    else:
        user = data
    if not isinstance(user, dict):
        return None
    try:
        user["id"] = int(user["id"])
    except (KeyError, TypeError, ValueError):
        return None
    return user


async def _new_session(request: web.Request, telegram_id: int, *, auth_method: str = "telegram") -> str:
    account = await staff.by_telegram(telegram_id)
    if not account or account['status'] != 'active' or (auth_method != 'development' and account['auth_mode'] != auth_method):
        raise web.HTTPForbidden(text="This account has no management access")
    token = secrets.token_urlsafe(32)
    actor = {"telegram_id": telegram_id, "staff_id": account['id'], "version": account['session_version'], "csrf": secrets.token_urlsafe(24), "auth_method": auth_method}
    await request.app["redis"].setex(
        f"web:session:{token}", settings.web_session_hours * 3600, json.dumps(actor)
    )
    return token


def _set_session_cookie(result: web.StreamResponse, token: str):
    result.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.web_session_hours * 3600,
        httponly=True,
        secure=settings.app_env.lower() == "production",
        samesite="Strict",
        path="/",
    )


@web.middleware
async def security_headers(request: web.Request, handler):
    try:
        result = await handler(request)
    except web.HTTPException as exc:
        result = exc
    result.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self' https://telegram.org; "
                "style-src 'self'; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self'; "
                "frame-src 'self' blob: https://oauth.telegram.org https://t.me; object-src 'none'; frame-ancestors 'self' https://web.telegram.org"
            ),
        }
    )
    if settings.app_env.lower() == "production":
        result.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/api/"):
        result.headers["Cache-Control"] = "no-store"
    return result


@web.middleware
async def auth(request: web.Request, handler):
    public = request.path in {"/", "/health", "/manifest.webmanifest", "/service-worker.js", "/api/config", "/api/auth/telegram", "/api/auth/dev", "/api/auth/bot/start", "/api/auth/bot/poll", "/auth/telegram"} or request.path.startswith("/assets/")
    if public:
        return await handler(request)
    actor = await _session_actor(request)
    if not actor:
        return response({"error": "unauthorized"}, 401)
    request["actor"] = actor
    route_name = getattr(handler, '__name__', '')
    if route_name not in staff.ROUTE_PERMISSIONS:
        return response({'error': 'permission_denied'}, 403)
    staff.require(actor, staff.ROUTE_PERMISSIONS[route_name])
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), actor["csrf"]):
            return response({"error": "invalid_csrf"}, 403)
        origin = request.headers.get("Origin")
        forwarded_proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",", 1)[0].strip()
        forwarded_host = request.headers.get("X-Forwarded-Host", request.host).split(",", 1)[0].strip()
        if origin and origin.rstrip("/") != f"{forwarded_proto}://{forwarded_host}":
            return response({"error": "invalid_origin"}, 403)
    if await _rate_limited(request, "api", 180):
        result = response({"error": "rate_limited"}, 429)
        result.headers["Retry-After"] = "60"
        return result
    return await handler(request)


async def _session_actor(request: web.Request):
    """Same authorization for ordinary requests and already-open event streams."""
    token = request.cookies.get(SESSION_COOKIE, "")
    raw = await request.app["redis"].get(f"web:session:{token}") if token else None
    if not raw:
        return None
    actor = json.loads(raw)
    # Untagged legacy sessions may have been issued by the test-login bypass.
    real_login_required = not settings.web_dev_login or settings.app_env.lower() == "production"
    if real_login_required and actor.get("auth_method") not in {"telegram", "password_telegram"}:
        await request.app["redis"].delete(f"web:session:{token}")
        return None
    account = await staff.by_telegram(actor["telegram_id"])
    if not account or account['status'] != 'active' or account['id'] != actor.get('staff_id') or account['session_version'] != actor.get('version'):
        await request.app["redis"].delete(f"web:session:{token}")
        return None
    return {**actor, **staff.public(account)}


@web.middleware
async def errors(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError):
        return response({"error": "invalid_json"}, 400)
    except Exception:
        LOG.exception("web request failed", extra={"path": request.path})
        return response({"error": "server_error"}, 500)


async def _rate_limited(request: web.Request, scope: str, limit: int, window: int = 60) -> bool:
    key = f"web:limit:{scope}:{request['actor']['telegram_id']}:{int(time.time()) // window}"
    count = await request.app["redis"].incr(key)
    if count == 1:
        await request.app["redis"].expire(key, window + 10)
    return count > limit


def management_record_visible(role: str, rows: dict | list[dict] | None) -> bool:
    if role in {"sensi", "leader", "platform", "staff"}:
        return True
    records = rows if isinstance(rows, list) else [rows] if rows else []
    return any(bool(row.get("paid_at")) for row in records)


def _web_user(user: dict) -> dict:
    result = dict(user)
    photos = normalize_photos(result.pop("body_photo_file_ids", []))
    if not photos and result.get("body_photo_file_id"):
        photos = normalize_photos([result["body_photo_file_id"]])
    result.pop("body_photo_file_id", None)
    result["photo_count"] = len(photos)
    return result


def _web_order(order: dict) -> dict:
    result = dict(order)
    snapshot = repo._json_object(result.get("form_snapshot"))
    photos = normalize_photos(snapshot.pop("body_photo_file_ids", []))
    if not photos and snapshot.get("body_photo_file_id"):
        photos = normalize_photos([snapshot["body_photo_file_id"]])
    snapshot.pop("body_photo_file_id", None)
    result["form_snapshot"] = snapshot
    result["photo_count"] = len(photos)
    result.pop("payment_authority", None)
    result.pop("plan_file_id", None)
    if "receipt_file_id" in result:
        result["receipt_file_id"] = bool(result["receipt_file_id"])
    return result


def _web_message(message: dict) -> dict:
    result = dict(message)
    result["has_attachment"] = bool(result.pop("file_id", None))
    return result




async def _telegram_media(request: web.Request, file_id: str, fallback_type: str = "application/octet-stream", file_name: str | None = None):
    cache_key = hashlib.sha256(file_id.encode()).hexdigest()
    cached = request.app["media_cache"].get(cache_key)
    if cached and cached[0] > time.monotonic():
        body, content_type, name, previewable = cached[1:]
        disposition = "attachment" if request.query.get("download") == "1" or not previewable else "inline"
        return web.Response(body=body, content_type=content_type, headers={"Cache-Control": "private, max-age=86400", "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(name)}"})
    try:
        async with asyncio.timeout(12), request.app["media_slots"]:
            telegram_file = await request.app["bot"].get_file(file_id)
            if telegram_file.file_size and telegram_file.file_size > settings.max_plan_file_mb * 1024 * 1024:
                raise web.HTTPRequestEntityTooLarge(max_size=settings.max_plan_file_mb * 1024 * 1024, actual_size=telegram_file.file_size)
            content = BoundedBuffer(settings.max_plan_file_mb * 1024 * 1024)
            await request.app["bot"].download_file(telegram_file.file_path, destination=content)
    except TimeoutError:
        raise web.HTTPServiceUnavailable(headers={"Cache-Control": "no-store", "Retry-After": "3"})
    except TelegramBadRequest:
        raise web.HTTPNotFound(headers={"Cache-Control": "private, max-age=3600"})
    except ValueError:
        return response({"error": "file_too_large"}, 413)
    body = content.getvalue()
    name = Path(file_name or telegram_file.file_path or "attachment").name[:150]
    content_type, kind = _sniff_download(name, body, fallback_type)
    previewable = kind in {"image", "animation", "video", "audio", "voice"} or content_type == "application/pdf"
    if previewable and len(body) <= 10 * 1024 * 1024:
        # Budget actual retained bytes, not 128 x 10MiB entries (~1.25GiB).
        while request.app["media_cache"] and (len(request.app["media_cache"]) >= 128 or sum(len(item[1]) for item in request.app["media_cache"].values()) + len(body) > 32 * 1024 * 1024):
            request.app["media_cache"].pop(next(iter(request.app["media_cache"])))
        request.app["media_cache"][cache_key] = (time.monotonic() + 21_600, body, content_type, name, previewable)
    disposition = "attachment" if request.query.get("download") == "1" or not previewable else "inline"
    return web.Response(body=body, content_type=content_type, headers={"Cache-Control": "private, max-age=86400", "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(name)}"})


def _safe_page(request: web.Request):
    try:
        return min(10_000, max(1, int(request.query.get("page", "1"))))
    except ValueError:
        return 1


def _sales_period(raw: str | None) -> str:
    return raw if raw in SALES_PERIODS else "month"


async def _sales_snapshot(period: str) -> dict:
    where, bucket, start, end, step = SALES_PERIODS[period]
    async with db.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SET LOCAL TIME ZONE 'Asia/Tehran'")
            metric = await connection.fetchrow(
                f"SELECT COUNT(*) AS orders, COALESCE(SUM(amount),0) AS revenue FROM orders WHERE {where}"
            )
            trend = await connection.fetch(
                f"""
                WITH periods AS (
                    SELECT generate_series({start}, {end}, INTERVAL '{step}') AS bucket
                ), totals AS (
                    SELECT {bucket} AS bucket, COUNT(*) AS orders, COALESCE(SUM(amount),0) AS revenue
                    FROM orders WHERE {where}
                    GROUP BY 1
                )
                SELECT periods.bucket, COALESCE(totals.orders,0) AS orders, COALESCE(totals.revenue,0) AS revenue
                FROM periods LEFT JOIN totals USING (bucket)
                ORDER BY periods.bucket
                """
            )
    return {"period": period, "orders": int(metric["orders"]), "revenue": metric["revenue"], "trend": [dict(row) for row in trend]}


async def _sales_items(period: str, page: int, page_size: int = 20):
    where = SALES_PERIODS[period][0]
    offset = (page - 1) * page_size
    async with db.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SET LOCAL TIME ZONE 'Asia/Tehran'")
            rows = await connection.fetch(f"""
                SELECT o.id AS order_id,o.amount,o.paid_at,p.title AS product_title,
                       u.id AS user_id,u.name,u.first_name,u.last_name,u.username,
                       COUNT(*) OVER() AS total_count
                FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id
                WHERE {where}
                ORDER BY o.paid_at DESC,o.id DESC LIMIT $1 OFFSET $2
            """, page_size, offset)
    items = [dict(row) for row in rows]
    total = int(items[0].pop("total_count")) if items else 0
    return items, total


async def _cached(request: web.Request, key: str, ttl: float, load):
    cache = request.app["read_cache"]
    cached = cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    async with request.app["read_cache_locks"].setdefault(key, asyncio.Lock()):
        cached = cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        value = await load()
        if len(cache) >= 256:
            oldest = next(iter(cache))
            cache.pop(oldest, None)
            lock = request.app["read_cache_locks"].get(oldest)
            if lock and not lock.locked():
                request.app["read_cache_locks"].pop(oldest, None)
        cache[key] = (time.monotonic() + ttl, value)
        return value


async def index(_):
    return web.FileResponse(STATIC / "index.html")


async def asset(request: web.Request):
    name = request.match_info["name"]
    if name not in ASSET_FILES:
        raise web.HTTPNotFound()
    return web.FileResponse(STATIC / name)


async def manifest(_):
    return web.FileResponse(STATIC / "manifest.webmanifest")


async def service_worker(_):
    result = web.FileResponse(STATIC / "service-worker.js")
    result.headers["Cache-Control"] = "no-cache"
    return result


async def health(request: web.Request):
    try:
        async with asyncio.timeout(2):
            async with db.acquire() as connection:
                await connection.fetchval("SELECT 1")
            await request.app["redis"].ping()
    except Exception:
        return response({"status": "unavailable"}, 503)
    return response({"status": "ok"})


async def config(_):
    return response(
        {
            "botUsername": settings.bot_username.lstrip("@"),
            "devLogin": settings.web_dev_login and settings.app_env.lower() != "production",
        }
    )


async def telegram_widget_login(request: web.Request):
    user = validate_telegram_auth(dict(request.query), webapp=False)
    if not user:
        raise web.HTTPUnauthorized(text="Invalid Telegram login")
    token = await _new_session(request, user["id"])
    result = web.HTTPFound("/")
    _set_session_cookie(result, token)
    return result


async def bot_login(request: web.Request):
    # A non-simple same-origin request: cross-site forms cannot initiate/redeem a login.
    if request.headers.get("X-Login-Request") != "1" or request.headers.get("Sec-Fetch-Site") == "cross-site":
        return response({"error": "invalid_origin"}, 403)
    redis = request.app["redis"]
    starting = request.path.endswith("/start")
    client = request.remote or "unknown"
    if settings.web_trust_ingress:
        # Docker publishes only ingress, which replaces this header from its socket peer.
        try:
            client = str(ip_address(request.headers.get("X-Coach-Client-IP", "")))
        except ValueError:
            return response({"error": "invalid_ingress"}, 403)
    rate_key = f"web:login:rate:{client}:{'start' if starting else 'poll'}:{int(time.time()) // 60}"
    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 70)
    if count > (20 if starting else 240):
        result = response({"error": "rate_limited"}, 429)
        result.headers["Retry-After"] = "60"
        return result
    if starting:
        username = settings.bot_username.lstrip("@")
        if not username:
            return response({"error": "login_not_configured"}, 503)
        if request.content_length and request.content_length > 4096:
            return response({'error': 'payload_too_large'}, 413)
        body = {}
        if request.can_read_body:
            payload = BoundedBuffer(4096)
            try:
                async for chunk in request.content.iter_chunked(1024):
                    payload.write(chunk)
            except ValueError:
                return response({'error': 'payload_too_large'}, 413)
            body = json.loads(payload.getvalue())
        if not isinstance(body, dict):
            return response({'error': 'invalid_payload'}, 400)
        context = await staff.login_context(body, request.app['password_slots']) if body.get('username') else {}
        challenge, proof, code = await web_login.create(redis, context)
        result = response({"url": f"https://t.me/{username}?start=login_{challenge}", "code": code, "expiresIn": web_login.TTL})
        result.set_cookie(web_login.COOKIE, f"{challenge}.{proof}", max_age=web_login.TTL,
                          httponly=True, samesite="Strict", path="/api/auth/bot",
                          secure=settings.app_env.lower() == "production" or request.headers.get("X-Forwarded-Proto", request.scheme) == "https")
        return result
    status, context = await web_login.consume(redis, request.cookies.get(web_login.COOKIE, ""), with_context=True)
    account = await staff.finish_login(context, context['telegram_id']) if status == 'approved' else None
    if status == 'approved' and not account:
        status = 'denied'
    result = response({"status": status})
    if status == "approved":
        token = await _new_session(request, account['telegram_id'], auth_method=account['auth_mode'])
        _set_session_cookie(result, token)
    if status != "pending":
        result.del_cookie(web_login.COOKIE, path="/api/auth/bot")
    return result


async def telegram_webapp_login(request: web.Request):
    if request.content_length and request.content_length > 16_384:
        return response({"error": "payload_too_large"}, 413)
    body = await request.json()
    if not isinstance(body, dict):
        return response({"error": "invalid_telegram_auth"}, 400)
    user = validate_telegram_auth(body.get("initData", ""), webapp=True)
    if not user:
        return response({"error": "invalid_telegram_auth"}, 401)
    token = await _new_session(request, user["id"])
    result = response({"ok": True})
    _set_session_cookie(result, token)
    return result


async def dev_login(request: web.Request):
    if not settings.web_dev_login or settings.app_env.lower() == "production":
        raise web.HTTPNotFound()
    token = await _new_session(request, settings.sensi_id, auth_method="development")
    result = response({"ok": True})
    _set_session_cookie(result, token)
    return result


async def logout(request: web.Request):
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        await request.app["redis"].delete(f"web:session:{token}")
    result = response({"ok": True})
    result.del_cookie(SESSION_COOKIE, path="/")
    return result


async def session(request: web.Request):
    actor = request["actor"]
    return response({"role": actor["role"], "telegramId": actor["telegram_id"], "csrf": actor["csrf"], "staffId": actor['staff_id'], "displayName": actor['display_name'], "username": actor['username'], "permissions": sorted(staff.PERMISSIONS) if actor['role'] in {'leader', 'platform'} else actor['permissions']})


async def staff_profile(request):
    actor = request['actor']
    if request.method == 'POST':
        body = await request.json()
        name = body.get('display_name') if isinstance(body, dict) else None
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            return response({'error': 'invalid_profile'}, 400)
        async with db.acquire() as c, c.transaction():
            await c.execute('UPDATE staff_accounts SET display_name=$2,updated_at=NOW() WHERE id=$1', actor['staff_id'], name.strip())
            await staff.audit(c, actor, 'staff_profile', 'staff', actor['staff_id'], {'name': name.strip()})
        return response({'ok': True})
    return response(staff.public(actor))


async def staff_team(request):
    actor = request['actor']
    staff.require(actor, 'team')
    if request.method == 'POST':
        if await _rate_limited(request, 'team', 20):
            return response({'error': 'rate_limited'}, 429)
        body = await request.json()
        if not isinstance(body, dict):
            return response({'error': 'invalid_payload'}, 400)
        try:
            return response(await staff.team_change(actor, body))
        except (ValueError, TypeError):
            return response({'error': 'invalid_staff_data'}, 400)
        except asyncpg.UniqueViolationError:
            return response({'error': 'account_or_leader_exists'}, 409)
    page = _safe_page(request)
    async with db.acquire() as c:
        rows = await c.fetch("SELECT * FROM staff_accounts WHERE $1 OR role<>'platform' ORDER BY id LIMIT 20 OFFSET $2", actor['role'] == 'platform', (page-1)*20)
        total = await c.fetchval("SELECT COUNT(*) FROM staff_accounts WHERE $1 OR role<>'platform'", actor['role'] == 'platform')
    return response({'items': [staff.public(row) for row in rows], 'total': total, 'page': page, 'permissions': staff.PERMISSIONS, 'templates': staff.TEMPLATES})


async def staff_audit(request):
    staff.require(request['actor'], 'team')
    before = request.query.get('before', '')
    if before and (not before.isdigit() or len(before) > 18):
        return response({'error': 'invalid_cursor'}, 400)
    async with db.acquire() as c:
        rows = await c.fetch('''SELECT a.id,a.actor_staff_id,a.actor_name,a.action,a.target_type,a.target_id,a.created_at,a.metadata
            FROM audit_logs a LEFT JOIN staff_accounts s ON s.id=a.actor_staff_id
            WHERE ($1::bigint IS NULL OR a.id<$1) AND ($2 OR s.role IS DISTINCT FROM 'platform')
            ORDER BY a.id DESC LIMIT 51''', int(before) if before else None, request['actor']['role'] == 'platform')
    return response({'items': [dict(row) for row in rows[:50]], 'next': rows[49]['id'] if len(rows) > 50 else None})


async def collaboration(request):
    actor = request['actor']
    kind, target_id = request.match_info['kind'], int(request.match_info['target_id'])
    permission = 'chats.read' if kind == 'thread' else 'orders.read'
    staff.require(actor, permission)
    table = 'users' if kind == 'thread' else 'orders'
    async with db.acquire() as c, c.transaction():
        if not await c.fetchval(f'SELECT id FROM {table} WHERE id=$1', target_id):
            raise web.HTTPNotFound()
        if request.method == 'POST':
            staff.require(actor, 'chats.reply' if kind == 'thread' else 'orders.review')
            body = await request.json()
            if not isinstance(body, dict):
                return response({'error': 'invalid_payload'}, 400)
            if body.get('action') == 'note':
                text = body.get('text')
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
                    return response({'error': 'invalid_note'}, 400)
                await c.execute('INSERT INTO staff_notes(target_type,target_id,staff_id,author_name,body) VALUES($1,$2,$3,$4,$5)', kind, target_id, actor['staff_id'], actor['display_name'], text.strip())
                await staff.audit(c, actor, 'internal_note', kind, target_id)
            elif body.get('action') == 'assign':
                assignee = body.get('staff_id')
                if assignee is not None:
                    if type(assignee) is not int:
                        return response({'error': 'invalid_assignee'}, 400)
                    target = await c.fetchrow("SELECT * FROM staff_accounts WHERE id=$1 AND status='active'", assignee)
                    if not target or not staff.can(target, permission):
                        return response({'error': 'invalid_assignee'}, 400)
                if actor['role'] == 'staff' and assignee not in {None, actor['staff_id']}:
                    raise web.HTTPForbidden()
                await c.execute('INSERT INTO staff_assignments(target_type,target_id) VALUES($1,$2) ON CONFLICT DO NOTHING', kind, target_id)
                current = await c.fetchrow('SELECT * FROM staff_assignments WHERE target_type=$1 AND target_id=$2 FOR UPDATE', kind, target_id)
                if body.get('version', 1) != current['version'] or actor['role'] == 'staff' and current['staff_id'] not in {None, actor['staff_id']}:
                    return response({'error': 'assignment_changed'}, 409)
                await c.execute('UPDATE staff_assignments SET staff_id=$3,version=version+1,updated_at=NOW() WHERE target_type=$1 AND target_id=$2', kind, target_id, assignee)
                await staff.audit(c, actor, 'assigned', kind, target_id, {'staff_id': assignee})
            else:
                return response({'error': 'invalid_action'}, 400)
        assignment = await c.fetchrow('''SELECT a.staff_id,a.version,s.display_name FROM staff_assignments a
            LEFT JOIN staff_accounts s ON s.id=a.staff_id WHERE a.target_type=$1 AND a.target_id=$2''', kind, target_id)
        notes = await c.fetch('SELECT id,author_name,body,created_at FROM staff_notes WHERE target_type=$1 AND target_id=$2 ORDER BY id DESC LIMIT 30', kind, target_id)
        members = await c.fetch("SELECT id,display_name FROM staff_accounts WHERE status='active' AND (role IN ('leader','platform') OR $1=ANY(permissions)) ORDER BY display_name LIMIT 100", permission)
    return response({'assignment': dict(assignment) if assignment else {'staff_id': None, 'version': 1}, 'notes': [dict(n) for n in notes], 'members': [dict(m) for m in members]})


def _broadcast_update(app: web.Application, payload: str):
    try:
        update = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(update, dict) or len(payload) > 4096:
        return
    table = update.get("table")
    if table in {"users", "orders", "support_messages", "sales_gate"}:
        for key in tuple(app["read_cache"]):
            if key.startswith("dashboard:"):
                app["read_cache"].pop(key, None)
            elif table in {"users", "orders"} and key.startswith("orders:"):
                app["read_cache"].pop(key, None)
            elif table in {"users", "support_messages"} and key.startswith("threads:"):
                app["read_cache"].pop(key, None)
    if table == "products":
        app["read_cache"].pop("products", None)
    for queue in tuple(app["realtime_subscribers"]):
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(payload)


async def _listen_for_updates(app: web.Application):
    delay = 1
    while True:
        connection = None
        try:
            connection = await asyncpg.connect(settings.database_url)
            await connection.add_listener(
                "coach_updates",
                lambda _connection, _pid, _channel, payload: _broadcast_update(app, payload),
            )
            delay = 1
            while not connection.is_closed():
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("realtime database listener disconnected")
        finally:
            if connection and not connection.is_closed():
                await connection.close()
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)


async def realtime_events(request: web.Request):
    if len(request.app["realtime_subscribers"]) >= 64:
        return response({"error": "too_many_streams"}, 429)
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    request.app["realtime_subscribers"].add(queue)
    result = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
    try:
        await result.prepare(request)
        await result.write(b"retry: 3000\n\n")
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=20)
                current_actor = await _session_actor(request)
                if not current_actor:
                    await result.write(b'event: session-expired\ndata: {}\n\n')
                    break
                table = json.loads(payload).get('table')
                needed = {'support_messages':'chats.read', 'users':'identity.read', 'orders':'records.read', 'products':'records.read', 'sales_gate':'sales.manage', 'staff_accounts':'team', 'staff_assignments':'collaboration', 'staff_notes':'collaboration'}.get(table, 'team')
                if table == 'orders' and staff.can(current_actor, 'sales.read'):
                    needed = None
                if not staff.can(current_actor, needed):
                    continue
                await result.write(f"event: update\ndata: {payload}\n\n".encode())
            except TimeoutError:
                if not await _session_actor(request):
                    await result.write(b'event: session-expired\ndata: {}\n\n')
                    break
                await result.write(b": keepalive\n\n")
    except (ConnectionResetError, RuntimeError):
        pass
    finally:
        request.app["realtime_subscribers"].discard(queue)
    return result


async def dashboard(request: web.Request):
    role = request["actor"]["role"]
    period = _sales_period(request.query.get("period"))

    async def load():
        if role == "admin_team":
            buyers, users, sales, sales_open = await asyncio.gather(
                repo.purchaser_count(), repo.user_count(), _sales_snapshot(period), repo.sales_are_open()
            )
            counts = {"actionable": 0, "receipts": 0, "new_orders": 0, "designing": 0, "needs_info": 0, "unread": 0, "active": buyers}
        else:
            counts, buyers, users, sales, sales_open = await asyncio.gather(
                repo.sensi_dashboard_counts(), repo.purchaser_count(), repo.user_count(), _sales_snapshot(period), repo.sales_are_open()
            )
        data = {"role": role, "counts": counts, "sales": sales, "salesOpen": sales_open, "buyers": buyers, "users": users}
        if role == "admin_team":
            data["commission"] = round(int(sales["revenue"]) * settings.development_team_percent / 100)
            data["commissionPercent"] = settings.development_team_percent
        return data

    data = dict(await _cached(request, f"dashboard:{role}:{period}", 2, load))
    # Cached aggregates are shared, but the returned payload is permission-scoped.
    if not staff.can(request['actor'], 'sales.read'):
        data['sales'] = {'period': period, 'revenue': 0, 'orders': 0, 'trend': []}
    data['counts'] = dict(data['counts'])
    if not staff.can(request['actor'], 'chats.read'):
        data['counts']['unread'] = 0
    if not staff.can(request['actor'], 'orders.read'):
        for key in ('actionable', 'receipts', 'new_orders', 'designing', 'needs_info'):
            data['counts'][key] = 0
    return response(data)


async def sales_gate(request: web.Request):
    staff.require(request['actor'], 'sales.manage')
    body = await request.json()
    is_open = body.get("open") if isinstance(body, dict) else None
    if not isinstance(is_open, bool):
        return response({"error": "invalid_sales_state"}, 400)
    current = await repo.set_sales_open(is_open)
    request.app["read_cache"].clear()
    await repo.add_audit(request["actor"]["telegram_id"], "web_sales_gate", "sales_gate", 1, {"open": current})
    return response({"open": current})


async def orders(request: web.Request):
    staff.require(request['actor'], 'orders.read')
    page = _safe_page(request)
    status = request.query.get("status")
    query = request.query.get("q", "")
    async def load():
        (rows, total), counts = await asyncio.gather(repo.list_sensi_orders(page, 20, status, query), repo.sensi_dashboard_counts())
        return {"items": rows, "total": total, "page": page, "pageSize": 20, "counts": counts}
    key = f"orders:{page}:{status or 'all'}:{query.strip().lower()[:80]}"
    return response(await _cached(request, key, 2, load))


async def order_detail(request: web.Request):
    row = await repo.get_order(int(request.match_info["order_id"]))
    if not row or not management_record_visible(request["actor"]["role"], row):
        raise web.HTTPNotFound()
    result = _web_order(row)
    if staff.can(request['actor'], 'orders.read'):
        async with db.acquire() as c:
            last_request = await c.fetchval("SELECT metadata->>'message' FROM audit_logs WHERE target_type='order' AND target_id=$1 AND action='web_needs_info' ORDER BY created_at DESC,id DESC LIMIT 1", row["id"])
        result["info_request"] = last_request
    return response(result)


async def order_action(request: web.Request):
    staff.require(request['actor'], 'orders.read')
    order_id = int(request.match_info["order_id"])
    body = await request.json()
    if not isinstance(body, dict):
        return response({"error": "invalid_payload"}, 400)
    action = body.get("action")
    if action not in ("approve_receipt", "reject_receipt", "in_progress", "needs_info"):
        return response({"error": "invalid_action"}, 400)
    staff.require(request['actor'], 'payments.review' if action in {'approve_receipt', 'reject_receipt'} else 'orders.review')
    info = body.get("message", "")
    if action == "needs_info" and (not isinstance(info, str) or not info.strip() or len(info.strip()) > 1000):
        return response({"error": "message_required"}, 400)
    actor = request["actor"]["telegram_id"]
    current = await repo.get_order(order_id)
    if not current:
        raise web.HTTPNotFound()
    changed = None
    if action == "approve_receipt":
        if current.get("payment_method") != "card_to_card":
            return response({"error": "gateway_payment_is_automatic"}, 409)
        changed = await repo.approve_card_payment(order_id, actor)
        message = "✅ پرداخت شما تأیید شد. اطلاعات دوره شما در صف بررسی مربی قرار گرفت."
    elif action == "reject_receipt":
        if current.get("payment_method") != "card_to_card":
            return response({"error": "gateway_payment_is_automatic"}, 409)
        changed = await repo.reject_card_payment(order_id, actor)
        message = "❌ رسید پرداخت تأیید نشد. لطفاً رسید درست را دوباره در ربات ارسال کنید."
    elif action in {"in_progress", "needs_info"}:
        changed = await repo.update_order_status(order_id, action)
        message = (f"اطلاعات تکمیلی سفارش ORD-{order_id:06d}\n\n{info.strip()}\n\nپاسخ و عکس‌های درخواستی را از بخش «پیام به مربی» ارسال کنید و در پایان دکمه ارسال پیام را بزنید." if action == "needs_info" else "🏋️ اطلاعات دوره تأیید شد و طراحی برنامه شما آغاز شد.")
    else:
        return response({"error": "invalid_action"}, 400)
    if not changed:
        return response({"error": "invalid_transition"}, 409)
    await repo.add_audit(actor, f"web_{action}", "order", order_id, {"message": info.strip()} if action == "needs_info" else {})
    request.app["read_cache"].clear()
    notified = False
    try:
        sent = await request.app["bot"].send_message(current["telegram_id"], message)
        notified = True
        if action == "needs_info":
            await repo.add_support_message(current["telegram_id"], sent.message_id, direction="sensi", sender_telegram_id=actor, content_text=message)
    except Exception:
        LOG.exception("Order %s updated but its Telegram notification failed", order_id)
    return response({"ok": True, "notification_sent": notified})


async def upload_plan(request: web.Request):
    staff.require(request['actor'], 'orders.deliver')
    order_id = int(request.match_info["order_id"])
    order = await repo.get_order(order_id)
    if not order or order["status"] not in {"in_progress", "ready"}:
        return response({"error": "invalid_transition"}, 409)
    if request.app['upload_slots'].locked():
        return response({'error': 'uploads_busy'}, 503)
    try:
        async with asyncio.timeout(65), request.app['upload_slots'], db.acquire() as c, c.transaction():
            locked = await c.fetchval('SELECT pg_try_advisory_xact_lock(hashtextextended($1,0))', f'plan-delivery:{order_id}')
            if not locked:
                return response({'error': 'delivery_in_progress'}, 409)
            # Recheck inside the cross-process lock: another coach may have delivered.
            order = await repo.get_order(order_id)
            if not order or order['status'] not in {'in_progress', 'ready'}:
                return response({'error': 'invalid_transition'}, 409)
            return await _upload_plan(request, order)
    except TimeoutError:
        return response({'error': 'upload_timeout'}, 503)


async def _upload_plan(request, order):
    order_id = order['id']
    reader = await request.multipart()
    part = await reader.next()
    if not part or part.name != "file" or not part.filename:
        return response({"error": "file_required"}, 400)
    filename = Path(part.filename.replace("\\", "/").rsplit("/", 1)[-1]).name[:150]
    limit = settings.max_plan_file_mb * 1024 * 1024
    async with asyncio.timeout(60):
        chunks, size = [], 0
        while chunk := await part.read_chunk():
            size += len(chunk)
            if size > limit:
                return response({"error": "file_too_large"}, 413)
            chunks.append(chunk)
        payload = b"".join(chunks)
        if not _inspect_upload(filename, payload):
            return response({"error": "invalid_file_type"}, 400)
        async with asyncio.timeout(60):
            sent = await request.app["bot"].send_document(
                order["telegram_id"], BufferedInputFile(payload, filename=filename), caption="✅ دوره جدید شما آماده است."
            )
    changed = await repo.attach_plan(order_id, sent.document.file_id, filename)
    if not changed:
        return response({"error": "save_failed"}, 409)
    await repo.add_audit(request["actor"]["telegram_id"], "web_deliver_plan", "order", order_id, {"filename": filename})
    return response({"ok": True})


async def threads(request: web.Request):
    staff.require(request['actor'], 'chats.read')
    page = _safe_page(request)
    query, unread = request.query.get("q", ""), request.query.get("unread") == "1"
    async def load():
        (rows, total), counts = await asyncio.gather(repo.support_threads(page, 20, query, unread), repo.support_thread_counts())
        return {"items": rows, "total": total, "page": page, "pageSize": 20, "counts": counts}
    return response(await _cached(request, f"threads:{page}:{int(unread)}:{query.strip().lower()[:80]}", 2, load))


async def thread_detail(request: web.Request):
    staff.require(request['actor'], 'chats.read')
    user_id = int(request.match_info["user_id"])
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise web.HTTPNotFound()
    await repo.mark_customer_messages_read(user_id)
    items = await repo.support_messages_for_user(user_id, 100)
    return response({"user": _web_user(user), "items": [_web_message(item) for item in items]})


async def reply_message(request: web.Request):
    staff.require(request['actor'], 'chats.reply')
    if await _rate_limited(request, "reply", 30):
        result = response({"error": "rate_limited"}, 429)
        result.headers["Retry-After"] = "60"
        return result
    if request.app["upload_slots"].locked():
        return response({"error": "uploads_busy"}, 503)
    try:
        async with asyncio.timeout(60), request.app["upload_slots"]:
            return await _send_reply(request)
    except TimeoutError:
        return response({"error": "upload_timeout"}, 503)


async def _read_part(part, limit: int) -> bytes:
    buffer = BoundedBuffer(limit)
    try:
        while chunk := await part.read_chunk():
            buffer.write(chunk)
    except ValueError:
        raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=limit + 1)
    return buffer.getvalue()


async def _send_reply(request: web.Request):
    user_id = int(request.match_info["user_id"])
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise web.HTTPNotFound()
    text, filename, payload = "", "", b""
    if request.content_type.startswith("multipart/"):
        reader, seen = await request.multipart(), set()
        while part := await reader.next():
            if part.name not in {"message", "file"} or part.name in seen:
                return response({"error": "invalid_multipart"}, 400)
            seen.add(part.name)
            if part.name == "message":
                text = (await _read_part(part, 16_000)).decode("utf-8").strip()
            elif part.name == "file" and part.filename:
                filename = Path(part.filename.replace("\\", "/").rsplit("/", 1)[-1]).name[:150]
                payload = await _read_part(part, settings.max_plan_file_mb * 1024 * 1024)
    else:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("message", ""), str):
            return response({"error": "invalid_message"}, 400)
        text = body.get("message", "").strip()
    inspected = _inspect_upload(filename, payload) if payload else None
    if payload and len(text) > 1024:
        return response({"error": "caption_too_long"}, 400)
    if len(text) > 4000 or (not text and not payload) or (payload and not inspected):
        return response({"error": "invalid_message"}, 400)
    bot = request.app["bot"]
    await bot.send_message(user["telegram_id"], "📩 پیام جدید از طرف سنسی")
    content_type, file_id = "text", None
    if payload:
        upload = BufferedInputFile(payload, filename=filename)
        mime_type, media_kind = inspected
        if media_kind == "image":
            sent = await bot.send_photo(user["telegram_id"], upload, caption=text or None)
            content_type, file_id = "photo", sent.photo[-1].file_id
        elif media_kind == "animation":
            sent = await bot.send_animation(user["telegram_id"], upload, caption=text or None)
            content_type, file_id = "animation", sent.animation.file_id
        elif media_kind == "video":
            sent = await bot.send_video(user["telegram_id"], upload, caption=text or None)
            content_type, file_id = "video", sent.video.file_id
        elif media_kind == "voice":
            sent = await bot.send_voice(user["telegram_id"], upload, caption=text or None)
            content_type, file_id = "voice", sent.voice.file_id
        elif media_kind == "audio":
            sent = await bot.send_audio(user["telegram_id"], upload, caption=text or None)
            content_type, file_id = "audio", sent.audio.file_id
        else:
            sent = await bot.send_document(user["telegram_id"], upload, caption=text or None)
            content_type, file_id = "document", sent.document.file_id
    else:
        sent = await bot.send_message(user["telegram_id"], text)
    await repo.add_support_message(
        user["telegram_id"], sent.message_id, direction="sensi", sender_telegram_id=request["actor"]["telegram_id"], content_type=content_type,
        content_text=text or None, file_id=file_id, file_name=filename or None,
        mime_type=inspected[0] if inspected else None, file_size=len(payload) if payload else None,
    )
    return response({"ok": True})


async def customers(request: web.Request):
    page = _safe_page(request)
    raw_product = request.query.get("product", "")
    product_id = int(raw_product) if raw_product.isdigit() and 0 < int(raw_product) <= 32767 else None
    (rows, total), products = await asyncio.gather(
        repo.purchaser_list(
            page,
            20,
            request.query.get("q", ""),
            request.query.get("activity", "all"),
            product_id,
            request.query.get("sort", "recent"),
        ),
        _cached(request, "products", 60, lambda: repo.get_products(active_only=False)),
    )
    return response({
        "items": rows,
        "total": total,
        "page": page,
        "pageSize": 20,
        "products": [{"id": item["id"], "title": item["title"]} for item in products],
    })


async def customer_avatar(request: web.Request):
    user_id = int(request.match_info["user_id"])
    user = await repo.purchaser_identity(user_id)
    if not user or not user["has_paid_order"]:
        raise web.HTTPNotFound()

    cached = request.app["avatar_cache"].get(user_id)
    if cached and cached[0] > time.monotonic():
        return web.Response(body=cached[1], content_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    cache_key = f"web:avatar:{user['telegram_id']}"
    file_id = await request.app["redis"].get(cache_key)
    try:
        # Telegram media must never hold every browser/proxy connection and block core APIs.
        async with asyncio.timeout(3), request.app["avatar_slots"]:
            if file_id is None:
                photos = await request.app["bot"].get_user_profile_photos(user["telegram_id"], limit=1)
                file_id = photos.photos[0][0].file_id if photos.photos else "-"
                await request.app["redis"].set(cache_key, file_id, ex=21_600)
            if file_id == "-":
                raise web.HTTPNotFound(headers={"Cache-Control": "private, max-age=3600"})
            telegram_file = await request.app["bot"].get_file(file_id)
            content = BoundedBuffer(2 * 1024 * 1024)
            await request.app["bot"].download_file(telegram_file.file_path, destination=content)
    except web.HTTPException:
        raise
    except TimeoutError:
        await request.app["redis"].delete(cache_key)
        raise web.HTTPServiceUnavailable(headers={"Cache-Control": "no-store", "Retry-After": "3"})
    except TelegramBadRequest:
        await request.app["redis"].set(cache_key, "-", ex=3600)
        raise web.HTTPNotFound(headers={"Cache-Control": "private, max-age=3600"})
    except Exception:
        LOG.warning("could not load Telegram avatar", extra={"user_id": user["id"]}, exc_info=True)
        await request.app["redis"].delete(cache_key)
        raise web.HTTPNotFound(headers={"Cache-Control": "private, max-age=60"})

    body = content.getvalue()
    # ponytail: per-process cache; move avatars to object storage if web-api is horizontally replicated.
    while request.app["avatar_cache"] and (len(request.app["avatar_cache"]) >= 256 or sum(len(item[1]) for item in request.app["avatar_cache"].values()) + len(body) > 8 * 1024 * 1024):
        request.app["avatar_cache"].pop(next(iter(request.app["avatar_cache"])))
    request.app["avatar_cache"][user_id] = (time.monotonic() + 21_600, body)
    return web.Response(body=body, content_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


async def customer_detail(request: web.Request):
    user_id = int(request.match_info["user_id"])
    user, customer_orders = await repo.purchaser_detail(user_id)
    if not user or not management_record_visible(request["actor"]["role"], customer_orders):
        raise web.HTTPNotFound()
    history = await repo.profile_history_for_user(user_id, 20)
    messages = await repo.support_messages_for_user(user_id, 20) if staff.can(request['actor'], 'chats.read') else []
    safe_history = []
    for item in history:
        item = dict(item)
        snapshot = repo._json_object(item.get("snapshot"))
        snapshot.pop("body_photo_file_ids", None)
        snapshot.pop("body_photo_file_id", None)
        item["snapshot"] = snapshot
        safe_history.append(item)
    return response({
        "user": _web_user(user),
        "orders": [_web_order(order) for order in customer_orders],
        "history": safe_history,
        "messages": [_web_message(message) for message in messages],
    })


async def customer_body_photo(request: web.Request):
    user_id = int(request.match_info["user_id"])
    index = int(request.match_info["index"])
    user, customer_orders = await repo.purchaser_detail(user_id)
    if not user or not management_record_visible(request["actor"]["role"], customer_orders):
        raise web.HTTPNotFound()
    photos = normalize_photos(user.get("body_photo_file_ids"))
    if not photos and user.get("body_photo_file_id"):
        photos = normalize_photos([user["body_photo_file_id"]])
    if index >= len(photos):
        raise web.HTTPNotFound()
    return await _telegram_media(request, photos[index]["file_id"], "image/jpeg")


async def order_body_photo(request: web.Request):
    order = await repo.get_order(int(request.match_info["order_id"]))
    index = int(request.match_info["index"])
    if not order or not management_record_visible(request["actor"]["role"], order):
        raise web.HTTPNotFound()
    snapshot = repo._json_object(order.get("form_snapshot"))
    photos = normalize_photos(snapshot.get("body_photo_file_ids"))
    if not photos and snapshot.get("body_photo_file_id"):
        photos = normalize_photos([snapshot["body_photo_file_id"]])
    if index >= len(photos):
        raise web.HTTPNotFound()
    return await _telegram_media(request, photos[index]["file_id"], "image/jpeg")


async def order_receipt(request: web.Request):
    staff.require(request['actor'], 'payments.review')
    order = await repo.get_order(int(request.match_info["order_id"]))
    if not order or not order.get("receipt_file_id"):
        raise web.HTTPNotFound()
    fallback = "image/jpeg" if order.get("receipt_type") == "photo" else "application/octet-stream"
    return await _telegram_media(request, order["receipt_file_id"], fallback)


async def support_message_media(request: web.Request):
    staff.require(request['actor'], 'chats.read')
    message = await repo.support_message_media(int(request.match_info["message_id"]))
    if not message or not message.get("file_id"):
        raise web.HTTPNotFound()
    fallback = {
        "photo": "image/jpeg", "video": "video/mp4", "voice": "audio/ogg",
        "audio": "audio/mpeg", "animation": "video/mp4",
    }.get(message.get("content_type"), "application/octet-stream")
    return await _telegram_media(request, message["file_id"], message.get("mime_type") or fallback, message.get("file_name"))


async def sales(request: web.Request):
    period, page = _sales_period(request.query.get("period")), _safe_page(request)
    snapshot, (items, count) = await asyncio.gather(_sales_snapshot(period), _sales_items(period, page))
    revenue = int(snapshot["revenue"])
    commission = round(revenue * settings.development_team_percent / 100)
    data = {**snapshot, "items": items, "count": count, "page": page, "pageSize": 20,
            "commission": commission, "commissionPercent": settings.development_team_percent, "net": revenue - commission}
    return response(data)


async def build_app():
    await db.connect()
    await staff.bootstrap()
    redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    await redis.ping()
    app = web.Application(middlewares=[security_headers, errors, auth], client_max_size=(settings.max_plan_file_mb + 1) * 1024 * 1024)
    app["redis"] = redis
    app['password_slots'] = asyncio.Semaphore(2)
    app["bot"] = Bot(settings.bot_token)
    app["upload_slots"] = asyncio.Semaphore(4)
    app["avatar_slots"] = asyncio.Semaphore(3)
    app["avatar_cache"] = {}
    app["media_slots"] = asyncio.Semaphore(3)
    app["media_cache"] = {}
    app["read_cache"] = {}
    app["read_cache_locks"] = WeakValueDictionary()
    app["realtime_subscribers"] = set()
    app["realtime_task"] = asyncio.create_task(_listen_for_updates(app), name="web-realtime-listener")
    app.add_routes(
        [
            web.get('/api/staff/profile', staff_profile), web.post('/api/staff/profile', staff_profile),
            web.get('/api/staff/team', staff_team), web.post('/api/staff/team', staff_team), web.get('/api/staff/audit', staff_audit),
            web.get('/api/collaboration/{kind:thread|order}/{target_id:\\d+}', collaboration), web.post('/api/collaboration/{kind:thread|order}/{target_id:\\d+}', collaboration),
            web.get("/", index), web.get("/health", health), web.get("/manifest.webmanifest", manifest), web.get("/service-worker.js", service_worker), web.get("/assets/{name}", asset),
            web.get("/api/config", config), web.get("/auth/telegram", telegram_widget_login), web.post("/api/auth/telegram", telegram_webapp_login),
            web.post("/api/auth/bot/start", bot_login), web.post("/api/auth/bot/poll", bot_login),
            web.post("/api/auth/dev", dev_login), web.post("/api/logout", logout), web.get("/api/session", session),
            web.get("/api/dashboard", dashboard), web.post("/api/sales-gate", sales_gate), web.get("/api/orders", orders), web.get("/api/orders/{order_id:\\d+}", order_detail),
            web.post("/api/orders/{order_id:\\d+}/action", order_action), web.post("/api/orders/{order_id:\\d+}/plan", upload_plan),
            web.get("/api/threads", threads), web.get("/api/threads/{user_id:\\d+}", thread_detail), web.post("/api/threads/{user_id:\\d+}/reply", reply_message),
            web.get("/api/customers", customers), web.get("/media/customers/{user_id:\\d+}/avatar", customer_avatar), web.get("/media/customers/{user_id:\\d+}/photos/{index:\\d+}", customer_body_photo), web.get("/api/customers/{user_id:\\d+}", customer_detail),
            web.get("/media/orders/{order_id:\\d+}/photos/{index:\\d+}", order_body_photo), web.get("/media/orders/{order_id:\\d+}/receipt", order_receipt), web.get("/media/messages/{message_id:\\d+}", support_message_media), web.get("/api/sales", sales), web.get("/api/events", realtime_events),
        ]
    )

    async def cleanup(_):
        app["realtime_task"].cancel()
        try:
            await app["realtime_task"]
        except asyncio.CancelledError:
            pass
        await app["bot"].session.close()
        await app["redis"].aclose()
        await db.close()

    app.on_cleanup.append(cleanup)
    return app


def main():
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    web.run_app(build_app(), host="0.0.0.0", port=8090, access_log=None)


if __name__ == "__main__":
    main()
