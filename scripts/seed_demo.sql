-- Re-runnable local demo data. Run with:
-- docker compose exec -T postgres psql -U coach -d coach -v target_tg=5819561965 -f /tmp/seed_demo.sql
\if :{?target_tg}
\else
\set target_tg 5819561965
\endif

BEGIN;

-- Only remove rows created by this script; existing real data is untouched.
DELETE FROM support_messages WHERE message_id BETWEEN 9500000000 AND 9500000999;
DELETE FROM user_profile_history WHERE snapshot->>'seed'='coach-bot-demo-20260825';
UPDATE orders SET renewal_of_order_id=NULL
WHERE renewal_of_order_id IN (SELECT id FROM orders WHERE form_snapshot->>'seed'='coach-bot-demo-20260825');
DELETE FROM orders WHERE form_snapshot->>'seed'='coach-bot-demo-20260825';

INSERT INTO users(telegram_id,username,first_name,name,phone,age,gender,height_cm,weight_kg,goal,training_history,food_allergy,food_restriction,supplements,notes,motivation_last_sent_at)
SELECT 9901000000+n,
       'demo_customer_'||n,
       'تستی '||n,
       '🧪 مشتری تست '||n,
       '09120000'||lpad(n::text,2,'0'),
       20+n,
       CASE WHEN n%2=0 THEN 'زن' ELSE 'مرد' END,
       160+n,
       58+n*2,
       (ARRAY['کاهش وزن','عضله‌سازی','افزایش آمادگی'])[1+(n%3)],
       'سابقه تمرین تستی '||n||' ماه',
       CASE WHEN n%4=0 THEN 'حساسیت به لبنیات' ELSE NULL END,
       CASE WHEN n%5=0 THEN 'بدون گلوتن' ELSE NULL END,
       CASE WHEN n%3=0 THEN 'کراتین' ELSE NULL END,
       'دادهٔ آزمایشی برای پوشش مسیرهای بات',
       NOW()-INTERVAL '4 days'
FROM generate_series(1,15) AS n
ON CONFLICT (telegram_id) DO UPDATE SET
  username=EXCLUDED.username,first_name=EXCLUDED.first_name,name=EXCLUDED.name,phone=EXCLUDED.phone,
  age=EXCLUDED.age,gender=EXCLUDED.gender,height_cm=EXCLUDED.height_cm,weight_kg=EXCLUDED.weight_kg,
  goal=EXCLUDED.goal,training_history=EXCLUDED.training_history,food_allergy=EXCLUDED.food_allergy,
  food_restriction=EXCLUDED.food_restriction,supplements=EXCLUDED.supplements,notes=EXCLUDED.notes,
  motivation_last_sent_at=EXCLUDED.motivation_last_sent_at,updated_at=NOW();

WITH demo_orders AS (
  SELECT u.id AS user_id,p.id AS product_id,p.price_irr,n,
         (ARRAY['awaiting_payment','awaiting_receipt','payment_rejected','paid','needs_info','in_progress','ready','delivered','cancelled'])[((n-1)%9)+1] AS status
  FROM generate_series(1,15) AS n
  JOIN users u ON u.telegram_id=9901000000+n
  JOIN products p ON p.id=((n-1)%3)+1
)
INSERT INTO orders(user_id,product_id,amount,status,form_snapshot,payment_method,payment_status,receipt_type,created_at,paid_at,delivered_at)
SELECT user_id,product_id,price_irr,status,
       jsonb_build_object('seed','coach-bot-demo-20260825','name','🧪 مشتری تست '||n,'phone','09120000'||lpad(n::text,2,'0'),'age',20+n,'gender',CASE WHEN n%2=0 THEN 'زن' ELSE 'مرد' END,'height_cm',160+n,'weight_kg',58+n*2,'goal','هدف تستی','training_history','سابقه تستی','notes','سفارش تستی با وضعیت '||status,'body_photo_file_ids',jsonb_build_array()),
       CASE WHEN status IN ('awaiting_receipt','payment_rejected') THEN 'card_to_card' ELSE 'mock' END,
       CASE status WHEN 'awaiting_payment' THEN 'pending' WHEN 'awaiting_receipt' THEN 'awaiting_review' WHEN 'payment_rejected' THEN 'rejected' WHEN 'cancelled' THEN 'cancelled' ELSE 'paid' END,
       CASE WHEN status IN ('awaiting_receipt','payment_rejected') THEN 'photo' ELSE NULL END,
       NOW()-(n||' days')::interval,
       CASE WHEN status IN ('paid','needs_info','in_progress','ready','delivered') THEN NOW()-(n||' days')::interval+INTERVAL '1 hour' ELSE NULL END,
       CASE WHEN status='delivered' THEN NOW()-INTERVAL '27 days' ELSE NULL END
