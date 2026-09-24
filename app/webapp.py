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
from urllib.parse import quote, urlsplit
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
from app.services import staff
from app.services.content import asset_path, store_upload
from app.utils.media import BoundedBuffer, _inspect_upload, _sniff_download, message_file


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


async def _new_session(request: web.Request, account: dict) -> str:
    token = secrets.token_urlsafe(32)
    actor = {"staff_id": account['id'], "version": account['session_version'], "csrf": secrets.token_urlsafe(24), "auth_method": "password"}
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
    public = request.path in {"/", "/health", "/manifest.webmanifest", "/service-worker.js", "/api/config", "/api/auth/password"} or request.path.startswith(("/assets/", "/content/"))
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
    if actor.get("auth_method") != "password":
        await request.app["redis"].delete(f"web:session:{token}")
        return None
    account = await staff.by_id(actor.get("staff_id"))
    if not account or account['status'] != 'active' or account['id'] != actor.get('staff_id') or account['session_version'] != actor.get('version'):
        await request.app["redis"].delete(f"web:session:{token}")
        return None
    return {**actor, **staff.public(account)}


@web.middleware
async def errors(request: web.Request, handler):
    request_id=secrets.token_hex(8)
    request['request_id']=request_id
    try:
        result=await handler(request)
        result.headers['X-Request-ID']=request_id
        if result.status>=500:
            LOG.error('Request unavailable',extra={'event':f"{getattr(request.match_info.handler,'__name__','request')}.{result.status}",'request_id':request_id})
        return result
    except web.HTTPException as exc:
        exc.headers['X-Request-ID']=request_id
        if exc.status>=500:
            LOG.error('Request failed',extra={'event':f"{getattr(request.match_info.handler,'__name__','request')}.{exc.status}",'request_id':request_id})
        raise
    except (json.JSONDecodeError, UnicodeDecodeError):
        return response({"error": "invalid_json"}, 400)
    except Exception:
        LOG.exception("web request failed", extra={"event":getattr(request.match_info.handler,'__name__','request'),"request_id":request_id})
        return response({"error": "server_error","request_id":request_id}, 500)


async def _rate_limited(request: web.Request, scope: str, limit: int, window: int = 60) -> bool:
    key = f"web:limit:{scope}:{request['actor']['staff_id']}:{int(time.time()) // window}"
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
    result['product_snapshot']=repo._json_object(result.get('product_snapshot'))
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
                SELECT o.id AS order_id,o.amount,o.paid_at,COALESCE(o.product_snapshot->>'title',p.title) AS product_title,
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
    return response({"loginMethod": "password"})


async def password_login(request: web.Request):
    # JSON plus a non-simple header prevents cross-site login/session swapping.
    if request.headers.get("X-Login-Request") != "1" or request.headers.get("Sec-Fetch-Site") == "cross-site":
        return response({"error": "invalid_origin"}, 403)
    origin = request.headers.get("Origin")
    proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",", 1)[0].strip()
    host = request.headers.get("X-Forwarded-Host", request.host).split(",", 1)[0].strip()
    if origin and origin.rstrip("/") != f"{proto}://{host}":
        return response({"error": "invalid_origin"}, 403)
    client = request.remote or "unknown"
    if settings.web_trust_ingress:
        try:
            client = str(ip_address(request.headers.get("X-Coach-Client-IP", "")))
        except ValueError:
            return response({"error": "invalid_ingress"}, 403)
    redis = request.app["redis"]
    async def limited(key, limit):
        key = f"web:password:{key}:{int(time.time()) // 300}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 310)
        return count > limit
    if await limited(f"ip:{client}", 30):
        raise web.HTTPTooManyRequests(headers={"Retry-After": "300"})
    if request.content_length and request.content_length > 4096:
        return response({"error": "payload_too_large"}, 413)
    payload = BoundedBuffer(4096)
    try:
        async for chunk in request.content.iter_chunked(1024):
            payload.write(chunk)
    except ValueError:
        return response({"error": "payload_too_large"}, 413)
    body = json.loads(payload.getvalue())
    if not isinstance(body, dict):
        return response({"error": "invalid_payload"}, 400)
    username = body.get("username")
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
        raise web.HTTPUnauthorized(text="Invalid credentials")
    identity = hashlib.sha256(username.lower().encode()).hexdigest()
    if await limited(f"account:{identity}", 10):
        raise web.HTTPTooManyRequests(headers={"Retry-After": "300"})
    account = await staff.authenticate(body, request.app["password_slots"])
    token = await _new_session(request, account)
    result = response({"ok": True})
    _set_session_cookie(result, token)
    if proto == "https":
        result.cookies[SESSION_COOKIE]["secure"] = True
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        await redis.delete(f"web:session:{previous}")
    return result


