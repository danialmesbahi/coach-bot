from alembic import op

revision = '0009_unread_and_renewals'
down_revision = '0008_motivation_schedule'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ')
    op.execute("CREATE INDEX IF NOT EXISTS idx_support_unread_customer ON support_messages(user_id, created_at DESC) WHERE direction='customer' AND read_at IS NULL")
    op.execute('ALTER TABLE orders ADD COLUMN IF NOT EXISTS renewal_of_order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL')


def downgrade():
    op.execute('ALTER TABLE orders DROP COLUMN IF EXISTS renewal_of_order_id')
    op.execute('DROP INDEX IF EXISTS idx_support_unread_customer')
    op.execute('ALTER TABLE support_messages DROP COLUMN IF EXISTS read_at')