FROM demo_orders;

-- A renewal already in progress: its original delivered order must not offer another renewal.
WITH original AS (
  INSERT INTO orders(user_id,product_id,amount,status,form_snapshot,payment_method,payment_status,created_at,paid_at,delivered_at)
  SELECT u.id,p.id,p.price_irr,'delivered',
         jsonb_build_object('seed','coach-bot-demo-20260825','name','🧪 مشتری تست 1','weight_kg',60,'notes','دورهٔ قبلی برای تست تمدید','body_photo_file_ids',jsonb_build_array()),
         'mock','paid',NOW()-INTERVAL '29 days',NOW()-INTERVAL '29 days',NOW()-INTERVAL '27 days'
  FROM users u JOIN products p ON p.code='training' WHERE u.telegram_id=9901000001
  RETURNING id,user_id,product_id,amount
)
INSERT INTO orders(user_id,product_id,amount,status,form_snapshot,payment_method,payment_status,receipt_type,renewal_of_order_id,created_at)
SELECT user_id,product_id,amount,'awaiting_receipt',
       jsonb_build_object('seed','coach-bot-demo-20260825','name','🧪 مشتری تست 1','weight_kg',60,'notes','تمدید در انتظار تأیید پرداخت','body_photo_file_ids',jsonb_build_array()),
       'card_to_card','awaiting_review','photo',id,NOW()-INTERVAL '1 day'
FROM original;

-- The current tester gets a clearly labelled expiring course and enough history for pagination.
WITH target_orders AS (
  INSERT INTO orders(user_id,product_id,amount,status,form_snapshot,payment_method,payment_status,created_at,paid_at,delivered_at)
  SELECT u.id,p.id,p.price_irr,v.status,
         jsonb_build_object('seed','coach-bot-demo-20260825','name','Danial — تست','phone','09120000000','age',28,'gender','مرد','height_cm',178,'weight_kg',82-v.seq,'goal','تست مسیر مشتری','training_history','دادهٔ تستی','notes',v.note,'body_photo_file_ids',jsonb_build_array()),
         'mock',CASE WHEN v.status='cancelled' THEN 'cancelled' ELSE 'paid' END,
         NOW()-(v.seq||' days')::interval,
         CASE WHEN v.status='delivered' THEN NOW()-INTERVAL '27 days' ELSE NULL END,
         CASE WHEN v.status='delivered' THEN NOW()-INTERVAL '27 days' ELSE NULL END
  FROM users u
  JOIN (VALUES ('complete','delivered',27,'دورهٔ تستی با امکان تمدید'),('training','cancelled',3,'سفارش تستی لغوشده'),('nutrition','cancelled',4,'سفارش تستی لغوشده'),('training','cancelled',5,'سفارش تستی لغوشده')) AS v(code,status,seq,note) ON TRUE
  JOIN products p ON p.code=v.code
  WHERE u.telegram_id=:'target_tg'::bigint
  RETURNING id,user_id,product_id,form_snapshot,created_at
)
INSERT INTO user_profile_history(user_id,product_code,order_id,snapshot,created_at)
SELECT o.user_id,p.code,o.id,o.form_snapshot,o.created_at FROM target_orders o JOIN products p ON p.id=o.product_id;

INSERT INTO user_profile_history(user_id,product_code,order_id,snapshot,created_at)
SELECT o.user_id,p.code,o.id,o.form_snapshot,o.created_at
FROM orders o JOIN products p ON p.id=o.product_id
WHERE o.form_snapshot->>'seed'='coach-bot-demo-20260825'
  AND NOT EXISTS (SELECT 1 FROM user_profile_history h WHERE h.order_id=o.id);

INSERT INTO support_messages(user_id,message_id,direction,sender_telegram_id,content_type,content_text,read_at,created_at)
SELECT u.id,9500000000+n*10,'customer',u.telegram_id,'text','🧪 پیام تستی مشتری '||n||' برای بررسی اینباکس',
       CASE WHEN n%2=0 THEN NOW()-INTERVAL '2 hours' ELSE NULL END,NOW()-(n||' hours')::interval
FROM generate_series(1,15) AS n JOIN users u ON u.telegram_id=9901000000+n
UNION ALL
SELECT u.id,9500000001+n*10,'sensi',8697023888,'text','🧪 پاسخ مربی برای مشتری تست '||n,NOW()-INTERVAL '1 hour',NOW()-(n||' hours')::interval+INTERVAL '5 minutes'
FROM generate_series(1,15) AS n JOIN users u ON u.telegram_id=9901000000+n;

COMMIT;