async def staff_password(request):
    if await _rate_limited(request, 'password-change', 5, 300):
        raise web.HTTPTooManyRequests(headers={'Retry-After': '300'})
    body = await request.json()
    if not isinstance(body, dict):
        return response({'error': 'invalid_payload'}, 400)
    try:
        await staff.change_password(request['actor'], body, request.app['password_slots'])
    except ValueError:
        return response({'error': 'password_policy'}, 400)
    return await logout(request)


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
            return response(await staff.team_change(actor, body, request.app['password_slots']))
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
        rows = await c.fetch('''SELECT a.id,a.actor_staff_id,a.actor_name,s.role AS actor_role,a.action,a.target_type,a.target_id,
                   target.display_name AS target_name,a.created_at,a.metadata
            FROM audit_logs a LEFT JOIN staff_accounts s ON s.id=a.actor_staff_id
            LEFT JOIN staff_accounts target ON a.target_type='staff' AND target.id=a.target_id
            WHERE ($1::bigint IS NULL OR a.id<$1) AND ($2 OR s.role IS DISTINCT FROM 'platform')
            ORDER BY a.id DESC LIMIT 51''', int(before) if before else None, request['actor']['role'] == 'platform')
    return response({'items': [dict(row) for row in rows[:50]], 'next': rows[49]['id'] if len(rows) > 50 else None})


