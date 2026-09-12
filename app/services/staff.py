"""Staff identity and authorization. Customer identities remain in users."""
import asyncio
import hashlib
import hmac
import json
import re
import secrets

from aiohttp import web

from app.config import get_settings
from app.db.core import db

PERMISSIONS = {
    'customers.read': ('مشاهده شاگردان و پرونده‌ها', 'View clients and records'),
    'orders.read': ('مشاهده کارها و سفارش‌ها', 'View tasks and orders'),
    'orders.review': ('بررسی اطلاعات و شروع طراحی', 'Review briefs and start design'),
    'orders.deliver': ('ارسال برنامه نهایی', 'Deliver programs'),
    'payments.review': ('بررسی رسید کارت‌به‌کارت', 'Review bank transfers'),
    'chats.read': ('خواندن گفت‌وگوها', 'Read conversations'),
    'chats.reply': ('پاسخ به شاگردان', 'Reply to clients'),
    'sales.read': ('مشاهده آمار مالی', 'View financial reports'),
    'sales.manage': ('باز و بسته کردن فروش', 'Open or pause sales'),
}
TEMPLATES = {
    'support': ['customers.read', 'chats.read', 'chats.reply'],
    'designer': ['customers.read', 'orders.read', 'orders.review', 'orders.deliver'],
    'finance': ['customers.read', 'orders.read', 'sales.read', 'payments.review'],
    'observer': ['customers.read', 'orders.read'],
}
# Fail closed for every authenticated handler, including private media.
ROUTE_PERMISSIONS = {
    'session': None, 'logout': None, 'realtime_events': None, 'dashboard': None,
    'staff_profile': None, 'staff_password': None, 'staff_team': 'team', 'staff_audit': 'team',
    'collaboration': 'collaboration',
    'sales_gate': 'sales.manage', 'sales': 'sales.read',
    'orders': 'orders.read', 'order_detail': 'records.read', 'order_action': 'orders.read',
    'upload_plan': 'orders.deliver', 'order_body_photo': 'records.read',
    'order_receipt': 'payments.review',
    'customers': 'customers.read', 'customer_detail': 'customers.read',
    'customer_body_photo': 'customers.read', 'customer_avatar': 'identity.read',
    'threads': 'chats.read', 'thread_detail': 'chats.read',
    'reply_message': 'chats.reply', 'support_message_media': 'chats.read',
}


def can(actor, permission):
    if permission is None:
        return True
    if actor.get('role') in {'leader', 'platform'}:
        return True
    if permission == 'team':
        return False
    if permission in {'identity.read', 'collaboration'}:
        return any(can(actor, item) for item in ('customers.read', 'orders.read', 'chats.read'))
    if permission == 'records.read':
        return can(actor, 'customers.read') or can(actor, 'orders.read')
    return permission in actor.get('permissions', [])


def require(actor, permission):
    if not can(actor, permission):
        raise web.HTTPForbidden(text='Permission denied')


def validate_permissions(values):
    if not isinstance(values, list) or len(values) > len(PERMISSIONS) or any(not isinstance(v, str) or v not in PERMISSIONS for v in values):
        raise ValueError('invalid_permissions')
    result = set(values)
    for action, read in (('orders.review', 'orders.read'), ('orders.deliver', 'orders.read'), ('payments.review', 'orders.read'), ('chats.reply', 'chats.read')):
        if action in result:
            result.add(read)
    return sorted(result)


def public(account):
    return {key: account[key] for key in ('id', 'telegram_id', 'username', 'display_name', 'role', 'permissions', 'status', 'auth_mode', 'session_version')}


async def by_id(staff_id):
    async with db.acquire() as c:
        row = await c.fetchrow('SELECT * FROM staff_accounts WHERE id=$1', staff_id)
    return dict(row) if row else None


async def by_telegram(telegram_id):
    """Optional contact lookup, never proof of web identity."""
    async with db.acquire() as c:
        row = await c.fetchrow('SELECT * FROM staff_accounts WHERE telegram_id=$1', telegram_id)
    return dict(row) if row else None


