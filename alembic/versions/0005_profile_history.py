from alembic import op

revision = "0005_profile_history"
down_revision = "0004_support_bidirectional"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'text'")
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS content_text TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_support_message_user_created ON support_messages(user_id, created_at DESC)")
    op.execute("""CREATE TABLE IF NOT EXISTS user_profile_history (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        product_code TEXT,
        order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
        snapshot JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_profile_history_user_created ON user_profile_history(user_id, created_at DESC)")

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_profile_history_user_created")
    op.execute("DROP TABLE IF EXISTS user_profile_history")
    op.execute("DROP INDEX IF EXISTS idx_support_message_user_created")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS content_text")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS content_type")