async def collaboration(request):
    actor = request['actor']
    kind, target_id = request.match_info['kind'], int(request.match_info['target_id'])
    permission = {'thread':'chats.read','customer':'customers.read','order':'orders.read'}[kind]
    staff.require(actor, permission)
    table = 'users' if kind in {'thread','customer'} else 'orders'
    async with db.acquire() as c, c.transaction():
        if not await c.fetchval(f'SELECT id FROM {table} WHERE id=$1', target_id):
            raise web.HTTPNotFound()
        if request.method == 'POST':
            body = await request.json()
            if not isinstance(body, dict):
                return response({'error': 'invalid_payload'}, 400)
            if body.get('action') == 'note':
                staff.require(actor, {'thread':'chats.reply','customer':'customers.read','order':'orders.review'}[kind])
                text = body.get('text')
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
                    return response({'error': 'invalid_note'}, 400)
                await c.execute('INSERT INTO staff_notes(target_type,target_id,staff_id,author_name,body) VALUES($1,$2,$3,$4,$5)', kind, target_id, actor['staff_id'], actor['display_name'], text.strip())
                await c.execute('UPDATE staff_assignments SET seen_at=CASE WHEN staff_id=$3 THEN NOW() ELSE NULL END,updated_at=NOW() WHERE target_type=$1 AND target_id=$2',kind,target_id,actor['staff_id'])
                await staff.audit(c, actor, 'internal_note', kind, target_id)
            elif body.get('action') == 'assign':
                staff.require(actor, {'thread':'chats.reply','customer':'customers.read','order':'orders.review'}[kind])
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
                await c.execute('UPDATE staff_assignments SET staff_id=$3,seen_at=NULL,version=version+1,updated_at=NOW() WHERE target_type=$1 AND target_id=$2', kind, target_id, assignee)
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
    if table in {"users", "orders", "support_messages", "sales_gate", "staff_assignments"}:
        for key in tuple(app["read_cache"]):
            if key.startswith("dashboard:"):
                app["read_cache"].pop(key, None)
            elif table in {"users", "orders"} and key.startswith("orders:"):
                app["read_cache"].pop(key, None)
            elif table in {"users", "support_messages"} and key.startswith("threads:"):
                app["read_cache"].pop(key, None)
            elif table == "staff_assignments" and key.startswith("threads:"):
                app["read_cache"].pop(key, None)
    if table == "products":
        app["read_cache"].pop("products", None)
    for queue in tuple(app["realtime_subscribers"]):
        if queue.full():
            queue.get_nowait()
            queue.put_nowait('{"resync":true}')
        else:
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
                # One current-session lookup per short, bounded burst, never per row.
                await asyncio.sleep(0.1)
                batch = [payload]
                while not queue.empty() and len(batch) < 32:
                    batch.append(queue.get_nowait())
                current_actor = await _session_actor(request)
                if not current_actor:
                    await result.write(b'event: session-expired\ndata: {}\n\n')
                    break
                events = []
                for payload in batch:
                    update = json.loads(payload)
                    table = update.get('table')
                    needed = {'support_messages':'chats.read', 'users':'identity.read', 'orders':'records.read', 'products':'records.read', 'sales_gate':'sales.manage', 'staff_accounts':'team', 'staff_assignments':'collaboration', 'staff_notes':'collaboration'}.get(table, 'team')
                    if update.get('resync') or (table == 'orders' and staff.can(current_actor, 'sales.read')):
                        needed = None
                    if staff.can(current_actor, needed):
                        events.append(f"event: update\ndata: {payload}\n\n")
                if events:
                    await result.write(''.join(events).encode())
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
    kinds = [kind for kind, permission in {'thread':'chats.read','customer':'customers.read','order':'orders.read'}.items() if staff.can(request['actor'], permission)]
    data['counts']['assigned'] = await repo.staff_assignment_count(request['actor']['staff_id'], kinds)
    if not staff.can(request['actor'], 'chats.read'):
        data['counts']['unread'] = 0
    if not staff.can(request['actor'], 'customers.read'):
        data['buyers'] = data['users'] = data['counts']['active'] = 0
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
    await repo.add_audit(request["actor"], "web_sales_gate", "sales_gate", 1, {"open": current})
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
            manual_delivery=await c.fetchrow('SELECT status,error FROM manual_deliveries WHERE order_id=$1',row['id'])
        result["info_request"] = last_request
        result['manual_delivery']=dict(manual_delivery) if manual_delivery else None
    return response(result)


