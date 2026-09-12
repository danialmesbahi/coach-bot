from __future__ import annotations
import json
from app.db.core import db


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if isinstance(value, dict) else {}


def _json_list(value) -> list:
    if isinstance(value, str):
        try:
            value=json.loads(value)
        except (TypeError, ValueError):
            return []
    return value if isinstance(value, list) else []

async def upsert_user(tg_user) -> dict:
    async with db.acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO users (telegram_id, username, first_name, last_name)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (telegram_id) DO UPDATE SET
              username=EXCLUDED.username, first_name=EXCLUDED.first_name,
              last_name=EXCLUDED.last_name, updated_at=NOW()
            RETURNING *
        """, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        return dict(row)

async def get_user(tg_id: int):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM users WHERE telegram_id=$1", tg_id)
        return dict(r) if r else None

async def get_user_by_id(user_id: int):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
        return dict(r) if r else None


async def latest_course_photos(tg_id: int):
    """Return the latest course's body photos, or None when no course exists."""
    async with db.acquire() as c:
        row=await c.fetchrow("""
            SELECT o.form_snapshot
            FROM orders o JOIN users u ON u.id=o.user_id
            WHERE u.telegram_id=$1 AND (o.status<>'cancelled' OR o.paid_at IS NOT NULL)
            ORDER BY o.created_at DESC,o.id DESC LIMIT 1
        """,tg_id)
        if not row:
            return None
        snapshot=_json_object(row['form_snapshot'])
        photos=_json_list(snapshot.get('body_photo_file_ids'))
        if not photos and snapshot.get('body_photo_file_id'):
            photos=[snapshot['body_photo_file_id']]
        return photos


async def due_motivation_users(interval_days: int, limit: int, excluded_telegram_ids: set[int] | None = None):
    interval_days=max(1,min(interval_days,30)); limit=max(1,min(limit,100))
    excluded=list(excluded_telegram_ids or set())
    async with db.acquire() as c:
        rows=await c.fetch("""
            SELECT id, telegram_id, name, first_name
            FROM users
            WHERE (motivation_last_sent_at IS NULL
               OR motivation_last_sent_at < NOW() - ($1::int * INTERVAL '1 day'))
              AND NOT (telegram_id = ANY($3::bigint[]))
            ORDER BY COALESCE(motivation_last_sent_at, created_at), id
            LIMIT $2
        """,interval_days,limit,excluded)
        return [dict(row) for row in rows]


async def mark_motivation_sent(telegram_id: int):
    async with db.acquire() as c:
        await c.execute("UPDATE users SET motivation_last_sent_at=NOW() WHERE telegram_id=$1",telegram_id)

