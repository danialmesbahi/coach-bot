from alembic import op

revision = "0007_paid_reporting_index"
down_revision = "0006_receipt_type"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP INDEX IF EXISTS idx_orders_paid_created")
    op.execute("CREATE INDEX idx_orders_paid_created ON orders(paid_at DESC) WHERE paid_at IS NOT NULL")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_orders_paid_created")
    op.execute("CREATE INDEX idx_orders_paid_created ON orders(paid_at DESC) WHERE status IN ('paid','in_progress','ready','delivered')")