async def order_action(request: web.Request):
    staff.require(request['actor'], 'orders.read')
    order_id = int(request.match_info["order_id"])
    body = await request.json()
    if not isinstance(body, dict):
        return response({"error": "invalid_payload"}, 400)
    action = body.get("action")
    if action == 'retry_manual_delivery':
        staff.require(request['actor'],'orders.deliver')
        if await _rate_limited(request,'retry_delivery',3): return response({'error':'rate_limited'},429)
        async with db.acquire() as c,c.transaction():
            changed=await c.fetchval("UPDATE manual_deliveries SET status='queued',next_at=NOW(),error=NULL,attempts=0 WHERE order_id=$1 AND status='paused' RETURNING order_id",order_id)
            if not changed: return response({'error':'invalid_transition'},409)
            await staff.audit(c,request['actor'],'manual_delivery_retried','order',order_id)
        return response({'ok':True})
    if action == 'retry_delivery':
        staff.require(request['actor'],'orders.deliver')
        if await _rate_limited(request,'retry_delivery',3):
            return response({'error':'rate_limited'},429)
        async with db.acquire() as c,c.transaction():
            changed=await c.fetchval('''UPDATE orders SET fulfillment_next_at=NOW(),
                fulfillment_error=NULL,fulfillment_attempts=0,updated_at=NOW()
                WHERE id=$1 AND paid_at IS NOT NULL AND NOT fulfillment_done
                AND fulfillment_error='delivery_paused' RETURNING id''',order_id)
            if not changed: return response({'error':'invalid_transition'},409)
            await staff.audit(c,request['actor'],'delivery_retry_requested','order',order_id)
        request.app['read_cache'].clear()
        return response({'ok':True})
    if action not in ("approve_receipt", "reject_receipt", "in_progress", "needs_info"):
        return response({"error": "invalid_action"}, 400)
    staff.require(request['actor'], 'payments.review' if action in {'approve_receipt', 'reject_receipt'} else 'orders.review')
    info = body.get("message", "")
    if action == "needs_info" and (not isinstance(info, str) or not info.strip() or len(info.strip()) > 1000):
        return response({"error": "message_required"}, 400)
    actor = request["actor"]
    actor_telegram_id = actor["telegram_id"]
    current = await repo.get_order(order_id)
    if not current:
        raise web.HTTPNotFound()
    if action in {'in_progress','needs_info'} and repo._json_object(current.get('product_snapshot')).get('delivery_mode','manual')!='manual':
        return response({'error':'automatic_delivery'},409)
    changed = None
    if action == "approve_receipt":
        if current.get("payment_method") != "card_to_card":
            return response({"error": "gateway_payment_is_automatic"}, 409)
        changed = await repo.approve_card_payment(order_id, actor_telegram_id)
        message = "✅ پرداخت شما تأیید شد. اطلاعات دوره شما در صف بررسی مربی قرار گرفت."
    elif action == "reject_receipt":
        if current.get("payment_method") != "card_to_card":
            return response({"error": "gateway_payment_is_automatic"}, 409)
        changed = await repo.reject_card_payment(order_id, actor_telegram_id)
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
    if action == 'approve_receipt':
        return response({'ok':True,'notification_queued':True})
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
        async with asyncio.timeout(900), request.app['upload_slots'], db.acquire() as lock, lock.transaction():
            if not await lock.fetchval('SELECT pg_try_advisory_xact_lock(hashtextextended($1,0))',f'plan-delivery:{order_id}'):
                return response({'error':'delivery_in_progress'},409)
            if await _rate_limited(request,'plan_upload',8):
                return response({'error':'rate_limited'},429)
            return await _upload_plan(request, order)
    except TimeoutError:
        return response({'error': 'upload_timeout'}, 503)


async def _upload_plan(request, order):
    order_id = order['id']
    reader = await request.multipart()
    text_value=''; links=[]; files=[]; committed=False
    try:
        while part:=await reader.next():
            if part.name=='file' and part.filename:
                if len(files)>=10: return response({'error':'too_many_files'},400)
                key,filename,size=await store_upload(part,max_bytes=50*1024*1024)
                files.append((key,filename,size))
            elif part.name in {'text','links'}:
                chunks=[];size=0
                while chunk:=await part.read_chunk(8192):
                    size+=len(chunk)
                    if size>32000: return response({'error':'invalid_delivery'},400)
                    chunks.append(chunk)
                value=b''.join(chunks)
                if part.name=='text': text_value=value.decode('utf-8').strip()
                else: links=json.loads(value)
        if len(text_value)>4000 or not isinstance(links,list) or len(links)>20 or any(not isinstance(url,str) or not 1<=len(url)<=1500 for url in links):
            return response({'error':'invalid_delivery'},400)
        links=[url.strip() for url in links]
        if any((parts:=urlsplit(url)).scheme!='https' or not parts.hostname or parts.username or parts.password or re.search(r'\s',url) for url in links):
            return response({'error':'invalid_links'},400)
        if not (text_value or links or files): return response({'error':'content_required'},400)
        async with db.acquire() as c,c.transaction():
            current=await c.fetchrow('SELECT id,status FROM orders WHERE id=$1 FOR UPDATE',order_id)
            if not current or current['status'] not in {'in_progress','ready'} or await c.fetchval('SELECT 1 FROM manual_deliveries WHERE order_id=$1',order_id):
                return response({'error':'invalid_transition'},409)
            await c.execute('INSERT INTO manual_deliveries(order_id) VALUES($1)',order_id)
            position=0
            for kind,value in ([('text',text_value)] if text_value else [])+[('link',url) for url in links]:
                await c.execute('INSERT INTO manual_delivery_items(order_id,position,kind,body) VALUES($1,$2,$3,$4)',order_id,position,kind,value)
                position+=1
            for key,filename,size in files:
                asset_id=await c.fetchval('INSERT INTO product_assets(filename,storage_key,byte_size) VALUES($1,$2,$3) RETURNING id',filename,key,size)
                await c.execute("INSERT INTO manual_delivery_items(order_id,position,kind,asset_id) VALUES($1,$2,'file',$3)",order_id,position,asset_id)
                position+=1
            await staff.audit(c,request['actor'],'web_deliver_plan','order',order_id,{'files':len(files),'links':len(links),'text':bool(text_value)})
        committed=True
        return response({'ok':True,'queued':True})
    except (UnicodeDecodeError,json.JSONDecodeError):
        return response({'error':'invalid_delivery'},400)
    except web.HTTPRequestEntityTooLarge:
        return response({'error':'file_too_large'},413)
    except web.HTTPBadRequest:
        return response({'error':'invalid_file_type'},400)
    finally:
        if not committed:
            for key,_,_ in files:
                asset_path(key).unlink(missing_ok=True)