async def update_user(tg_id: int, **fields):
    allowed = {"name","phone","age","gender","height_cm","weight_kg","goal","training_history","nutrition_training_days","food_allergy","food_restriction","supplements","notes","body_photo_file_id","body_photo_file_ids"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields: return
    keys = list(fields)
    sql = ", ".join(f"{k}=${i+2}" for i, k in enumerate(keys))
    values=[]
    for k in keys:
        v=fields[k]
        if k in {'body_photo_file_ids'} and isinstance(v,(list,dict)):
            v=json.dumps(v, ensure_ascii=False)
        values.append(v)
    async with db.acquire() as c:
        await c.execute(f"UPDATE users SET {sql}, updated_at=NOW() WHERE telegram_id=$1", tg_id, *values)


async def update_latest_course_snapshot(tg_id: int, **fields):
    """Keep a profile edit attached to the customer's latest non-cancelled course only."""
    if not fields:
        return
    async with db.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""
                SELECT o.id,o.form_snapshot,u.id AS user_id
                FROM orders o JOIN users u ON u.id=o.user_id
                WHERE u.telegram_id=$1 AND (o.status<>'cancelled' OR o.paid_at IS NOT NULL)
                ORDER BY o.created_at DESC,o.id DESC
                LIMIT 1 FOR UPDATE
            """,tg_id)
            if not row:
                return
            snapshot=_json_object(row['form_snapshot'])
            snapshot.update(fields)
            encoded=json.dumps(snapshot,ensure_ascii=False)
            await c.execute("UPDATE orders SET form_snapshot=$2::jsonb,updated_at=NOW() WHERE id=$1",row['id'],encoded)
            await c.execute("UPDATE user_profile_history SET snapshot=$2::jsonb WHERE user_id=$1 AND order_id=$3",row['user_id'],encoded,row['id'])


async def update_body_photos_for_latest_course(tg_id: int, photos: list[dict]) -> bool:
    """Atomically attach edited body photos to the user and their latest course."""
    encoded_photos=json.dumps(photos,ensure_ascii=False)
    last_file_id=photos[-1]['file_id'] if photos else None
    async with db.acquire() as c:
        async with c.transaction():
            user=await c.fetchrow("SELECT id FROM users WHERE telegram_id=$1 FOR UPDATE",tg_id)
            if not user:
                return False
            row=await c.fetchrow("""
                SELECT id,form_snapshot FROM orders
                WHERE user_id=$1 AND (status<>'cancelled' OR paid_at IS NOT NULL)
                ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE
            """,user['id'])
            if not row:
                return False
            snapshot=_json_object(row['form_snapshot'])
            snapshot['body_photo_file_id']=last_file_id
            snapshot['body_photo_file_ids']=photos
            encoded_snapshot=json.dumps(snapshot,ensure_ascii=False)
            await c.execute("UPDATE users SET body_photo_file_id=$2,body_photo_file_ids=$3::jsonb,updated_at=NOW() WHERE id=$1",user['id'],last_file_id,encoded_photos)
            await c.execute("UPDATE orders SET form_snapshot=$2::jsonb,updated_at=NOW() WHERE id=$1",row['id'],encoded_snapshot)
            await c.execute("UPDATE user_profile_history SET snapshot=$2::jsonb WHERE user_id=$1 AND order_id=$3",user['id'],encoded_snapshot,row['id'])
            return True

async def get_products(active_only=True):
    async with db.acquire() as c:
        q = "SELECT * FROM products WHERE active=TRUE ORDER BY sort_order" if active_only else "SELECT * FROM products ORDER BY sort_order"
        return [dict(r) for r in await c.fetch(q)]


async def sales_are_open() -> bool:
    """The single sales gate is shared by the web console and Telegram bot."""
    async with db.acquire() as c:
        value = await c.fetchval("SELECT is_open FROM sales_gate WHERE id=1")
    return True if value is None else bool(value)


async def set_sales_open(is_open: bool) -> bool:
    async with db.acquire() as c:
        value = await c.fetchval(
            "UPDATE sales_gate SET is_open=$1, updated_at=NOW() WHERE id=1 RETURNING is_open",
            is_open,
        )
    return bool(value)

async def get_products_for_user(tg_id: int):
    """Three-plan catalog with the only valid next action for each plan."""
    async with db.acquire() as c:
        rows = await c.fetch("""
          SELECT p.*,
                 EXISTS (
                   SELECT 1 FROM orders o JOIN users u ON u.id=o.user_id
                   WHERE u.telegram_id=$1 AND o.product_id=p.id
                     AND (o.status<>'cancelled' OR o.paid_at IS NOT NULL)
                 ) AS purchased_before,
                 latest.id AS latest_order_id, latest.status AS latest_status,
                 latest.days_remaining, latest.renewal_eligible,
                 (latest.renewal_of_order_id IS NOT NULL
                   AND latest.status NOT IN ('cancelled','delivered')) AS renewal_in_progress
          FROM products p
          LEFT JOIN LATERAL (
            SELECT o.id,o.status,o.renewal_of_order_id,
                   CASE WHEN o.delivered_at IS NULL THEN NULL ELSE
                     CEIL(EXTRACT(EPOCH FROM (o.delivered_at + INTERVAL '30 days' - NOW()))/86400.0)::int END AS days_remaining,
                   (o.status='delivered' AND o.delivered_at IS NOT NULL
                    AND o.delivered_at + INTERVAL '30 days' <= NOW() + INTERVAL '5 days'
                    AND NOT EXISTS (SELECT 1 FROM orders newer
                      WHERE newer.user_id=o.user_id AND newer.product_id=o.product_id
                        AND newer.status<>'cancelled'
                        AND (newer.created_at,newer.id)>(o.created_at,o.id))) AS renewal_eligible
            FROM orders o JOIN users u ON u.id=o.user_id
            WHERE u.telegram_id=$1 AND o.product_id=p.id AND o.status<>'cancelled'
            ORDER BY o.created_at DESC,o.id DESC LIMIT 1
          ) latest ON TRUE
          WHERE p.active=TRUE ORDER BY p.sort_order
        """,tg_id)
        return [dict(r) for r in rows]

async def get_product(product_id: int):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM products WHERE id=$1", product_id)
        return dict(r) if r else None

async def create_order(tg_id: int, product: dict, data: dict, payment_method: str, renewal_of_order_id: int | None = None):
    async with db.acquire() as c:
        async with c.transaction():
            user = await c.fetchrow("SELECT id FROM users WHERE telegram_id=$1 FOR UPDATE", tg_id)
            if not user: raise ValueError("user not found")
            if renewal_of_order_id:
                eligible=await c.fetchval("""
                  SELECT EXISTS(
                    SELECT 1 FROM orders old
                    WHERE old.id=$1 AND old.user_id=$2 AND old.product_id=$3
                      AND old.status='delivered' AND old.delivered_at IS NOT NULL
                      AND old.delivered_at + INTERVAL '30 days' <= NOW() + INTERVAL '5 days'
                      AND NOT EXISTS (SELECT 1 FROM orders newer
                        WHERE newer.user_id=old.user_id AND newer.product_id=old.product_id
                          AND newer.status<>'cancelled'
                          AND (newer.created_at,newer.id)>(old.created_at,old.id))
                  )
                """,renewal_of_order_id,user['id'],product['id'])
                if not eligible: raise ValueError('renewal not eligible')
            else:
                purchased=await c.fetchval("""
                  SELECT EXISTS(SELECT 1 FROM orders
                    WHERE user_id=$1 AND product_id=$2
                      AND (status<>'cancelled' OR paid_at IS NOT NULL))
                """,user['id'],product['id'])
                if purchased: raise ValueError('plan already purchased; renew it')
            row = await c.fetchrow("""
              INSERT INTO orders(user_id,product_id,amount,status,form_snapshot,payment_method,payment_status,renewal_of_order_id)
              VALUES($1,$2,$3,'awaiting_payment',$4::jsonb,$5,'pending',$6) RETURNING *
            """, user['id'], product['id'], product['price_irr'], json.dumps(data, ensure_ascii=False), payment_method, renewal_of_order_id)
            await c.execute(
                "INSERT INTO user_profile_history(user_id,product_code,order_id,snapshot) VALUES($1,$2,$3,$4::jsonb)",
                user['id'], product.get('code'), row['id'], json.dumps(data, ensure_ascii=False)
            )
            photos=_json_list(data.get('body_photo_file_ids'))[:6]
            last_file_id=(photos[-1].get('file_id') if photos and isinstance(photos[-1],dict) else photos[-1] if photos else None)
            await c.execute(
                "UPDATE users SET body_photo_file_id=$2,body_photo_file_ids=$3::jsonb,updated_at=NOW() WHERE id=$1",
                user['id'],last_file_id,json.dumps(photos,ensure_ascii=False),
            )
            return dict(row)

async def profile_history(tg_id: int, page: int = 1, page_size: int = 5):
    page=max(1,page); page_size=max(1,min(page_size,20)); offset=(page-1)*page_size
    async with db.acquire() as c:
        total=await c.fetchval("SELECT COUNT(*) FROM user_profile_history h JOIN users u ON u.id=h.user_id WHERE u.telegram_id=$1",tg_id)
        rows = await c.fetch("""
            SELECT h.id, h.product_code, h.order_id, h.snapshot, h.created_at,
                   COALESCE(p.title, h.product_code, 'اطلاعات شخصی') AS product_title
            FROM user_profile_history h
            LEFT JOIN products p ON p.code=h.product_code
            JOIN users u ON u.id=h.user_id
            WHERE u.telegram_id=$1
            ORDER BY h.created_at DESC, h.id DESC
            LIMIT $2 OFFSET $3
        """, tg_id, page_size, offset)
        result = [dict(r) for r in rows]
        for row in result:
            row['snapshot'] = _json_object(row.get('snapshot'))
        return result,int(total or 0)


async def profile_history_entry(tg_id: int, history_id: int):
    async with db.acquire() as c:
        row=await c.fetchrow("""
            SELECT h.*,COALESCE(p.title,h.product_code,'اطلاعات شخصی') AS product_title
            FROM user_profile_history h
            JOIN users u ON u.id=h.user_id
            LEFT JOIN products p ON p.code=h.product_code
            WHERE u.telegram_id=$1 AND h.id=$2
        """,tg_id,history_id)
        if not row:
            return None
        result=dict(row); result['snapshot']=_json_object(result.get('snapshot'))
        return result


async def latest_profile_photos(tg_id: int):
    async with db.acquire() as c:
        row=await c.fetchrow("""
            SELECT h.id,h.snapshot,COALESCE(p.title,h.product_code,'دوره') AS product_title
            FROM user_profile_history h
            JOIN users u ON u.id=h.user_id
            LEFT JOIN products p ON p.code=h.product_code
            WHERE u.telegram_id=$1
              AND jsonb_typeof(h.snapshot->'body_photo_file_ids')='array'
              AND jsonb_array_length(h.snapshot->'body_photo_file_ids')>0
            ORDER BY h.created_at DESC,h.id DESC LIMIT 1
        """,tg_id)
        if row:
            result=dict(row); result['snapshot']=_json_object(result.get('snapshot'))
            return result
        user=await c.fetchrow("SELECT body_photo_file_id,body_photo_file_ids FROM users WHERE telegram_id=$1",tg_id)
        if not user:
            return None
        photos=_json_list(user['body_photo_file_ids'])
        if not photos and user['body_photo_file_id']:
            photos=[user['body_photo_file_id']]
        return {'id':None,'product_title':'آخرین اطلاعات','snapshot':{'body_photo_file_ids':photos}} if photos else None

async def mark_mock_payment(order_id: int, gateway_ref: str):
    async with db.acquire() as c:
        row = await c.fetchrow("""
          UPDATE orders SET status='paid', payment_status='paid', gateway_ref=$2,
                 paid_at=COALESCE(paid_at,NOW()), updated_at=NOW()
          WHERE id=$1 AND payment_method='mock' AND status='awaiting_payment'
            AND gateway_ref IS NULL RETURNING *
        """, order_id, gateway_ref)
        return dict(row) if row else None

async def get_order(order_id: int):
    async with db.acquire() as c:
        r = await c.fetchrow("""
          SELECT o.*,p.code product_code,p.title product_title,u.id AS customer_id,
                 u.telegram_id,u.name,u.first_name,u.last_name,u.username,u.phone
          FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id WHERE o.id=$1
        """, order_id)
        return dict(r) if r else None

async def get_user_order(order_id: int, tg_id: int):
    async with db.acquire() as c:
        r = await c.fetchrow("""
          SELECT o.*, p.title product_title, p.code product_code,
                 CASE WHEN o.delivered_at IS NULL THEN NULL ELSE
                   CEIL(EXTRACT(EPOCH FROM (o.delivered_at + INTERVAL '30 days' - NOW()))/86400.0)::int END AS days_remaining,
                 (o.status='delivered' AND o.delivered_at IS NOT NULL
                  AND o.delivered_at + INTERVAL '30 days' <= NOW() + INTERVAL '5 days'
                  AND NOT EXISTS (SELECT 1 FROM orders newer WHERE newer.user_id=o.user_id AND newer.product_id=o.product_id
                    AND newer.status<>'cancelled' AND (newer.created_at,newer.id)>(o.created_at,o.id))) AS renewal_eligible,
                 (SELECT r.id FROM orders r WHERE r.renewal_of_order_id=o.id AND r.status<>'cancelled' ORDER BY r.created_at DESC LIMIT 1) AS active_renewal_id,
                 (SELECT r.status FROM orders r WHERE r.renewal_of_order_id=o.id AND r.status<>'cancelled' ORDER BY r.created_at DESC LIMIT 1) AS active_renewal_status
          FROM orders o JOIN products p ON p.id=o.product_id
          JOIN users u ON u.id=o.user_id
          WHERE o.id=$1 AND u.telegram_id=$2
        """, order_id, tg_id)
        return dict(r) if r else None

async def get_user_orders(tg_id: int):
    async with db.acquire() as c:
        rows = await c.fetch("""
          SELECT o.*,p.title product_title,
                 CASE WHEN o.delivered_at IS NULL THEN NULL ELSE
                   CEIL(EXTRACT(EPOCH FROM (o.delivered_at + INTERVAL '30 days' - NOW()))/86400.0)::int END AS days_remaining,
                 (o.status='delivered' AND o.delivered_at IS NOT NULL
                  AND o.delivered_at + INTERVAL '30 days' <= NOW() + INTERVAL '5 days'
                  AND NOT EXISTS (SELECT 1 FROM orders newer WHERE newer.user_id=o.user_id AND newer.product_id=o.product_id
                    AND newer.status<>'cancelled' AND (newer.created_at,newer.id)>(o.created_at,o.id))) AS renewal_eligible,
                 (SELECT r.id FROM orders r WHERE r.renewal_of_order_id=o.id AND r.status<>'cancelled' ORDER BY r.created_at DESC LIMIT 1) AS active_renewal_id,
                 (SELECT r.status FROM orders r WHERE r.renewal_of_order_id=o.id AND r.status<>'cancelled' ORDER BY r.created_at DESC LIMIT 1) AS active_renewal_status
          FROM orders o JOIN users u ON u.id=o.user_id
          JOIN products p ON p.id=o.product_id WHERE u.telegram_id=$1 ORDER BY o.created_at DESC LIMIT 30
        """, tg_id)
        return [dict(r) for r in rows]


async def has_course_access(tg_id: int) -> bool:
    async with db.acquire() as c:
        return bool(await c.fetchval("""
            SELECT EXISTS(SELECT 1 FROM orders o JOIN users u ON u.id=o.user_id
              WHERE u.telegram_id=$1 AND o.paid_at IS NOT NULL AND o.status<>'cancelled')
        """,tg_id))


async def active_courses(tg_id: int):
    async with db.acquire() as c:
        rows=await c.fetch("""
          SELECT * FROM (
            SELECT DISTINCT ON (o.product_id) o.*,p.title AS product_title,
              CASE WHEN o.delivered_at IS NULL THEN NULL ELSE
                CEIL(EXTRACT(EPOCH FROM (o.delivered_at + INTERVAL '30 days' - NOW()))/86400.0)::int END AS days_remaining
            FROM orders o JOIN users u ON u.id=o.user_id JOIN products p ON p.id=o.product_id
            WHERE u.telegram_id=$1 AND o.paid_at IS NOT NULL AND o.status<>'cancelled'
            ORDER BY o.product_id,o.created_at DESC,o.id DESC
          ) latest
          WHERE latest.status<>'delivered' OR latest.delivered_at + INTERVAL '30 days' >= NOW()
          ORDER BY latest.created_at DESC,latest.id DESC
        """,tg_id)
        return [dict(row) for row in rows]


async def renewable_orders(tg_id: int, limit: int = 10):
    async with db.acquire() as c:
        rows=await c.fetch("""
          SELECT o.id,o.product_id,o.status,o.paid_at,o.delivered_at,p.title AS product_title,
                 CEIL(EXTRACT(EPOCH FROM (o.delivered_at + INTERVAL '30 days' - NOW()))/86400.0)::int AS days_remaining
          FROM orders o JOIN users u ON u.id=o.user_id JOIN products p ON p.id=o.product_id
          WHERE u.telegram_id=$1 AND o.status='delivered' AND o.delivered_at IS NOT NULL
            AND o.delivered_at + INTERVAL '30 days' <= NOW() + INTERVAL '5 days'
            AND NOT EXISTS (SELECT 1 FROM orders newer WHERE newer.user_id=o.user_id AND newer.product_id=o.product_id
              AND newer.status<>'cancelled' AND (newer.created_at,newer.id)>(o.created_at,o.id))
          ORDER BY o.delivered_at DESC,o.id DESC LIMIT $2
        """,tg_id,max(1,min(limit,20)))
        return [dict(r) for r in rows]

async def list_sensi_orders(page: int = 1, page_size: int = 10, status: str | None = None, query: str = ""):
    page=max(1,page); page_size=max(1,min(page_size,20)); offset=(page-1)*page_size
    status=status if status in {'awaiting_receipt','paid','needs_info','in_progress'} else None
    query=query.strip().lower()[:80]
    async with db.acquire() as c:
        total=await c.fetchval("""
          SELECT COUNT(*) FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id
          WHERE o.status IN ('awaiting_receipt','paid','needs_info','in_progress','ready')
            AND ($1::text IS NULL OR o.status=$1 OR ($1='in_progress' AND o.status='ready'))
            AND ($2='' OR LOWER(COALESCE(u.name,'') || ' ' || COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'') || ' ' || COALESCE(u.username,'')) LIKE '%'||$2||'%'
              OR u.telegram_id::text=$2 OR o.id::text=$2 OR ('ORD-'||LPAD(o.id::text,6,'0')) ILIKE '%'||$2||'%'
              OR LOWER(p.title) LIKE '%'||$2||'%')
        """,status,query)
        rows = await c.fetch("""
          SELECT o.id,o.status,o.amount,o.created_at,o.updated_at,o.payment_method,o.payment_status,o.paid_at,p.title product_title,
                 u.id AS customer_id,u.telegram_id,u.name,u.first_name,u.last_name,u.username
          FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id
          WHERE o.status IN ('awaiting_receipt','paid','needs_info','in_progress','ready')
            AND ($1::text IS NULL OR o.status=$1 OR ($1='in_progress' AND o.status='ready'))
            AND ($2='' OR LOWER(COALESCE(u.name,'') || ' ' || COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'') || ' ' || COALESCE(u.username,'')) LIKE '%'||$2||'%'
              OR u.telegram_id::text=$2 OR o.id::text=$2 OR ('ORD-'||LPAD(o.id::text,6,'0')) ILIKE '%'||$2||'%'
              OR LOWER(p.title) LIKE '%'||$2||'%')
          ORDER BY CASE o.status WHEN 'awaiting_receipt' THEN 1 WHEN 'paid' THEN 2 WHEN 'in_progress' THEN 3 WHEN 'ready' THEN 3 ELSE 4 END,
                   o.created_at,o.id LIMIT $3 OFFSET $4
        """,status,query,page_size,offset)
        return [dict(r) for r in rows],int(total or 0)


async def sensi_dashboard_counts():
    async with db.acquire() as c:
        row=await c.fetchrow("""
          SELECT
            (SELECT COUNT(*) FROM orders WHERE status IN ('awaiting_receipt','paid','needs_info','in_progress','ready')) AS actionable,
            (SELECT COUNT(*) FROM orders WHERE status='awaiting_receipt') AS receipts,
            (SELECT COUNT(*) FROM orders WHERE status='paid') AS new_orders,
            (SELECT COUNT(*) FROM orders WHERE status IN ('in_progress','ready')) AS designing,
            (SELECT COUNT(*) FROM orders WHERE status='needs_info') AS needs_info,
            (SELECT COUNT(*) FROM support_messages WHERE direction='customer' AND read_at IS NULL) AS unread,
            (SELECT COUNT(DISTINCT user_id) FROM orders
             WHERE status IN ('paid','needs_info','in_progress','ready')
                OR (status='delivered' AND delivered_at + INTERVAL '30 days' > NOW())) AS active
        """)
        return dict(row)


async def customer_progress(page: int = 1, page_size: int = 10):
    page=max(1,page); page_size=max(1,min(page_size,20)); offset=(page-1)*page_size
    async with db.acquire() as c:
        total=await c.fetchval("""SELECT COUNT(DISTINCT o.user_id) FROM orders o
          WHERE o.status IN ('paid','needs_info','in_progress','ready')
             OR (o.status='delivered' AND o.delivered_at + INTERVAL '30 days' > NOW())""")
        rows=await c.fetch("""
          SELECT DISTINCT ON (u.id) o.*,u.id AS user_id,p.title AS product_title,u.name,u.first_name,
                 u.weight_kg AS current_weight,
                 first_weight.start_weight,
                 (SELECT COUNT(*) FROM orders done WHERE done.user_id=u.id AND done.status='delivered') AS delivered_count,
                 CASE WHEN o.delivered_at IS NULL THEN NULL ELSE
                   CEIL(EXTRACT(EPOCH FROM (o.delivered_at + INTERVAL '30 days' - NOW()))/86400.0)::int END AS days_remaining
          FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id
          LEFT JOIN LATERAL (
            SELECT (h.snapshot->>'weight_kg')::numeric AS start_weight
            FROM user_profile_history h
            WHERE h.user_id=u.id AND h.snapshot->>'weight_kg' ~ '^[0-9]+([.][0-9]+)?$'
            ORDER BY h.created_at,h.id LIMIT 1
          ) first_weight ON TRUE
          WHERE o.status IN ('paid','needs_info','in_progress','ready')
             OR (o.status='delivered' AND o.delivered_at + INTERVAL '30 days' > NOW())
          ORDER BY u.id,COALESCE(o.delivered_at,o.created_at) DESC,o.id DESC
          LIMIT $1 OFFSET $2
        """,page_size,offset)
        return [dict(r) for r in rows],int(total or 0)

async def update_order_status(order_id: int, status: str):
    transitions = {
        'paid': {'in_progress', 'needs_info', 'cancelled'},
        'needs_info': {'in_progress', 'cancelled'},
        'in_progress': {'needs_info', 'ready', 'cancelled'},
        'ready': {'delivered'},
    }
    async with db.acquire() as c:
        async with c.transaction():
            r = await c.fetchrow("SELECT status FROM orders WHERE id=$1 FOR UPDATE", order_id)
            if not r: return None
            current = r['status']
            if current == status: return None
            if status not in transitions.get(current, set()): return None
            row = await c.fetchrow("UPDATE orders SET status=$2, updated_at=NOW() WHERE id=$1 RETURNING *", order_id, status)
            return dict(row) if row else None

async def attach_plan(order_id: int, file_id: str, file_name: str | None, plan_type: str = 'document'):
    async with db.acquire() as c:
        r = await c.fetchrow("""
          UPDATE orders SET plan_file_id=$2, plan_file_name=$3, plan_type=$4, status='delivered', delivered_at=NOW(), updated_at=NOW()
          WHERE id=$1 AND status IN ('paid','in_progress','needs_info','ready') RETURNING *
        """, order_id, file_id, file_name, plan_type)
        return dict(r) if r else None

async def _write_audit(c, actor: int | dict, action, target_type, target_id, metadata=None):
    if isinstance(actor, dict):
        from app.services.staff import audit
        await audit(c, actor, action, target_type, target_id, metadata)
    else:
        await c.execute('''INSERT INTO audit_logs(actor_telegram_id,action,target_type,target_id,metadata,actor_staff_id,actor_name)
            VALUES($1,$2,$3,$4,$5::jsonb,(SELECT id FROM staff_accounts WHERE telegram_id=$1),(SELECT display_name FROM staff_accounts WHERE telegram_id=$1))''', actor, action, target_type, target_id, json.dumps(metadata or {}, ensure_ascii=False))


async def add_audit(actor: int | dict, action: str, target_type: str | None = None, target_id: int | None = None, metadata: dict | None = None):
    async with db.acquire() as c:
        await _write_audit(c, actor, action, target_type, target_id, metadata)

async def add_support_message(tg_id: int, message_id: int, direction: str = 'customer', sender_telegram_id: int | dict | None = None, reply_to_message_id: int | None = None, content_type: str = 'text', content_text: str | None = None, file_id: str | None = None, file_name: str | None = None, mime_type: str | None = None, file_size: int | None = None):
    actor = sender_telegram_id if isinstance(sender_telegram_id, dict) else None
    sender = actor.get('telegram_id') if actor else sender_telegram_id or tg_id
    async with db.acquire() as c:
        u = await c.fetchrow("SELECT id FROM users WHERE telegram_id=$1", tg_id)
        if u:
            await c.execute(
                """INSERT INTO support_messages(user_id,message_id,direction,sender_telegram_id,reply_to_message_id,content_type,content_text,file_id,file_name,mime_type,file_size,sender_staff_id,sender_name)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
                   COALESCE($12::bigint,(SELECT id FROM staff_accounts WHERE telegram_id=$4 AND $3='sensi')),
                   COALESCE($13::text,(SELECT display_name FROM staff_accounts WHERE telegram_id=$4 AND $3='sensi')))""",
                u['id'], message_id, direction, sender, reply_to_message_id, content_type, content_text, file_id,
                file_name, mime_type, file_size, actor['staff_id'] if actor else None, actor['display_name'] if actor else None
            )

async def support_threads(page: int = 1, page_size: int = 10, query: str = '', unread_only: bool = False):
    page=max(1,page); page_size=max(1,min(page_size,20)); offset=(page-1)*page_size
    query=(query or '').strip()[:80].lower()
    term=f'%{query}%'
    async with db.acquire() as c:
        total=await c.fetchval("""
            SELECT COUNT(*) FROM (
                SELECT sm.user_id
                FROM support_messages sm JOIN users u ON u.id=sm.user_id
                WHERE ($1='' OR LOWER(COALESCE(u.name,'') || ' ' || COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'') || ' ' || COALESCE(u.username,'')) LIKE $2
                  OR u.telegram_id::text=$1 OR ('u'||LPAD(u.id::text,6,'0'))=$1)
                GROUP BY sm.user_id
                HAVING NOT $3 OR COUNT(*) FILTER (WHERE sm.direction='customer' AND sm.read_at IS NULL) > 0
            ) filtered_threads
        """, query, term, unread_only)
        rows = await c.fetch("""
            WITH page AS (
            SELECT u.id AS user_id, u.telegram_id, u.name, u.first_name, u.last_name, u.username,
                   MAX(sm.created_at) AS last_message_at,
                   COUNT(*) FILTER (WHERE sm.direction='customer' AND sm.read_at IS NULL) AS unread_count,
                   COUNT(*) AS message_count
            FROM users u JOIN support_messages sm ON sm.user_id=u.id
            WHERE ($3='' OR LOWER(COALESCE(u.name,'') || ' ' || COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'') || ' ' || COALESCE(u.username,'')) LIKE $4
              OR u.telegram_id::text=$3 OR ('u'||LPAD(u.id::text,6,'0'))=$3)
            GROUP BY u.id
            HAVING NOT $5 OR COUNT(*) FILTER (WHERE sm.direction='customer' AND sm.read_at IS NULL) > 0
            ORDER BY (COUNT(*) FILTER (WHERE sm.direction='customer' AND sm.read_at IS NULL) > 0) DESC, MAX(sm.created_at) DESC, u.id DESC
            LIMIT $1 OFFSET $2
            )
            SELECT page.*, latest.content_text AS last_content_text,
                   latest.content_type AS last_content_type, latest.direction AS last_direction
            FROM page
            CROSS JOIN LATERAL (
                SELECT content_text,content_type,direction FROM support_messages
                WHERE user_id=page.user_id ORDER BY created_at DESC,id DESC LIMIT 1
            ) latest
            ORDER BY (page.unread_count > 0) DESC, page.last_message_at DESC, page.user_id DESC
        """,page_size,offset,query,term,unread_only)
        return [dict(r) for r in rows], int(total or 0)


async def support_thread_counts():
    async with db.acquire() as c:
        row = await c.fetchrow("""
            SELECT COUNT(DISTINCT user_id) AS all,
                   COUNT(DISTINCT user_id) FILTER (WHERE direction='customer' AND read_at IS NULL) AS unread_threads,
                   COUNT(*) FILTER (WHERE direction='customer' AND read_at IS NULL) AS unread_messages
            FROM support_messages
        """)
        return {key: int(row[key] or 0) for key in ('all','unread_threads','unread_messages')}


async def unread_support_count():
    async with db.acquire() as c:
        return int(await c.fetchval("SELECT COUNT(*) FROM support_messages WHERE direction='customer' AND read_at IS NULL") or 0)


async def mark_customer_messages_read(user_id: int):
    async with db.acquire() as c:
        await c.execute("UPDATE support_messages SET read_at=NOW() WHERE user_id=$1 AND direction='customer' AND read_at IS NULL",user_id)


async def delete_support_messages(tg_id: int, message_ids: list[int]):
    if not message_ids: return
    async with db.acquire() as c:
        await c.execute("""DELETE FROM support_messages sm USING users u
            WHERE sm.user_id=u.id AND u.telegram_id=$1 AND sm.message_id=ANY($2::bigint[])""",tg_id,message_ids)

async def support_messages_for_user(user_id: int, limit: int = 50):
    async with db.acquire() as c:
        rows = await c.fetch("""
            SELECT * FROM (
                SELECT sm.*, u.telegram_id, u.name, u.first_name, u.last_name
                FROM support_messages sm JOIN users u ON u.id=sm.user_id
                WHERE sm.user_id=$1
                ORDER BY sm.created_at DESC, sm.id DESC LIMIT $2
            ) recent
            ORDER BY recent.created_at ASC, recent.id ASC
        """, user_id, limit)
        return [dict(r) for r in rows]


async def support_message_media(message_id: int):
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT id,user_id,content_type,file_id,file_name,mime_type,file_size FROM support_messages WHERE id=$1",
            message_id,
        )
        return dict(row) if row else None

async def monthly_sales(year: int, month: int):
    async with db.acquire() as c:
        r = await c.fetchrow("""
          SELECT COUNT(*) AS orders, COALESCE(SUM(amount),0) AS revenue
          FROM orders WHERE paid_at >= make_date($1,$2,1)
          AND paid_at < (make_date($1,$2,1) + INTERVAL '1 month')
        """, year, month)
        return dict(r)


async def set_zarinpal_authority(order_id:int, authority:str):
    async with db.acquire() as c:
        async with c.transaction():
            r=await c.fetchrow("UPDATE orders SET payment_authority=$2, updated_at=NOW() WHERE id=$1 AND payment_method='zarinpal' AND status='awaiting_payment' RETURNING *", order_id, authority)
            if not r:
                # All callers send the gateway URL after this operation. Never publish
                # a payable URL whose authority could not be attached to an order.
                raise ValueError('Order is no longer awaiting payment')
            await c.execute("INSERT INTO payment_attempts(authority,order_id) VALUES($1,$2)", authority, order_id)
            return dict(r)

async def get_order_by_authority(authority:str):
    async with db.acquire() as c:
        r=await c.fetchrow("SELECT o.*, p.title AS product_title, u.telegram_id, u.name, u.phone FROM payment_attempts a JOIN orders o ON o.id=a.order_id JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id WHERE a.authority=$1", authority)
        return dict(r) if r else None

async def submit_receipt(order_id:int, file_id:str, receipt_type:str='photo'):
    if receipt_type not in {'photo', 'document'}:
        return None
    async with db.acquire() as c:
        r=await c.fetchrow("UPDATE orders SET receipt_file_id=$2, receipt_type=$3, payment_status='awaiting_review', status='awaiting_receipt', updated_at=NOW() WHERE id=$1 AND payment_method='card_to_card' AND status IN ('awaiting_payment','payment_rejected') RETURNING *", order_id,file_id,receipt_type)
        return dict(r) if r else None

async def approve_card_payment(order_id:int, actor:int | dict):
    async with db.acquire() as c:
        async with c.transaction():
            r=await c.fetchrow("UPDATE orders SET payment_status='paid', status='paid', paid_at=COALESCE(paid_at,NOW()), updated_at=NOW() WHERE id=$1 AND payment_method='card_to_card' AND status='awaiting_receipt' RETURNING id",order_id)
            if not r: return None
            await _write_audit(c, actor, 'approve_card_payment', 'order', order_id)
            full=await c.fetchrow("SELECT o.*,p.code AS product_code,p.title AS product_title,u.telegram_id,u.name,u.phone FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id WHERE o.id=$1",order_id)
            return dict(full) if full else None

async def reject_card_payment(order_id:int, actor:int | dict):
    async with db.acquire() as c:
        async with c.transaction():
            r=await c.fetchrow("UPDATE orders SET payment_status='rejected', status='payment_rejected', updated_at=NOW() WHERE id=$1 AND payment_method='card_to_card' AND status='awaiting_receipt' RETURNING id",order_id)
            if not r: return None
            await _write_audit(c, actor, 'reject_card_payment', 'order', order_id)
            full=await c.fetchrow("SELECT o.*,p.code AS product_code,p.title AS product_title,u.telegram_id,u.name,u.phone FROM orders o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.user_id WHERE o.id=$1",order_id)
            return dict(full) if full else None

async def mark_zarinpal_paid(order_id:int, ref:str):
    async with db.acquire() as c:
        r=await c.fetchrow("UPDATE orders SET payment_status='paid', status='paid', paid_at=NOW(), gateway_ref=$2, updated_at=NOW() WHERE id=$1 AND payment_method='zarinpal' AND paid_at IS NULL AND payment_status != 'paid' AND status IN ('awaiting_payment','cancelled') RETURNING *",order_id,ref)
        return dict(r) if r else None


async def cancel_awaiting_payment_order(order_id: int, tg_id: int):
    async with db.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow('''
                UPDATE orders o SET status='cancelled', payment_status='cancelled', updated_at=NOW()
                FROM users u
                WHERE o.id=$1 AND o.user_id=u.id
                  AND u.telegram_id=$2
                  AND o.status='awaiting_payment'
                  AND o.payment_status='pending'
                  AND o.paid_at IS NULL
                RETURNING o.*
            ''', order_id, tg_id)
            return dict(row) if row else None


async def total_sales():
    async with db.acquire() as c:
        r = await c.fetchrow("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(amount),0) AS revenue
            FROM orders
            WHERE paid_at IS NOT NULL
        """)
        return dict(r)

