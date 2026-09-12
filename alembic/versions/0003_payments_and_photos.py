from alembic import op
revision='0003_payments_and_photos'; down_revision='0002_security_roles'; branch_labels=None; depends_on=None

def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS body_photo_file_ids JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'unpaid'")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS receipt_file_id TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_authority TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS plan_type TEXT")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_check")
    op.execute("ALTER TABLE orders ADD CONSTRAINT orders_status_check CHECK (status IN ('awaiting_payment','awaiting_receipt','payment_rejected','paid','needs_info','in_progress','ready','delivered','cancelled'))")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_payment_authority ON orders(payment_authority) WHERE payment_authority IS NOT NULL")

def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_orders_payment_authority")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS plan_type")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS payment_authority")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS receipt_file_id")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS payment_status")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS payment_method")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS body_photo_file_ids")
