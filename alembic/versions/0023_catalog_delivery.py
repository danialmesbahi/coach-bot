"""Flexible terms, streamed assets and purchase-bound content delivery."""
from alembic import op

revision = '0023_catalog_delivery'
down_revision = '0022_analytics'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE products DROP CONSTRAINT products_duration_days_check;
        ALTER TABLE products ADD CHECK(duration_days BETWEEN -1 AND 36500),
            ADD COLUMN duration_unit text NOT NULL DEFAULT 'days'
                CHECK(duration_unit IN ('days','weeks','months','years','lifetime','once')),
            ADD COLUMN asset_ids bigint[] NOT NULL DEFAULT '{}';
        UPDATE products SET asset_ids=ARRAY[asset_id] WHERE asset_id IS NOT NULL;
        ALTER TABLE product_assets ALTER COLUMN payload DROP NOT NULL,
            ADD COLUMN storage_key text UNIQUE,
            ADD COLUMN byte_size bigint;
        UPDATE product_assets SET byte_size=octet_length(payload);
        CREATE TABLE order_content_delivery (
            order_id bigint NOT NULL REFERENCES orders(id),
            asset_id bigint NOT NULL REFERENCES product_assets(id),
            file_id text,
            delivered_at timestamptz NOT NULL DEFAULT NOW(),
            PRIMARY KEY(order_id,asset_id));
        CREATE TABLE content_links (
            token_hash text PRIMARY KEY,
            order_id bigint NOT NULL REFERENCES orders(id),
            asset_id bigint REFERENCES product_assets(id),
            expires_at timestamptz NOT NULL,
            redeemed_at timestamptz,
            session_hash text);
        CREATE INDEX content_links_expiry ON content_links(expires_at);
        CREATE FUNCTION course_expiry(delivered timestamptz, days integer, subscription timestamptz)
        RETURNS timestamptz LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
            SELECT CASE WHEN days=0 THEN 'infinity'::timestamptz
                WHEN days=-1 THEN delivered ELSE COALESCE(subscription,delivered+days*INTERVAL '1 day') END
        $$;
    """)


def downgrade():
    # Do not silently turn perpetual purchases into expired ones on rollback.
    op.execute("""
        DO $$ BEGIN IF EXISTS(SELECT 1 FROM orders WHERE duration_days<=0)
            OR EXISTS(SELECT 1 FROM products WHERE duration_days NOT BETWEEN 1 AND 3650)
            OR EXISTS(SELECT 1 FROM product_assets WHERE storage_key IS NOT NULL)
            THEN RAISE EXCEPTION 'New catalog data requires a reviewed data migration before rollback'; END IF; END $$;
        DROP FUNCTION course_expiry(timestamptz,integer,timestamptz);
        DROP TABLE content_links,order_content_delivery;
        ALTER TABLE products DROP COLUMN duration_unit,DROP COLUMN asset_ids,
            DROP CONSTRAINT products_duration_days_check;
        ALTER TABLE products ADD CHECK(duration_days BETWEEN 1 AND 3650);
        ALTER TABLE product_assets DROP COLUMN storage_key,DROP COLUMN byte_size,
            ALTER COLUMN payload SET NOT NULL;
    """)
