"""Checkpointed, multi-part manual order delivery."""
import asyncio
import logging

from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import FSInputFile

from app.db.core import db
from app.services.content import asset_path
from app.utils.media import message_file

log = logging.getLogger(__name__)


async def deliver_manual_order(bot, order_id):
    async with asyncio.timeout(300), db.acquire() as c, c.transaction():
        order = await c.fetchrow('''SELECT o.id,o.status,u.telegram_id FROM orders o
            JOIN users u ON u.id=o.user_id WHERE o.id=$1 AND o.status IN ('in_progress','ready')
            FOR UPDATE OF o SKIP LOCKED''',order_id)
        if not order:
            return
        delivery = await c.fetchrow("SELECT * FROM manual_deliveries WHERE order_id=$1 AND status='queued' AND next_at<=NOW() FOR UPDATE",order_id)
        if not delivery:
            return
        items = await c.fetch('SELECT * FROM manual_delivery_items WHERE order_id=$1 ORDER BY position',order_id)
        first_id = None
        first_name = None
        for item in items:
            if item['sent_at']:
                if item['kind']=='file' and not first_name:
                    asset=await c.fetchrow('SELECT filename FROM product_assets WHERE id=$1',item['asset_id'])
                    first_id,first_name=item['file_id'],asset['filename'] if asset else None
                continue
            file_id=None
            if item['kind']=='file':
                asset=await c.fetchrow('SELECT filename,storage_key,file_id FROM product_assets WHERE id=$1',item['asset_id'])
                if not asset:
                    raise ValueError('Manual delivery file is missing')
                sent=await bot.send_document(order['telegram_id'],asset['file_id'] or FSInputFile(asset_path(asset['storage_key']),filename=asset['filename']),protect_content=True,disable_content_type_detection=True,request_timeout=180)
                kind,sent_id=message_file(sent)
                file_id=sent_id if kind=='document' else None
                if not first_name:
                    first_id,first_name=file_id,asset['filename']
            else:
                await bot.send_message(order['telegram_id'],item['body'],protect_content=True)
            # Commit each item separately, so a later failure resumes at the next part.
            async with db.acquire() as checkpoint,checkpoint.transaction():
                await checkpoint.execute('UPDATE manual_delivery_items SET sent_at=NOW(),file_id=$2 WHERE id=$1',item['id'],file_id)
                if file_id and item['asset_id']:
                    await checkpoint.execute('UPDATE product_assets SET file_id=$2 WHERE id=$1',item['asset_id'],file_id)
        await c.execute("UPDATE orders SET status='delivered',delivered_at=NOW(),updated_at=NOW(),plan_file_id=$2,plan_file_name=$3,plan_type=CASE WHEN $2::text IS NULL THEN NULL ELSE 'document' END WHERE id=$1",order_id,first_id,first_name)
        await c.execute("UPDATE manual_deliveries SET status='completed',error=NULL WHERE order_id=$1",order_id)


async def process_manual_deliveries(bot):
    async with db.acquire() as c:
        due=await c.fetch("SELECT order_id FROM manual_deliveries WHERE status='queued' AND next_at<=NOW() ORDER BY next_at,order_id LIMIT 5")
    for row in due:
        try:
            await deliver_manual_order(bot,row['order_id'])
        except Exception as exc:
            retry=isinstance(exc,TelegramRetryAfter)
            async with db.acquire() as c:
                await c.execute("""UPDATE manual_deliveries SET status=CASE WHEN attempts>=4 THEN 'paused' ELSE $2 END,
                    attempts=attempts+1,
                    next_at=CASE WHEN $3::int>0 THEN NOW()+$3*INTERVAL '1 second' ELSE next_at END,
                    error=$4 WHERE order_id=$1""",row['order_id'],'queued' if retry else 'paused',max(30,exc.retry_after) if retry else 0,'rate_limited' if retry else 'delivery_paused')
            log.exception('Manual order delivery paused',extra={'order_id':row['order_id'],'event':'manual_delivery_failed'})
        await asyncio.sleep(.1)
