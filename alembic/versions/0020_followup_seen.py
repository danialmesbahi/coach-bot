"""Track whether the current assignee has opened a follow-up."""
from alembic import op

revision = '0020_followup_seen'
down_revision = '0019_collaboration_targets'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE staff_assignments ADD COLUMN seen_at TIMESTAMPTZ")


def downgrade():
    op.execute("ALTER TABLE staff_assignments DROP COLUMN seen_at")
