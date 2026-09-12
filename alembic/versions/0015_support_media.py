from alembic import op


revision = "0015_support_media"
down_revision = "0014_customer_list_index"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS file_name TEXT")
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS mime_type TEXT")
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS file_size BIGINT")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_users_management_search
      ON users USING GIN (LOWER(COALESCE(name,'') || ' ' || COALESCE(first_name,'') || ' ' || COALESCE(last_name,'') || ' ' || COALESCE(username,'')) gin_trgm_ops)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_title_search ON products USING GIN (LOWER(title) gin_trgm_ops)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_products_title_search")
    op.execute("DROP INDEX IF EXISTS idx_users_management_search")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS file_size")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS mime_type")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS file_name")