async def purchaser_report(limit: int = 1000):
    async with db.acquire() as c:
        rows = await c.fetch("""
            SELECT u.telegram_id,u.username,u.first_name,u.last_name,u.name,u.phone,
                   u.age,u.gender,u.height_cm,u.weight_kg,u.goal,u.training_history,
                   u.food_allergy,u.food_restriction,u.supplements,u.notes,
                   o.id AS order_id,o.amount,o.status,o.payment_method,o.paid_at,
                   p.title AS product_title
            FROM users u
            JOIN orders o ON o.user_id=u.id
            JOIN products p ON p.id=o.product_id
            WHERE o.paid_at IS NOT NULL
            ORDER BY o.paid_at DESC, o.id DESC
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]

async def purchaser_count():
    async with db.acquire() as c:
        r = await c.fetchrow("""
            SELECT COUNT(DISTINCT u.id) AS users
            FROM users u JOIN orders o ON o.user_id=u.id
            WHERE o.paid_at IS NOT NULL
        """)
        return int(r['users'] or 0)


async def user_count():
    async with db.acquire() as c:
        return int(await c.fetchval("SELECT COUNT(*) FROM users") or 0)


async def monthly_sales_items(year: int, month: int, page: int = 1, page_size: int = 8):
    page=max(1,page); page_size=max(1,min(page_size,20)); offset=(page-1)*page_size
    async with db.acquire() as c:
        total=await c.fetchval("""SELECT COUNT(*) FROM orders WHERE paid_at >= make_date($1,$2,1)
          AND paid_at < (make_date($1,$2,1) + INTERVAL '1 month')""",year,month)
        rows = await c.fetch("""
            SELECT o.id AS order_id, o.amount, o.paid_at, p.title AS product_title,
                   u.id AS user_id, u.name, u.phone, u.telegram_id
            FROM orders o
            JOIN products p ON p.id=o.product_id
            JOIN users u ON u.id=o.user_id
            WHERE o.paid_at >= make_date($1,$2,1)
              AND o.paid_at < (make_date($1,$2,1) + INTERVAL '1 month')
              AND o.paid_at IS NOT NULL
            ORDER BY o.paid_at ASC, o.id ASC
            LIMIT $3 OFFSET $4
        """, year, month,page_size,offset)
        return [dict(r) for r in rows],int(total or 0)


PURCHASER_SORTS = {
    "recent": "last_paid_at DESC, user_id DESC",
    "spend_desc": "total_spend DESC, user_id DESC",
    "spend_asc": "total_spend ASC, user_id DESC",
    "orders_desc": "orders_count DESC, user_id DESC",
    "orders_asc": "orders_count ASC, user_id DESC",
    "name_asc": "LOWER(COALESCE(NULLIF(name,''), NULLIF(CONCAT_WS(' ',first_name,last_name),''), username, '')) ASC, user_id DESC",
    "name_desc": "LOWER(COALESCE(NULLIF(name,''), NULLIF(CONCAT_WS(' ',first_name,last_name),''), username, '')) DESC, user_id DESC",
}


def purchaser_order_by(value: str) -> str:
    return PURCHASER_SORTS.get(value, PURCHASER_SORTS["recent"])


async def purchaser_list(
    page: int = 1,
    page_size: int = 10,
    query: str = "",
    activity: str = "all",
    product_id: int | None = None,
    sort: str = "recent",
):
    page = max(1, page)
    page_size = max(1, min(page_size, 50))
    offset = (page - 1) * page_size
    query = query.strip()[:80]
    text_query = query[1:] if query.startswith("@") else query
    identity_query = query[1:] if query[:1].lower() == "u" else query
    identity = int(identity_query) if identity_query.isdigit() and int(identity_query) <= 9_223_372_036_854_775_807 else None
    activity = activity if activity in {"all", "active", "inactive"} else "all"
    order_by = purchaser_order_by(sort)
    async with db.acquire() as c:
        rows=await c.fetch(f"""
            WITH matched_users AS MATERIALIZED (
              SELECT u.id,u.telegram_id,u.username,u.name,u.first_name,u.last_name
              FROM users u
              WHERE ($1='' OR CONCAT_WS(' ',u.name,u.first_name,u.last_name,u.username) ILIKE '%' || $1 || '%'
                     OR u.id=$6::bigint OR u.telegram_id=$6::bigint)
            ), customer_stats AS (
              SELECT u.id AS user_id,u.telegram_id,u.username,u.name,u.first_name,u.last_name,
                     MAX(o.paid_at) AS last_paid_at,COUNT(o.id) AS orders_count,
                     COALESCE(SUM(o.amount),0) AS total_spend,
                     COUNT(DISTINCT o.product_id) FILTER (WHERE
                       o.status IN ('paid','needs_info','in_progress','ready')
                       OR (o.status='delivered' AND o.delivered_at + INTERVAL '30 days' > NOW())
                     ) AS active_courses
              FROM matched_users u JOIN orders o ON o.user_id=u.id
              WHERE o.paid_at IS NOT NULL
              GROUP BY u.id,u.telegram_id,u.username,u.name,u.first_name,u.last_name
            )
            SELECT customer_stats.*,COUNT(*) OVER() AS total_count
            FROM customer_stats
            WHERE ($2='all' OR ($2='active' AND active_courses>0) OR ($2='inactive' AND active_courses=0))
              AND ($3::smallint IS NULL OR EXISTS (
                SELECT 1 FROM orders product_order
                WHERE product_order.user_id=customer_stats.user_id
                  AND product_order.product_id=$3 AND product_order.paid_at IS NOT NULL
              ))
            ORDER BY {order_by}
            LIMIT $4 OFFSET $5
        """, text_query, activity, product_id, page_size, offset, identity)
        items = [dict(row) for row in rows]
        total = int(items[0].pop("total_count")) if items else 0
        return items, total


async def purchaser_detail(user_id: int):
    async with db.acquire() as c:
        user = await c.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
        if not user: return None, []
        orders = await c.fetch("""
            SELECT o.*, p.title AS product_title, p.code AS product_code
            FROM orders o JOIN products p ON p.id=o.product_id
            WHERE o.user_id=$1
            ORDER BY o.created_at DESC, o.id DESC
        """, user_id)
        return dict(user), [dict(r) for r in orders]


async def purchaser_identity(user_id: int):
    async with db.acquire() as c:
        row = await c.fetchrow("""
            SELECT u.*, EXISTS(
              SELECT 1 FROM orders o WHERE o.user_id=u.id AND o.paid_at IS NOT NULL
            ) AS has_paid_order
            FROM users u WHERE u.id=$1
        """, user_id)
        return dict(row) if row else None


async def profile_history_for_user(user_id: int, limit: int = 50):
    async with db.acquire() as c:
        rows = await c.fetch("""
            SELECT h.*, COALESCE(p.title, h.product_code, 'اطلاعات شخصی') AS product_title
            FROM user_profile_history h
            LEFT JOIN products p ON p.code=h.product_code
            WHERE h.user_id=$1
            ORDER BY h.created_at DESC, h.id DESC LIMIT $2
        """, user_id, limit)
        result = [dict(r) for r in rows]
        for row in result:
            row['snapshot'] = _json_object(row.get('snapshot'))
        return result
