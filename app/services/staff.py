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
    'staff_profile': None, 'staff_team': 'team', 'staff_audit': 'team',
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


async def by_telegram(telegram_id):
    async with db.acquire() as c:
        row = await c.fetchrow('SELECT * FROM staff_accounts WHERE telegram_id=$1', telegram_id)
    return dict(row) if row else None


async def bootstrap():
    """Insert configured identities once; never re-enable/re-promote on restart."""
    settings = get_settings()
    async with db.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock(917001)")
        accounts = [(value, 'platform', []) for value in sorted(settings.platform_team)]
        if settings.sensi_id not in settings.platform_team:
            accounts.append((settings.sensi_id, 'leader', []))
        accounts.extend((value, 'staff', ['customers.read', 'orders.read', 'sales.read']) for value in sorted(settings.admin_team - settings.platform_team - {settings.sensi_id}))
        for telegram_id, role, permissions in accounts:
            await c.execute('''INSERT INTO staff_accounts(telegram_id,username,display_name,role,permissions,status,auth_mode)
                VALUES($1,$2,COALESCE((SELECT COALESCE(name,first_name) FROM users WHERE telegram_id=$1),$2),$3,$4,'active','telegram')
                ON CONFLICT DO NOTHING''', telegram_id, f'tg_{telegram_id}', role, permissions)


def hash_password(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('password_length')
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024).hex()
    return f'scrypt-32768-8-3${salt}${digest}'


def verify_password(password, encoded):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        return False
    try:
        scheme, salt, _ = encoded.split('$')
        return scheme == 'scrypt-32768-8-3' and hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, AttributeError):
        return False


async def login_context(body, slots):
    """Password never authorizes a session by itself: Telegram must also approve."""
    username = body.get('username', '')
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
        raise web.HTTPUnauthorized(text='Invalid credentials')
    async with db.acquire() as c:
        row = await c.fetchrow('SELECT * FROM staff_accounts WHERE username=$1', username.lower())
        token = body.get('invite', '')
        invite_hash = hashlib.sha256(token.encode()).hexdigest() if isinstance(token, str) and len(token) <= 100 else ''
        invite = await c.fetchrow('SELECT staff_id FROM staff_invites WHERE token_hash=$1 AND expires_at>NOW()', invite_hash) if token else None
    if slots.locked():
        raise web.HTTPTooManyRequests(headers={'Retry-After': '5'})
    async with slots:
        if token and row and invite and invite['staff_id'] == row['id'] and row['status'] != 'disabled':
            try:
                encoded = await asyncio.to_thread(hash_password, body.get('password'))
            except ValueError:
                raise web.HTTPBadRequest(text='Password must contain 12–128 characters')
            return {'target': row['telegram_id'], 'version': row['session_version'], 'password_hash': encoded, 'invite': invite_hash, 'method': 'password_telegram'}
        # A fixed dummy hash equalizes the expensive part for unknown usernames.
        dummy = 'scrypt-32768-8-3$' + '0' * 32 + '$' + '0' * 128
        valid = await asyncio.to_thread(verify_password, body.get('password'), row['password_hash'] if row and row['password_hash'] else dummy)
    if not valid or not row or row['status'] != 'active' or row['auth_mode'] != 'password_telegram':
        raise web.HTTPUnauthorized(text='Invalid credentials')
    return {'target': row['telegram_id'], 'version': row['session_version'], 'method': 'password_telegram'}


async def finish_login(context, telegram_id):
    async with db.acquire() as c, c.transaction():
        row = await c.fetchrow('SELECT * FROM staff_accounts WHERE telegram_id=$1 FOR UPDATE', telegram_id)
        if not row or row['status'] == 'disabled':
            return None
        if context.get('target') and (context['target'] != telegram_id or context.get('version') != row['session_version']):
            return None
        if context.get('invite'):
            used = await c.fetchrow('DELETE FROM staff_invites WHERE token_hash=$1 AND staff_id=$2 AND expires_at>NOW() RETURNING staff_id', context['invite'], row['id'])
            if not used:
                return None
            row = await c.fetchrow("UPDATE staff_accounts SET password_hash=$2,status='active',auth_mode='password_telegram',session_version=session_version+1,updated_at=NOW() WHERE id=$1 RETURNING *", row['id'], context['password_hash'])
        if row['status'] != 'active' or row['auth_mode'] != context.get('method', 'telegram'):
            return None
        await audit(c, row, 'staff_login', 'staff', row['id'])
        return dict(row)


