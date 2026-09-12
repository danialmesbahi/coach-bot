from alembic import op


revision = "0014_customer_list_index"
down_revision = "0013_scale_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_orders_paid_user
      ON orders(user_id, paid_at DESC)
      INCLUDE (product_id, amount, status, delivered_at)
      WHERE paid_at IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_orders_paid_user")
