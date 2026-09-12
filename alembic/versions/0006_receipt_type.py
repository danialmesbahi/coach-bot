from alembic import op

revision = "0006_receipt_type"
down_revision = "0005_profile_history"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS receipt_type TEXT")
    op.execute("UPDATE orders SET receipt_type='photo' WHERE receipt_file_id IS NOT NULL AND receipt_type IS NULL")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_receipt_type_check")
    op.execute("ALTER TABLE orders ADD CONSTRAINT orders_receipt_type_check CHECK (receipt_type IS NULL OR receipt_type IN ('photo','document'))")


def downgrade():
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS receipt_type")
