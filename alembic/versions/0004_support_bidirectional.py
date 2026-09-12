from alembic import op

revision = "0004_support_bidirectional"
down_revision = "0003_payments_and_photos"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS direction TEXT NOT NULL DEFAULT 'customer'")
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS sender_telegram_id BIGINT")
    op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS reply_to_message_id BIGINT")
    op.execute("UPDATE support_messages sm SET sender_telegram_id = u.telegram_id FROM users u WHERE u.id = sm.user_id AND sm.sender_telegram_id IS NULL")
    op.execute("ALTER TABLE support_messages ALTER COLUMN sender_telegram_id SET NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_support_direction_created ON support_messages(direction, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_support_sender_created ON support_messages(sender_telegram_id, created_at DESC)")

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_support_sender_created")
    op.execute("DROP INDEX IF EXISTS idx_support_direction_created")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS reply_to_message_id")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS sender_telegram_id")
    op.execute("ALTER TABLE support_messages DROP COLUMN IF EXISTS direction")
