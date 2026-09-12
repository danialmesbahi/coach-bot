from alembic import op

revision = '0008_motivation_schedule'
down_revision = '0007_paid_reporting_index'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS motivation_last_sent_at TIMESTAMPTZ')
    op.execute('CREATE INDEX IF NOT EXISTS idx_users_motivation_due ON users(motivation_last_sent_at, created_at)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS idx_users_motivation_due')
    op.execute('ALTER TABLE users DROP COLUMN IF EXISTS motivation_last_sent_at')
