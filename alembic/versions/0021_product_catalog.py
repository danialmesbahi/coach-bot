"""Configurable products, immutable purchase terms, and channel entitlements."""
from alembic import op

revision = '0021_product_catalog'
down_revision = '0020_followup_seen'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE products ADD COLUMN duration_days integer NOT NULL DEFAULT 30 CHECK(duration_days BETWEEN 1 AND 3650),
            ADD COLUMN delivery_mode text NOT NULL DEFAULT 'manual' CHECK(delivery_mode IN ('manual','content','channel')),
            ADD COLUMN form_fields jsonb NOT NULL DEFAULT '[]',
            ADD COLUMN questions jsonb NOT NULL DEFAULT '[]',
            ADD COLUMN response_text text NOT NULL DEFAULT '',
            ADD COLUMN content_url text NOT NULL DEFAULT '',
            ADD COLUMN channel_id bigint,
            ADD COLUMN asset_id bigint,
            ADD COLUMN archived boolean NOT NULL DEFAULT false,
            ADD COLUMN version integer NOT NULL DEFAULT 1;
        UPDATE products SET form_fields = CASE code
            WHEN 'nutrition' THEN '["name","phone","age","gender","height","weight","allergy","restriction","supplements","notes","body_photo"]'::jsonb
            WHEN 'training' THEN '["name","phone","age","gender","height","weight","goal","training_history","notes","body_photo"]'::jsonb
            ELSE '["name","phone","age","gender","height","weight","allergy","restriction","supplements","goal","training_history","notes","body_photo"]'::jsonb END;
        CREATE TABLE product_assets(id bigserial PRIMARY KEY, filename text NOT NULL, payload bytea NOT NULL,
            file_id text, created_at timestamptz NOT NULL DEFAULT NOW());
        ALTER TABLE products ADD FOREIGN KEY(asset_id) REFERENCES product_assets(id);
        ALTER TABLE orders ADD COLUMN duration_days integer NOT NULL DEFAULT 30,
            ADD COLUMN product_snapshot jsonb NOT NULL DEFAULT '{}',
            ADD COLUMN fulfillment_done boolean NOT NULL DEFAULT false,
            ADD COLUMN fulfillment_attempts integer NOT NULL DEFAULT 0,
            ADD COLUMN fulfillment_next_at timestamptz NOT NULL DEFAULT NOW(),
            ADD COLUMN fulfillment_error text,
            ADD COLUMN subscription_expires_at timestamptz;
        UPDATE orders SET product_snapshot=jsonb_build_object('title',p.title,'delivery_mode','manual','duration_days',30),
            fulfillment_done=(orders.paid_at IS NOT NULL) FROM products p WHERE p.id=orders.product_id;
        CREATE INDEX orders_fulfillment_due ON orders(fulfillment_next_at,id) WHERE paid_at IS NOT NULL AND NOT fulfillment_done;
        CREATE TABLE managed_channels(chat_id bigint PRIMARY KEY, title text NOT NULL, last_error text, verified_at timestamptz NOT NULL DEFAULT NOW());
        CREATE TABLE channel_access(order_id bigint PRIMARY KEY REFERENCES orders(id), chat_id bigint NOT NULL REFERENCES managed_channels(chat_id),
            telegram_id bigint NOT NULL, starts_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
            invite_link text UNIQUE, invite_expires_at timestamptz, joined_at timestamptz);
        CREATE INDEX channel_access_identity ON channel_access(chat_id,telegram_id,expires_at);
        CREATE TABLE channel_members(chat_id bigint NOT NULL REFERENCES managed_channels(chat_id), telegram_id bigint NOT NULL,
            next_check_at timestamptz NOT NULL DEFAULT NOW(), present boolean NOT NULL DEFAULT true,
            PRIMARY KEY(chat_id,telegram_id));
        CREATE INDEX channel_members_due ON channel_members(next_check_at) WHERE present;
    """)


def downgrade():
    op.execute("""
        DROP TABLE channel_members, channel_access, managed_channels;
        DROP INDEX orders_fulfillment_due;
        ALTER TABLE orders DROP COLUMN duration_days, DROP COLUMN product_snapshot, DROP COLUMN fulfillment_done,
            DROP COLUMN fulfillment_attempts, DROP COLUMN fulfillment_next_at, DROP COLUMN fulfillment_error, DROP COLUMN subscription_expires_at;
        ALTER TABLE products DROP COLUMN duration_days, DROP COLUMN delivery_mode, DROP COLUMN form_fields,
            DROP COLUMN questions, DROP COLUMN response_text, DROP COLUMN content_url, DROP COLUMN channel_id,
            DROP COLUMN asset_id, DROP COLUMN archived, DROP COLUMN version;
        DROP TABLE product_assets;
    """)
