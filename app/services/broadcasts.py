"""Explicit, recipient-snapshotted Telegram announcements."""
import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.db.core import db

log=logging.getLogger(__name__)

AUDIENCE_SQL='''FROM users u WHERE u.telegram_id>0
    AND ($1::text='all'
        OR ($1='never' AND NOT EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL))
        OR ($1='purchased' AND EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL
            AND (cardinality($2::bigint[])=0 OR o.product_id=ANY($2))))
        OR ($1='active' AND EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL
            AND (cardinality($2::bigint[])=0 OR o.product_id=ANY($2)) AND o.status='delivered'
            AND course_expiry(o.delivered_at,o.duration_days,o.subscription_expires_at)>NOW()))
        OR ($1='expired' AND EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL
            AND (cardinality($2::bigint[])=0 OR o.product_id=ANY($2)) AND o.status='delivered'
            AND course_expiry(o.delivered_at,o.duration_days,o.subscription_expires_at)<=NOW())
            AND NOT EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL
            AND (cardinality($2::bigint[])=0 OR o.product_id=ANY($2)) AND o.status='delivered'
            AND course_expiry(o.delivered_at,o.duration_days,o.subscription_expires_at)>NOW())))
    AND (cardinality($2::bigint[])=0 OR EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id
        AND o.paid_at IS NOT NULL AND o.product_id=ANY($2)))
    AND ($3::smallint IS NULL OR u.age >= $3)
    AND ($4::smallint IS NULL OR u.age <= $4)
    AND ($5::text IS NULL OR u.gender=$5)
    AND ($6::int IS NULL OR u.created_at>=NOW()-$6*INTERVAL '1 day')
    AND ($7::int IS NULL OR (SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL)>=$7)
    AND ($8::int IS NULL OR (SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL)<=$8)
    AND ($9::bigint IS NULL OR COALESCE((SELECT SUM(o.amount) FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL),0)>=$9)
    AND ($10::bigint IS NULL OR COALESCE((SELECT SUM(o.amount) FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL),0)<=$10)
    AND ($11::int IS NULL OR EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.paid_at>=NOW()-$11*INTERVAL '1 day'))
    AND ($12::text IS NULL OR position(lower($12) in lower(concat_ws(' ',u.name,u.first_name,u.last_name,u.username,u.phone,u.telegram_id::text,'U'||lpad(u.id::text,7,'0'))))>0)
    AND ($13::int IS NULL OR u.height_cm >= $13)
    AND ($14::int IS NULL OR u.height_cm <= $14)
    AND ($15::int IS NULL OR u.weight_kg >= $15)
    AND ($16::int IS NULL OR u.weight_kg <= $16)
    AND ($17::text IS NULL OR position(lower($17) in lower(concat_ws(' ',u.goal,u.training_history,u.food_allergy,u.food_restriction,u.supplements,u.notes)))>0)
    AND ($18::boolean IS NULL OR (u.phone IS NOT NULL AND btrim(u.phone)<>'')=$18)
    AND ($19::boolean IS NULL OR (u.body_photo_file_id IS NOT NULL OR jsonb_array_length(u.body_photo_file_ids)>0)=$19)
    AND ($20::int IS NULL OR u.updated_at>=NOW()-$20*INTERVAL '1 day')
    AND ($21::text IS NULL OR EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.payment_method=$21 AND o.paid_at IS NOT NULL))
    AND ($22::text IS NULL OR EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.status=$22))
    AND ($23::text='all' OR ($23='chatted' AND EXISTS(SELECT 1 FROM support_messages m WHERE m.user_id=u.id))
        OR ($23='never' AND NOT EXISTS(SELECT 1 FROM support_messages m WHERE m.user_id=u.id)))
    AND ($24::int IS NULL OR EXISTS(SELECT 1 FROM support_messages m WHERE m.user_id=u.id AND m.created_at>=NOW()-$24*INTERVAL '1 day'))'''


