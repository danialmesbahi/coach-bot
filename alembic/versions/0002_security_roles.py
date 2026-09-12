from alembic import op

revision='0002_security_roles'
down_revision='0001_initial'
branch_labels=None
depends_on=None

def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
      id BIGSERIAL PRIMARY KEY,
      actor_telegram_id BIGINT NOT NULL,
      action TEXT NOT NULL,
      target_type TEXT,
      target_id BIGINT,
      metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_audit_actor_created ON audit_logs(actor_telegram_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_logs(target_type, target_id, created_at DESC);
    CREATE TABLE IF NOT EXISTS support_messages (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id),
      message_id BIGINT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_support_user_created ON support_messages(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_orders_paid_created ON orders(paid_at DESC) WHERE status IN ('paid','in_progress','ready','delivered');
    """)

def downgrade():
    op.execute("DROP TABLE IF EXISTS support_messages")
    op.execute("DROP TABLE IF EXISTS audit_logs")