async def bootstrap():
    """Seed unconfigured identities once. A manager must set their password."""
    settings = get_settings()
    async with db.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock(917001)")
        accounts = [(value, 'platform', []) for value in sorted(settings.platform_team)]
        if settings.sensi_id not in settings.platform_team:
            accounts.append((settings.sensi_id, 'leader', []))
        accounts.extend((value, 'staff', ['customers.read', 'orders.read', 'sales.read']) for value in sorted(settings.admin_team - settings.platform_team - {settings.sensi_id}))
        for telegram_id, role, permissions in accounts:
            await c.execute('''INSERT INTO staff_accounts(telegram_id,username,display_name,role,permissions,status,auth_mode)
                VALUES($1,$2,COALESCE((SELECT COALESCE(name,first_name) FROM users WHERE telegram_id=$1),$2),$3,$4,'invited','password')
                ON CONFLICT DO NOTHING''', telegram_id, f'tg_{telegram_id}', role, permissions)


def validate_password(password):
    if (not isinstance(password, str) or not 8 <= len(password) <= 128
            or not re.search(r'[A-Z]', password) or not re.search(r'[0-9]', password)
            or not re.search(r'[^\w\s]', password)):
        raise ValueError('password_policy')


def _password_digest(password, salt):
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024).hex()
    return f'scrypt-32768-8-3${salt}${digest}'


def hash_password(password, salt=None):
    validate_password(password)
    return _password_digest(password, salt or secrets.token_hex(16))


def verify_password(password, encoded):
    # Verification accepts existing passwords even if the creation policy changes.
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        return False
    try:
        scheme, salt, _ = encoded.split('$')
        return scheme == 'scrypt-32768-8-3' and hmac.compare_digest(_password_digest(password, salt), encoded)
    except (ValueError, AttributeError):
        return False


async def password_work(slots, function, *args):
    # Bounded CPU/memory per process: never queue unbounded scrypt jobs.
    if slots.locked():
        raise web.HTTPTooManyRequests(headers={'Retry-After': '5'})
    async with slots:
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # A disconnected client must not free a slot while its thread still hashes.
            await task
            raise


async def authenticate(body, slots):
    username = body.get('username', '')
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
        raise web.HTTPUnauthorized(text='Invalid credentials')
    async with db.acquire() as c:
        row = await c.fetchrow('SELECT * FROM staff_accounts WHERE username=$1', username.lower())
    dummy = 'scrypt-32768-8-3$' + '0' * 32 + '$' + '0' * 128
    valid = await password_work(slots, verify_password, body.get('password'), row['password_hash'] if row and row['password_hash'] else dummy)
    if not valid or not row or row['status'] != 'active' or row['auth_mode'] != 'password':
        raise web.HTTPUnauthorized(text='Invalid credentials')
    # Recheck after hashing: password resets/disables must win concurrent logins.
    async with db.acquire() as c, c.transaction():
        current = await c.fetchrow('SELECT * FROM staff_accounts WHERE id=$1 FOR UPDATE', row['id'])
        if not current or current['status'] != 'active' or current['session_version'] != row['session_version']:
            raise web.HTTPUnauthorized(text='Invalid credentials')
        await audit(c, current, 'staff_login', 'staff', current['id'])
    return dict(current)


async def change_password(actor, body, slots):
    row = await by_id(actor['staff_id'])
    if not row or row['status'] != 'active' or row['session_version'] != actor['version']:
        raise web.HTTPUnauthorized()
    if not await password_work(slots, verify_password, body.get('current_password'), row['password_hash']):
        raise web.HTTPUnauthorized(text='Invalid current password')
    encoded = await password_work(slots, hash_password, body.get('password'))
    async with db.acquire() as c, c.transaction():
        changed = await c.fetchrow("""UPDATE staff_accounts SET password_hash=$2,session_version=session_version+1,updated_at=NOW()
            WHERE id=$1 AND session_version=$3 AND status='active' RETURNING id""", row['id'], encoded, row['session_version'])
        if not changed:
            raise web.HTTPConflict(text='Account changed; sign in again')
        await audit(c, actor, 'staff_password_changed', 'staff', row['id'])