def audience_args(body):
    if not isinstance(body,dict): raise ValueError('invalid_audience')
    allowed={'purchased_only','active_only','purchase_state','product_ids','age_min','age_max','gender',
             'joined_within_days','orders_min','orders_max','spent_min','spent_max','last_purchase_within_days',
             'search','height_min','height_max','weight_min','weight_max','profile_keyword','has_phone',
             'has_photo','profile_updated_within_days','payment_method','order_status','message_state',
             'last_message_within_days'}
    if body.keys()-allowed: raise ValueError('invalid_audience')
    purchased=body.get('purchased_only',False)
    active=body.get('active_only',False)
    state=body.get('purchase_state', 'active' if active else 'purchased' if purchased else 'all')
    products=body.get('product_ids',[])
    low=body.get('age_min'); high=body.get('age_max')
    gender=body.get('gender'); joined=body.get('joined_within_days')
    count_min=body.get('orders_min'); count_max=body.get('orders_max')
    spend_min=body.get('spent_min'); spend_max=body.get('spent_max')
    recent=body.get('last_purchase_within_days');search=body.get('search')
    height_min=body.get('height_min');height_max=body.get('height_max')
    weight_min=body.get('weight_min');weight_max=body.get('weight_max')
    profile=body.get('profile_keyword');phone=body.get('has_phone');photo=body.get('has_photo')
    updated=body.get('profile_updated_within_days');payment=body.get('payment_method')
    order_status=body.get('order_status');messages=body.get('message_state','all')
    last_message=body.get('last_message_within_days')
    if isinstance(search,str): search=search.strip().removeprefix('@') or None
    if isinstance(profile,str): profile=profile.strip() or None
    def bounded(value, lower, upper):
        return value is None or (type(value) is int and lower<=value<=upper)
    if (type(purchased) is not bool or type(active) is not bool
        or state not in ('all','never','purchased','active','expired') or not isinstance(products,list)
        or len(products)>200 or any(type(p) is not int or p<1 for p in products)
        or len(set(products))!=len(products)
        or not bounded(low,10,100) or not bounded(high,10,100)
        or gender not in (None,'مرد','زن') or not bounded(joined,1,3650)
        or not bounded(count_min,0,100000) or not bounded(count_max,0,100000)
        or not bounded(spend_min,0,10**12) or not bounded(spend_max,0,10**12)
        or not bounded(recent,1,3650) or (search is not None and (not isinstance(search,str) or len(search)>80))
        or low is not None and high is not None and low>high
        or count_min is not None and count_max is not None and count_min>count_max
        or spend_min is not None and spend_max is not None and spend_min>spend_max
        or state=='never' and (products or recent is not None or (count_min or 0)>0 or (spend_min or 0)>0)
        or not bounded(height_min,100,230) or not bounded(height_max,100,230)
        or not bounded(weight_min,25,300) or not bounded(weight_max,25,300)
        or height_min is not None and height_max is not None and height_min>height_max
        or weight_min is not None and weight_max is not None and weight_min>weight_max
        or profile is not None and (not isinstance(profile,str) or len(profile)>80)
        or phone is not None and type(phone) is not bool or photo is not None and type(photo) is not bool
        or not bounded(updated,1,3650) or payment not in (None,'card_to_card','zarinpal')
        or order_status not in (None,'awaiting_payment','awaiting_receipt','payment_rejected','paid','needs_info','in_progress','ready','delivered','cancelled')
        or messages not in ('all','chatted','never') or not bounded(last_message,1,3650)
        or messages=='never' and last_message is not None
        or state=='never' and payment is not None
        or active and 'purchase_state' not in body and not products):
        raise ValueError('invalid_audience')
    return (state,products,low,high,gender,joined,count_min,count_max,spend_min,spend_max,recent,search,
            height_min,height_max,weight_min,weight_max,profile,phone,photo,updated,payment,order_status,messages,last_message)


async def process_broadcasts(bot):
    async with db.acquire() as c:
        recipients=await c.fetch('''SELECT r.broadcast_id,r.user_id,r.telegram_id,b.message FROM broadcast_recipients r
            JOIN broadcasts b ON b.id=r.broadcast_id WHERE r.status='pending' AND r.next_at<=NOW()
            AND b.status='queued' ORDER BY b.created_at,r.user_id LIMIT 10''')
    for row in recipients:
        try:
            # A row lock prevents another worker from sending to this recipient simultaneously.
            async with db.acquire() as c,c.transaction():
                recipient=await c.fetchrow("SELECT status FROM broadcast_recipients WHERE broadcast_id=$1 AND user_id=$2 AND next_at<=NOW() FOR UPDATE SKIP LOCKED",row['broadcast_id'],row['user_id'])
                if not recipient or recipient['status']!='pending': continue
                try:
                    await bot.send_message(row['telegram_id'],row['message'])
                except TelegramRetryAfter as exc:
                    await c.execute("UPDATE broadcast_recipients SET attempts=attempts+1,status=CASE WHEN attempts>=4 THEN 'paused' ELSE 'pending' END,next_at=NOW()+$3*INTERVAL '1 second',error=CASE WHEN attempts>=4 THEN 'rate_limited' ELSE NULL END WHERE broadcast_id=$1 AND user_id=$2",row['broadcast_id'],row['user_id'],max(30,exc.retry_after))
                except (TelegramForbiddenError,TelegramBadRequest):
                    await c.execute("UPDATE broadcast_recipients SET status='failed',error='telegram_unavailable' WHERE broadcast_id=$1 AND user_id=$2",row['broadcast_id'],row['user_id'])
                else:
                    await c.execute("UPDATE broadcast_recipients SET status='sent',sent_at=NOW() WHERE broadcast_id=$1 AND user_id=$2",row['broadcast_id'],row['user_id'])
        except Exception:
            # An ambiguous transport error may occur after Telegram accepts the send.
            # Pause rather than entering an automatic duplicate loop.
            async with db.acquire() as c:
                await c.execute("UPDATE broadcast_recipients SET status='paused',error='delivery_uncertain' WHERE broadcast_id=$1 AND user_id=$2 AND status='pending'",row['broadcast_id'],row['user_id'])
            log.exception('Broadcast recipient paused',extra={'broadcast_id':row['broadcast_id'],'event':'broadcast_delivery_failed'})
        await asyncio.sleep(.2)
    async with db.acquire() as c:
        await c.execute("""UPDATE broadcasts b SET status=CASE WHEN EXISTS(SELECT 1 FROM broadcast_recipients r WHERE r.broadcast_id=b.id AND r.status='paused') THEN 'paused' ELSE 'completed' END
            WHERE b.status='queued' AND NOT EXISTS(SELECT 1 FROM broadcast_recipients r WHERE r.broadcast_id=b.id AND r.status='pending')""")
