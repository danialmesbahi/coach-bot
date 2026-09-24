"""Disposable database integration test; never modifies the application DB."""
import asyncio
import os
import subprocess
import sys
import time
import json
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
import asyncpg


async def main():
    original=os.environ['DATABASE_URL'];name='analytics_test_'+uuid.uuid4().hex[:12]
    admin=await asyncpg.connect(original)
    await admin.execute(f'CREATE DATABASE {name}')
    parts=urlsplit(original)
    os.environ['DATABASE_URL']=urlunsplit((parts.scheme,parts.netloc,'/'+name,parts.query,parts.fragment))
    try:
        subprocess.run(['alembic','upgrade','head'],check=True)
        from app.db.core import db
        from app.db import repositories as repo
        from app.analytics_api import snapshot
        from app.services import telemetry
        await db.connect()
        try:
            empty=await snapshot(0,7)
            assert empty['sales']['revenue']==0 and empty['sales']['conversion'] is None
            assert empty['operations']['delivery_hours'] is None
            tg=SimpleNamespace(id=990000001,username='analytics_test',first_name='Test',last_name=None)
            await repo.upsert_user(tg)
            async with db.acquire() as c:
                product=dict(await c.fetchrow('SELECT * FROM products ORDER BY id LIMIT 1'))
                sid=await c.fetchval("INSERT INTO staff_accounts(username,display_name,role,status,permissions) VALUES('analytics_one','Analyst','staff','active',ARRAY['analytics.self']) RETURNING id")
                other=await c.fetchval("INSERT INTO staff_accounts(username,display_name,role,status) VALUES('analytics_two','Other','staff','active') RETURNING id")
                uid=await c.fetchval('SELECT id FROM users WHERE telegram_id=$1',tg.id)
                for actor in (sid,other):
                    await c.execute("INSERT INTO audit_logs(actor_staff_id,actor_name,action,target_type,target_id,metadata) VALUES($1,'Analyst','staff_login','staff',$1,'{\"secret\":\"must not leak\"}')",actor)
                    await c.execute("INSERT INTO support_messages(user_id,message_id,direction,sender_staff_id,sender_name) VALUES($1,123,'sensi',$2,'Analyst')",uid,actor)
            for amount,days,status in ((100000,2,'delivered'),(200000,1,'paid'),(300000,40,'delivered')):
                async with db.acquire() as c:
                    oid=await c.fetchval("INSERT INTO orders(user_id,product_id,amount,status,form_snapshot,payment_method) VALUES($1,$2,$3,$4,'{}','zarinpal') RETURNING id",uid,product['id'],amount,status)
                    await c.execute("UPDATE orders SET created_at=NOW()-$2*INTERVAL '1 day',paid_at=NOW()-$2*INTERVAL '1 day',delivered_at=CASE WHEN status='delivered' THEN NOW()-$2*INTERVAL '1 day'+INTERVAL '2 hours' ELSE NULL END WHERE id=$1",oid,float(days))
            telemetry.record('web','request','orders',elapsed=3)
            await telemetry.flush('web')
            result=await snapshot(0,30)
            assert result['sales']['revenue']==300000,result['sales']
            assert sum(r['revenue'] for r in result['trend'])==300000
            assert result['sales']['conversion']==100 and result['sales']['buyers']==1
            assert result['sales']['repeat_buyers']==1
            assert result['operations']['delivery_hours']==2
            assert result['telemetry'][0]['slow']==1
            own=await snapshot(sid,30)
            assert 'sales' not in own and 'team' not in own and 'telemetry' not in own
            assert own['activity']['replies']==1 and own['activity']['logins']==1
            assert len(own['logs']['items'])==2
            assert 'secret' not in str(own)
            assert len((await snapshot(sid,30,'login'))['logs']['items'])==1
            assert len((await snapshot(sid,30,'messages'))['logs']['items'])==1
            assert not (await snapshot(sid,30,'all',2))['logs']['items']
            from app.analytics_api import activity_log
            from datetime import datetime,timedelta,timezone
            async with db.acquire() as c:
                pid=await c.fetchval("INSERT INTO staff_accounts(username,display_name,role,status) VALUES('analytics_platform','Developer','platform','active') RETURNING id")
                await c.execute("INSERT INTO audit_logs(actor_staff_id,actor_name,action,target_type,target_id) VALUES($1,'Developer','product_saved','product',$2)",pid,product['id'])
                end=datetime.now(timezone.utc)
                leader=await activity_log(c,end-timedelta(days=30),end,0,'all',1,False)
                platform=await activity_log(c,end-timedelta(days=30),end,0,'all',1,True)
                assert all(r['actor_role']!='platform' for r in leader['items'])
                assert any(r['action']=='product_saved' and r['actor_role']=='platform' for r in platform['items'])
                assert any(r['action']=='reply_sent' and r['target_id']==uid for r in leader['items'])
                assert 'secret' not in str(platform)
            print('PASS: KPI SQL, financial totals, daily reconciliation, invoice cohort, null empty metrics, personal isolation, private metadata, category pagination, telemetry persistence')
            if '--benchmark' in sys.argv:
                # Disposable DB only. This is a query benchmark, not a 10k-user load test.
                async with db.acquire() as c:
                    await c.execute("INSERT INTO users(telegram_id,first_name) SELECT 8000000000+n,'Load user '||n FROM generate_series(1,10000) n")
                    await c.execute("""INSERT INTO orders(user_id,product_id,amount,status,form_snapshot,paid_at,delivered_at)
                        SELECT u.id,$1,100000,CASE WHEN n=1 THEN 'paid' ELSE 'delivered' END,'{}',NOW(),
                        CASE WHEN n=1 THEN NULL ELSE NOW() END FROM users u CROSS JOIN generate_series(1,5) n WHERE u.telegram_id>8000000000""",product['id'])
                    await c.execute("""INSERT INTO support_messages(user_id,message_id,sender_telegram_id,content_text,read_at)
                        SELECT u.id,n,u.telegram_id,'Fixture message',CASE WHEN n=1 THEN NULL ELSE NOW() END
                        FROM users u CROSS JOIN generate_series(1,10) n WHERE u.telegram_id>8000000000""")
                    await c.execute('ANALYZE users; ANALYZE orders; ANALYZE support_messages')
                samples={}
                async def measure(name,query):
                    start=time.perf_counter()
                    await query()
                    samples.setdefault(name,[]).append(round((time.perf_counter()-start)*1000,1))
                queries={'clients':lambda:repo.purchaser_list(page_size=20),'client_search':lambda:repo.purchaser_list(query='Load user 9'),
                         'tasks':lambda:repo.list_sensi_orders(page_size=20),'messages':lambda:repo.support_threads(page_size=20),
                         'analytics':lambda:snapshot(0,30)}
                for query_name,query in queries.items():
                    for _ in range(3): await measure(query_name,query)
                print('QUERY BENCHMARK ms, 10k additional users / 50k orders / 100k messages:',json.dumps(samples))
                samples.clear()
                await asyncio.gather(*(measure(name,query) for _ in range(2) for name,query in queries.items()))
                print('QUERY BENCHMARK ms, 10 concurrent reads:',json.dumps(samples))
        finally:
            await db.close()
    finally:
        await admin.execute(f'DROP DATABASE {name} WITH (FORCE)')
        await admin.close()


asyncio.run(main())