async def threads(request: web.Request):
    staff.require(request['actor'], 'chats.read')
    page = _safe_page(request)
    query, unread = request.query.get("q", ""), request.query.get("unread") == "1"
    async def load():
        kinds = [kind for kind, permission in {'thread':'chats.read','customer':'customers.read','order':'orders.read'}.items() if staff.can(request['actor'], permission)]
        (rows, total), counts = await asyncio.gather(repo.support_threads(page, 20, query, unread), repo.support_thread_counts(request['actor']['staff_id'], kinds))
        return {"items": rows, "total": total, "page": page, "pageSize": 20, "counts": counts}
    return response(await _cached(request, f"threads:{request['actor']['staff_id']}:{page}:{int(unread)}:{query.strip().lower()[:80]}", 2, load))


async def followups(request: web.Request):
    actor=request['actor']; page=_safe_page(request)
    state=request.query.get('state','all'); sort=request.query.get('sort','newest')
    if state not in {'all','unseen','seen'} or sort not in {'newest','oldest'}:
        return response({'error':'invalid_filter'},400)
    kinds=[kind for kind,permission in {'thread':'chats.read','customer':'customers.read','order':'orders.read'}.items() if staff.can(actor,permission)]
    rows,total,followup_counts=await repo.staff_followups(actor['staff_id'],kinds,page,20,request.query.get('q',''),state,sort)
    counts=await repo.support_thread_counts(actor['staff_id'],kinds)
    return response({'items':rows,'total':total,'page':page,'pageSize':20,'counts':counts,'followupCounts':followup_counts})