async def audit(c, actor, action, target_type, target_id, metadata=None):
    await c.execute('''INSERT INTO audit_logs(actor_telegram_id,actor_staff_id,actor_name,action,target_type,target_id,metadata)
        VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)''', actor.get('telegram_id'), actor.get('staff_id', actor.get('id')), actor['display_name'], action, target_type, target_id, json.dumps(metadata or {}, ensure_ascii=False))


def manageable(actor, target_role):
    return actor['role'] == 'platform' or actor['role'] == 'leader' and target_role == 'staff'


async def team_change(actor, body, slots):
    """Password hashing precedes transactions; hierarchy/version checked again at commit."""
    require(actor, 'team')
    action = body.get('action')
    if action not in {'create', 'permissions', 'disable', 'enable', 'reset_password', 'revoke'}:
        raise ValueError('invalid_action')
    if action == 'create':
        role = body.get('role', 'staff')
        if role not in {'platform', 'leader', 'staff'} or not manageable(actor, role):
            raise web.HTTPForbidden()
        name, username = body.get('display_name'), body.get('username')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
            raise ValueError('invalid_profile')
        permissions = validate_permissions(body.get('permissions', []))
    else:
        target = await by_id(int(body.get('id', 0)))
        if not target or not manageable(actor, target['role']) or target['id'] == actor['staff_id']:
            raise web.HTTPForbidden()
    encoded = await password_work(slots, hash_password, body.get('password')) if action in {'create', 'reset_password'} else None
    async with db.acquire() as c, c.transaction():
        # ponytail: rare team mutations use one lock; partition if management throughput grows.
        await c.execute('SELECT pg_advisory_xact_lock(917002)')
        manager = await c.fetchrow('SELECT * FROM staff_accounts WHERE id=$1 FOR UPDATE', actor['staff_id'])
        if not manager or manager['status'] != 'active' or manager['session_version'] != actor['version']:
            raise web.HTTPUnauthorized()
        if action == 'create':
            if not manageable(manager, role):
                raise web.HTTPForbidden()
            row = await c.fetchrow("""INSERT INTO staff_accounts(username,display_name,role,permissions,password_hash,status)
                VALUES($1,$2,$3,$4,$5,'active') RETURNING *""", username.lower(), name.strip(), role, permissions, encoded)
        else:
            row = await c.fetchrow('SELECT * FROM staff_accounts WHERE id=$1 FOR UPDATE', target['id'])
            if not row or not manageable(manager, row['role']) or row['id'] == actor['staff_id']:
                raise web.HTTPForbidden()
            if body.get('version') != row['session_version']:
                raise web.HTTPConflict(text='Account changed; refresh first')
            if row['role'] == 'platform' and action == 'disable':
                if await c.fetchval("SELECT COUNT(*) FROM staff_accounts WHERE role='platform' AND status='active'") <= 1:
                    raise web.HTTPConflict(text='Keep one active platform owner')
            permissions = validate_permissions(body.get('permissions', [])) if action == 'permissions' else row['permissions']
            status = row['status']
            if action == 'disable':
                status = 'disabled'
            elif action in {'enable', 'reset_password'}:
                status = 'active' if encoded or row['password_hash'] else 'invited'
                if action == 'reset_password' and row['status'] == 'disabled':
                    status = 'disabled'
            row = await c.fetchrow("""UPDATE staff_accounts SET permissions=$2,status=$3,session_version=session_version+1,updated_at=NOW(),
                password_hash=COALESCE($4,password_hash) WHERE id=$1 RETURNING *""", row['id'], permissions, status, encoded)
        await audit(c, actor, 'staff_' + action, 'staff', row['id'], {'role': row['role'], 'permissions': list(row['permissions']), 'status': row['status']})
        return {'account': public(row)}
