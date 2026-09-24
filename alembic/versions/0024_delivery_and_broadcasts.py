"""Multi-part delivery and explicitly queued coach broadcasts."""
from alembic import op

revision = '0024_delivery_and_broadcasts'
down_revision = '0023_catalog_delivery'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE products ADD COLUMN content_urls jsonb NOT NULL DEFAULT '[]';
        UPDATE products SET content_urls=jsonb_build_array(content_url) WHERE content_url<>'';
        CREATE TABLE manual_deliveries (
            order_id bigint PRIMARY KEY REFERENCES orders(id),
            status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','paused','completed')),
            attempts smallint NOT NULL DEFAULT 0,
            next_at timestamptz NOT NULL DEFAULT NOW(),
            error text,
            created_at timestamptz NOT NULL DEFAULT NOW());
        CREATE INDEX manual_deliveries_due ON manual_deliveries(next_at,order_id) WHERE status='queued';
        CREATE TABLE manual_delivery_items (
            id bigserial PRIMARY KEY,
            order_id bigint NOT NULL REFERENCES manual_deliveries(order_id),
            position smallint NOT NULL,
            kind text NOT NULL CHECK (kind IN ('text','link','file')),
            body text,
            asset_id bigint REFERENCES product_assets(id),
            sent_at timestamptz,
            file_id text,
            UNIQUE(order_id,position));
        CREATE TABLE order_message_delivery (
            order_id bigint NOT NULL REFERENCES orders(id),
            item_key text NOT NULL,
            sent_at timestamptz NOT NULL DEFAULT NOW(),
            PRIMARY KEY(order_id,item_key));
        CREATE TABLE broadcasts (
            id bigserial PRIMARY KEY,
            staff_id bigint NOT NULL REFERENCES staff_accounts(id),
            message text NOT NULL,
            audience jsonb NOT NULL,
            status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','paused','completed')),
            created_at timestamptz NOT NULL DEFAULT NOW());
        CREATE TABLE broadcast_recipients (
            broadcast_id bigint NOT NULL REFERENCES broadcasts(id),
            user_id bigint NOT NULL REFERENCES users(id),
            telegram_id bigint NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed','paused')),
            attempts smallint NOT NULL DEFAULT 0,
            next_at timestamptz NOT NULL DEFAULT NOW(),
            error text,
            sent_at timestamptz,
            PRIMARY KEY(broadcast_id,user_id));
        CREATE INDEX broadcast_recipients_due ON broadcast_recipients(next_at,broadcast_id) WHERE status='pending';
    """)


def downgrade():
    op.execute("""
        DROP TABLE broadcast_recipients,broadcasts,order_message_delivery,manual_delivery_items,manual_deliveries;
        ALTER TABLE products DROP COLUMN content_urls;
    """)