async def followup_seen(request: web.Request):
    actor=request['actor']; kind=request.match_info['kind']; target_id=int(request.match_info['target_id'])
    staff.require(actor,{'thread':'chats.read','customer':'customers.read','order':'orders.read'}[kind])
    async with db.acquire() as c:
        changed=await c.fetchval('''UPDATE staff_assignments SET seen_at=NOW() WHERE target_type=$1 AND target_id=$2 AND staff_id=$3
            RETURNING target_id''',kind,target_id,actor['staff_id'])
    if changed is None:
        raise web.HTTPNotFound()
    return response({'ok':True})


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
        elif media_kind == "animation":
            sent = await bot.send_animation(user["telegram_id"], upload, caption=text or None)
        elif media_kind == "video":
            sent = await bot.send_video(user["telegram_id"], upload, caption=text or None)
        elif media_kind == "voice":
            sent = await bot.send_voice(user["telegram_id"], upload, caption=text or None)
        elif media_kind == "audio":
            sent = await bot.send_audio(user["telegram_id"], upload, caption=text or None)
        else:
            sent = await bot.send_document(user["telegram_id"], upload, caption=text or None,disable_content_type_detection=True)
        content_type, file_id = message_file(sent)
    else:
        sent = await bot.send_message(user["telegram_id"], text)
    await repo.add_support_message(
        user["telegram_id"], sent.message_id, direction="sensi", sender_telegram_id=request["actor"], content_type=content_type,
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
            request.query.get("sort", "joined_desc"),
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
    if not user:
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
    from app.catalog_api import routes as catalog_routes
    from app.broadcast_api import routes as broadcast_routes
    from app.analytics_api import analytics, client_error
    from app.services.telemetry import web_metrics, run_telemetry_loop
    await db.connect()
    await staff.bootstrap()
    redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    await redis.ping()
    app = web.Application(middlewares=[security_headers, web_metrics, errors, auth], client_max_size=(settings.max_plan_file_mb + 1) * 1024 * 1024)
    app["redis"] = redis
    app['password_slots'] = asyncio.Semaphore(2)
    app["bot"] = Bot(settings.bot_token)
    app["upload_slots"] = asyncio.Semaphore(4)
    app['catalog_upload_slots'] = asyncio.Semaphore(2)
    from app.services.content import purchased_content, content_style
    app.router.add_get('/content/style.css',content_style)
    app.router.add_get('/content/{token:[A-Za-z0-9_-]{43}}',purchased_content)
    app.router.add_post('/content/{token:[A-Za-z0-9_-]{43}}',purchased_content)
    app["channel_slots"] = asyncio.Semaphore(2)
    app.add_routes(catalog_routes())
    app.add_routes(broadcast_routes())
    app.router.add_get('/api/analytics', analytics)
    app.router.add_post('/api/analytics/client-error',client_error)
    app['telemetry_task'] = asyncio.create_task(run_telemetry_loop('web'),name='web-telemetry')
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
            web.get('/api/collaboration/{kind:thread|customer|order}/{target_id:\\d+}', collaboration), web.post('/api/collaboration/{kind:thread|customer|order}/{target_id:\\d+}', collaboration),
            web.get("/", index), web.get("/health", health), web.get("/manifest.webmanifest", manifest), web.get("/service-worker.js", service_worker), web.get("/assets/{name}", asset),
            web.get("/api/config", config), web.post("/api/auth/password", password_login),
            web.post("/api/staff/password", staff_password), web.post("/api/logout", logout), web.get("/api/session", session),
            web.get("/api/dashboard", dashboard), web.post("/api/sales-gate", sales_gate), web.get("/api/orders", orders), web.get("/api/orders/{order_id:\\d+}", order_detail),
            web.post("/api/orders/{order_id:\\d+}/action", order_action), web.post("/api/orders/{order_id:\\d+}/plan", upload_plan),
            web.get("/api/threads", threads), web.get("/api/followups", followups), web.post('/api/followups/{kind:thread|customer|order}/{target_id:\\d+}/seen',followup_seen), web.get("/api/threads/{user_id:\\d+}", thread_detail), web.post("/api/threads/{user_id:\\d+}/reply", reply_message),
            web.get("/api/customers", customers), web.get("/media/customers/{user_id:\\d+}/avatar", customer_avatar), web.get("/media/customers/{user_id:\\d+}/photos/{index:\\d+}", customer_body_photo), web.get("/api/customers/{user_id:\\d+}", customer_detail),
            web.get("/media/orders/{order_id:\\d+}/photos/{index:\\d+}", order_body_photo), web.get("/media/orders/{order_id:\\d+}/receipt", order_receipt), web.get("/media/messages/{message_id:\\d+}", support_message_media), web.get("/api/sales", sales), web.get("/api/events", realtime_events),
        ]
    )

    async def cleanup(_):
        app['telemetry_task'].cancel()
        try:
            await app['telemetry_task']
        except asyncio.CancelledError:
            pass
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
    from app.services.diagnostics import configure
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    configure('web-api')
    web.run_app(build_app(), host="0.0.0.0", port=8090, access_log=None)


if __name__ == "__main__":
    main()
