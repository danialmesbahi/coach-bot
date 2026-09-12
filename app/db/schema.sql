CREATE TABLE IF NOT EXISTS users (
 id BIGSERIAL PRIMARY KEY,
 telegram_id BIGINT NOT NULL UNIQUE,
 username TEXT,
 first_name TEXT,
 last_name TEXT,
 name TEXT,
 phone TEXT,
 age SMALLINT CHECK (age IS NULL OR age BETWEEN 10 AND 100),
 gender TEXT,
 height_cm NUMERIC(5,2) CHECK (height_cm IS NULL OR height_cm BETWEEN 100 AND 230),
 weight_kg NUMERIC(5,2) CHECK (weight_kg IS NULL OR weight_kg BETWEEN 25 AND 300),
 goal TEXT,
 training_history TEXT,
 training_days SMALLINT CHECK (training_days IS NULL OR training_days BETWEEN 0 AND 7),
 nutrition_training_days SMALLINT CHECK (nutrition_training_days IS NULL OR nutrition_training_days BETWEEN 0 AND 14),
 workout_days SMALLINT CHECK (workout_days IS NULL OR workout_days BETWEEN 0 AND 7),
 food_allergy TEXT,
 food_restriction TEXT,
 supplements TEXT,
 notes TEXT,
 body_photo_file_id TEXT,
 body_photo_file_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
 motivation_last_sent_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
 id SMALLSERIAL PRIMARY KEY,
 code TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL,
 description TEXT NOT NULL,
 price_irr BIGINT NOT NULL CHECK (price_irr >= 0),
 active BOOLEAN NOT NULL DEFAULT TRUE,
 sort_order SMALLINT NOT NULL DEFAULT 0,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id),
 product_id SMALLINT NOT NULL REFERENCES products(id),
 amount BIGINT NOT NULL CHECK (amount >= 0),
 status TEXT NOT NULL CHECK (status IN ('awaiting_payment','awaiting_receipt','payment_rejected','paid','needs_info','in_progress','ready','delivered','cancelled')),
 payment_method TEXT,
 payment_status TEXT NOT NULL DEFAULT 'unpaid',
 receipt_file_id TEXT,
 receipt_type TEXT CHECK (receipt_type IS NULL OR receipt_type IN ('photo','document')),
 payment_authority TEXT,
 gateway_ref TEXT,
 form_snapshot JSONB NOT NULL,
 plan_file_id TEXT,
 plan_file_name TEXT,
 plan_type TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 paid_at TIMESTAMPTZ,
 delivered_at TIMESTAMPTZ,
 renewal_of_order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status_created ON orders(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_paid_created ON orders(paid_at DESC) WHERE paid_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_paid_user ON orders(user_id, paid_at DESC) INCLUDE (product_id, amount, status, delivered_at) WHERE paid_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_gateway_ref ON orders(gateway_ref) WHERE gateway_ref IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_payment_authority ON orders(payment_authority) WHERE payment_authority IS NOT NULL;

CREATE TABLE IF NOT EXISTS audit_logs (
 id BIGSERIAL PRIMARY KEY,
 actor_telegram_id BIGINT NOT NULL,
 action TEXT NOT NULL,
 target_type TEXT,
 target_id BIGINT,
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_actor_created ON audit_logs(actor_telegram_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_logs(target_type, target_id, created_at DESC);

CREATE TABLE IF NOT EXISTS support_messages (
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id),
 message_id BIGINT NOT NULL,
 direction TEXT NOT NULL DEFAULT 'customer',
 sender_telegram_id BIGINT NOT NULL,
 reply_to_message_id BIGINT,
 content_type TEXT NOT NULL DEFAULT 'text',
 content_text TEXT,
 file_id TEXT,
 file_name TEXT,
 mime_type TEXT,
 file_size BIGINT,
 read_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_support_message_user_created ON support_messages(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_user_created ON support_messages(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_unread_customer ON support_messages(user_id, created_at DESC) WHERE direction='customer' AND read_at IS NULL;

CREATE TABLE IF NOT EXISTS user_profile_history (
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 product_code TEXT,
 order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
 snapshot JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_profile_history_user_created ON user_profile_history(user_id, created_at DESC);
