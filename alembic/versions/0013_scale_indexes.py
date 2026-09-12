from alembic import op


revision = "0013_scale_indexes"
down_revision = "0012_realtime_events"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_orders_actionable_created
      ON orders(status, created_at, id)
      WHERE status IN ('awaiting_receipt','paid','needs_info','in_progress')
    """)
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_orders_user_product_latest
      ON orders(user_id, product_id, created_at DESC, id DESC)
    """)
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_orders_user_status_delivered
      ON orders(user_id, status, delivered_at DESC)
    """)
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_support_unread_created
      ON support_messages(created_at DESC)
      WHERE direction='customer' AND read_at IS NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_support_unread_created")
    op.execute("DROP INDEX IF EXISTS idx_orders_user_status_delivered")
    op.execute("DROP INDEX IF EXISTS idx_orders_user_product_latest")
    op.execute("DROP INDEX IF EXISTS idx_orders_actionable_created")
