"""Durable payment fulfillment and identity-bound private-channel access.

Orders are the work queue. Telegram does not offer exactly-once sends: a process
crash after send but before commit may repeat the message, never the entitlement.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.types import BufferedInputFile, ChatJoinRequest, ChatMemberUpdated
from app.db.core import db
from app.services.catalog import object_value

log=logging.getLogger(__name__)
router=Router(name='paid_channels')


async def _identity_lock(c,chat_id,user_id):
    await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',f'channel:{chat_id}:{user_id}')


async def active_access(c,chat_id,user_id):
    return await c.fetchval('''SELECT EXISTS(SELECT 1 FROM channel_access a JOIN orders o ON o.id=a.order_id
        WHERE a.chat_id=$1 AND a.telegram_id=$2 AND a.starts_at<=NOW() AND a.expires_at>NOW()
        AND o.paid_at IS NOT NULL AND o.status='delivered')''',chat_id,user_id)


async def _invite(c,bot,access):
    now=datetime.now(timezone.utc)
    if access['invite_link'] and access['invite_expires_at'] and access['invite_expires_at']>now:
        return access['invite_link']
    await bot.unban_chat_member(access['chat_id'],access['telegram_id'],only_if_banned=True)
    expiry=min(access['expires_at'],now+timedelta(days=1))
    link=await bot.create_chat_invite_link(access['chat_id'],name=f"order-{access['order_id']}",expire_date=expiry,creates_join_request=True)
    await c.execute('UPDATE channel_access SET invite_link=$2,invite_expires_at=$3 WHERE order_id=$1',access['order_id'],link.invite_link,expiry)
    return link.invite_link


async def channel_link(bot,order_id,telegram_id):
    async with asyncio.timeout(20),db.acquire() as c,c.transaction():
        access=await c.fetchrow('''SELECT a.* FROM channel_access a JOIN orders o ON o.id=a.order_id
            WHERE a.order_id=$1 AND a.telegram_id=$2 AND a.expires_at>NOW() AND o.paid_at IS NOT NULL AND o.status='delivered' FOR UPDATE OF a''',order_id,telegram_id)
        if not access: return None
        await _identity_lock(c,access['chat_id'],telegram_id)
        return await _invite(c,bot,access)


async def fulfill_order(bot,order_id):
    async with asyncio.timeout(60),db.acquire() as c,c.transaction():
        row=await c.fetchrow('''SELECT o.*,u.telegram_id FROM orders o JOIN users u ON u.id=o.user_id
            WHERE o.id=$1 AND o.paid_at IS NOT NULL AND NOT o.fulfillment_done FOR UPDATE OF o SKIP LOCKED''',order_id)
        if not row: return
        terms=object_value(row['product_snapshot'])
        mode=terms.get('delivery_mode','manual')
        text=terms.get('response_text') or ('✅ پرداخت تأیید شد. اطلاعات شما در صف بررسی مربی قرار گرفت؛ پس از آماده شدن، برنامه برایتان ارسال می‌شود.' if mode=='manual' else '✅ خرید شما تأیید شد. محتوای دوره در دسترس شماست.')
        file_id=None; filename=None
        if mode=='channel':
            chat_id=int(terms['channel_id'])
            await _identity_lock(c,chat_id,row['telegram_id'])
            access=await c.fetchrow('SELECT * FROM channel_access WHERE order_id=$1',order_id)
            if not access:
                # Renewals extend remaining time instead of discarding the previous subscription.
                start=await c.fetchval('SELECT GREATEST(NOW(),MAX(expires_at)) FROM channel_access WHERE chat_id=$1 AND telegram_id=$2',chat_id,row['telegram_id'])
                end=start+timedelta(days=row['duration_days'])
                access=await c.fetchrow('''INSERT INTO channel_access(order_id,chat_id,telegram_id,starts_at,expires_at)
                    VALUES($1,$2,$3,$4,$5) RETURNING *''',order_id,chat_id,row['telegram_id'],start,end)
            link=await _invite(c,bot,access)
            text+=f"\n\nورود به کانال: {link}\nاین لینک فقط برای همین حساب تلگرام معتبر است.\nاعتبار اشتراک: {row['duration_days']} روز"
            await c.execute('UPDATE orders SET subscription_expires_at=$2 WHERE id=$1',order_id,access['expires_at'])
        elif mode=='content':
            if terms.get('content_url'): text+='\n\n'+terms['content_url']
            if terms.get('asset_id'):
                asset=await c.fetchrow('SELECT * FROM product_assets WHERE id=$1',terms['asset_id'])
                if not asset: raise ValueError('Purchased asset is missing')
                filename=asset['filename']
                sent=await bot.send_document(row['telegram_id'],asset['file_id'] or BufferedInputFile(bytes(asset['payload']),filename=filename))
                file_id=sent.document.file_id
                await c.execute('UPDATE product_assets SET file_id=$2 WHERE id=$1',asset['id'],file_id)
        await bot.send_message(row['telegram_id'],text)
        await c.execute('''UPDATE orders SET fulfillment_done=true,fulfillment_error=NULL,
            status=CASE WHEN $2='manual' THEN status ELSE 'delivered' END,
            delivered_at=CASE WHEN $2='manual' THEN delivered_at ELSE COALESCE(delivered_at,NOW()) END,
            plan_file_id=COALESCE($3,plan_file_id),plan_file_name=COALESCE($4,plan_file_name),
            plan_type=CASE WHEN $3::text IS NULL THEN plan_type ELSE 'document' END,updated_at=NOW() WHERE id=$1''',order_id,mode,file_id,filename)


@router.chat_join_request()
async def join_request(event:ChatJoinRequest,bot):
    async with db.acquire() as c,c.transaction():
        if not await c.fetchval('SELECT 1 FROM managed_channels WHERE chat_id=$1',event.chat.id): return
        await _identity_lock(c,event.chat.id,event.from_user.id)
        link=event.invite_link.invite_link if event.invite_link else ''
        access=await c.fetchrow('''SELECT a.* FROM channel_access a JOIN orders o ON o.id=a.order_id
            WHERE a.chat_id=$1 AND a.telegram_id=$2 AND a.invite_link=$3 AND a.invite_expires_at>NOW()
            AND a.expires_at>NOW() AND o.paid_at IS NOT NULL AND o.status='delivered' ''',event.chat.id,event.from_user.id,link)
        if not access or not await active_access(c,event.chat.id,event.from_user.id):
            await bot.decline_chat_join_request(event.chat.id,event.from_user.id)
            return
        await bot.approve_chat_join_request(event.chat.id,event.from_user.id)
        await c.execute('UPDATE channel_access SET joined_at=NOW(),invite_expires_at=NOW() WHERE order_id=$1',access['order_id'])
        await c.execute('''INSERT INTO channel_members(chat_id,telegram_id) VALUES($1,$2)
            ON CONFLICT(chat_id,telegram_id) DO UPDATE SET present=true,next_check_at=NOW()''',event.chat.id,event.from_user.id)
    try:
        await bot.revoke_chat_invite_link(event.chat.id,link)
    except Exception:
        # Further requests still fail because the persisted invite is consumed.
        log.warning('Could not revoke consumed invitation for order=%s',access['order_id'])


@router.chat_member()
async def membership(event:ChatMemberUpdated,bot):
    member=event.new_chat_member
    async with db.acquire() as c,c.transaction():
        if not await c.fetchval('SELECT 1 FROM managed_channels WHERE chat_id=$1',event.chat.id): return
        if member.user.is_bot or member.status in {'creator','administrator'}: return
        await _identity_lock(c,event.chat.id,member.user.id)
        present=member.status in {'member','restricted'}
        if present and not await active_access(c,event.chat.id,member.user.id):
            await bot.ban_chat_member(event.chat.id,member.user.id)
            present=False
        await c.execute('''INSERT INTO channel_members(chat_id,telegram_id,present) VALUES($1,$2,$3)
            ON CONFLICT(chat_id,telegram_id) DO UPDATE SET present=$3,next_check_at=NOW()''',event.chat.id,member.user.id,present)


async def check_member(bot,chat_id,user_id):
    async with asyncio.timeout(20),db.acquire() as c,c.transaction():
        await _identity_lock(c,chat_id,user_id)
        member=await bot.get_chat_member(chat_id,user_id)
        present=member.status not in {'left','kicked'}
        if present and member.status not in {'creator','administrator'} and not member.user.is_bot and not await active_access(c,chat_id,user_id):
            await bot.ban_chat_member(chat_id,user_id)
            present=False
        await c.execute('''UPDATE channel_members SET present=$3,next_check_at=NOW()+INTERVAL '8 hours'
            WHERE chat_id=$1 AND telegram_id=$2''',chat_id,user_id,present)
        await c.execute('UPDATE managed_channels SET last_error=NULL WHERE chat_id=$1 AND last_error IS NOT NULL',chat_id)


async def run_fulfillment_loop(bot):
    while True:
        try:
            async with db.acquire() as c:
                orders=await c.fetch('''SELECT id FROM orders WHERE paid_at IS NOT NULL AND NOT fulfillment_done
                    AND fulfillment_next_at<=NOW() ORDER BY fulfillment_next_at,id LIMIT 10''')
            for row in orders:
                try:
                    await fulfill_order(bot,row['id'])
                except Exception:
                    log.exception('Order fulfillment failed: %s',row['id'])
                    async with db.acquire() as c:
                        await c.execute('''UPDATE orders SET fulfillment_attempts=fulfillment_attempts+1,
                            fulfillment_next_at=NOW()+LEAST(3600,30*power(2,LEAST(fulfillment_attempts,7))) * INTERVAL '1 second',
                            fulfillment_error='delivery_failed' WHERE id=$1 AND NOT fulfillment_done''',row['id'])
                await asyncio.sleep(.1)
            async with db.acquire() as c:
                members=await c.fetch('SELECT chat_id,telegram_id FROM channel_members WHERE present AND next_check_at<=NOW() ORDER BY next_check_at LIMIT 30')
            for member in members:
                try:
                    await check_member(bot,member['chat_id'],member['telegram_id'])
                except Exception:
                    log.exception('Channel membership check failed: %s',member['chat_id'])
                    async with db.acquire() as c:
                        await c.execute("UPDATE channel_members SET next_check_at=NOW()+INTERVAL '15 minutes' WHERE chat_id=$1 AND telegram_id=$2",member['chat_id'],member['telegram_id'])
                        await c.execute("UPDATE managed_channels SET last_error='membership_check_failed' WHERE chat_id=$1",member['chat_id'])
                await asyncio.sleep(.1)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Fulfillment worker failed')
        await asyncio.sleep(5)