async def audit(c, actor, action, target_type, target_id, metadata=None):
    await c.execute('''INSERT INTO audit_logs(actor_telegram_id,actor_staff_id,actor_name,action,target_type,target_id,metadata)
        VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)''', actor['telegram_id'], actor.get('staff_id', actor.get('id')), actor['display_name'], action, target_type, target_id, json.dumps(metadata or {}, ensure_ascii=False))


def manageable(actor, target_role):
    return actor['role'] == 'platform' or actor['role'] == 'leader' and target_role == 'staff'


async def team_change(actor, body):
    """Account changes and audit commit together; optimistic version avoids lost edits."""
    async with db.acquire() as c, c.transaction():
        # Team mutations are rare; serialize hierarchy changes across API replicas.
        await c.execute('SELECT pg_advisory_xact_lock(917002)')
        if body.get('action') == 'create':
            role = body.get('role', 'staff')
            if role not in {'platform', 'leader', 'staff'} or not manageable(actor, role):
                raise web.HTTPForbidden()
            name, username = body.get('display_name'), body.get('username')
            telegram_id = body.get('telegram_id')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username) or type(telegram_id) is not int or not 0 < telegram_id < 2**53:
                raise ValueError('invalid_profile')
            permissions = validate_permissions(body.get('permissions', []))
            row = await c.fetchrow('''INSERT INTO staff_accounts(telegram_id,username,display_name,role,permissions)
                VALUES($1,$2,$3,$4,$5) RETURNING *''', telegram_id, username.lower(), name.strip(), role, permissions)
        else:
            row = await c.fetchrow('SELECT * FROM staff_accounts WHERE id=$1 FOR UPDATE', int(body.get('id', 0)))
            if not row or not manageable(actor, row['role']) or row['id'] == actor['staff_id']:
                raise web.HTTPForbidden()
            if body.get('version') != row['session_version']:
                raise web.HTTPConflict(text='Account changed; refresh first')
            action = body.get('action')
            if action not in {'permissions', 'disable', 'enable', 'invite', 'revoke'}:
                raise ValueError('invalid_action')
            if row['role'] == 'platform' and action in {'disable', 'invite'}:
                if await c.fetchval("SELECT COUNT(*) FROM staff_accounts WHERE role='platform' AND status='active'") <= 1:
                    raise web.HTTPConflict(text='Keep one active platform owner')
            permissions = validate_permissions(body.get('permissions', [])) if action == 'permissions' else row['permissions']
            status = 'disabled' if action == 'disable' else 'invited' if action == 'invite' else ('active' if row['password_hash'] or row['auth_mode'] == 'telegram' else 'invited') if action == 'enable' else row['status']
            row = await c.fetchrow('''UPDATE staff_accounts SET permissions=$2,status=$3,session_version=session_version+1,updated_at=NOW(),
                password_hash=CASE WHEN $4 THEN NULL ELSE password_hash END,
                auth_mode=CASE WHEN $4 THEN 'password_telegram' ELSE auth_mode END
                WHERE id=$1 RETURNING *''', row['id'], permissions, status, action == 'invite')
            await c.execute('DELETE FROM staff_invites WHERE staff_id=$1', row['id'])
        token = None
        if body.get('action') in {'create', 'invite'} and row['status'] != 'disabled':
            token = secrets.token_urlsafe(32)
            await c.execute("INSERT INTO staff_invites(token_hash,staff_id,expires_at,created_by) VALUES($1,$2,NOW()+INTERVAL '24 hours',$3)", hashlib.sha256(token.encode()).hexdigest(), row['id'], actor['staff_id'])
        await audit(c, actor, 'staff_' + body['action'], 'staff', row['id'], {'role': row['role'], 'permissions': list(row['permissions']), 'status': row['status']})
        return {'account': public(row), 'invite': token}
