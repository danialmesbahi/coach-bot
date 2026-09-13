"""Separate client-profile follow-ups and index each staff member's queue."""
from alembic import op

revision = '0019_collaboration_targets'
down_revision = '0018_password_login'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE staff_assignments DROP CONSTRAINT staff_assignments_target_type_check;
        ALTER TABLE staff_assignments ADD CONSTRAINT staff_assignments_target_type_check CHECK (target_type IN ('thread','customer','order'));
        ALTER TABLE staff_notes DROP CONSTRAINT staff_notes_target_type_check;
        ALTER TABLE staff_notes ADD CONSTRAINT staff_notes_target_type_check CHECK (target_type IN ('thread','customer','order'));
        CREATE INDEX staff_assignments_staff_updated ON staff_assignments(staff_id,updated_at DESC) WHERE staff_id IS NOT NULL;
    """)


def downgrade():
    op.execute("""
        DELETE FROM staff_notes WHERE target_type='customer';
        DELETE FROM staff_assignments WHERE target_type='customer';
        DROP INDEX staff_assignments_staff_updated;
        ALTER TABLE staff_assignments DROP CONSTRAINT staff_assignments_target_type_check;
        ALTER TABLE staff_assignments ADD CONSTRAINT staff_assignments_target_type_check CHECK (target_type IN ('thread','order'));
        ALTER TABLE staff_notes DROP CONSTRAINT staff_notes_target_type_check;
        ALTER TABLE staff_notes ADD CONSTRAINT staff_notes_target_type_check CHECK (target_type IN ('thread','order'));
    """)
