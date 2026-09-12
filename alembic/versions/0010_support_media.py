from alembic import op

revision = '0010_support_media'
down_revision = '0009_unread_and_renewals'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS file_id TEXT')


def downgrade():
    op.execute('ALTER TABLE support_messages DROP COLUMN IF EXISTS file_id')
