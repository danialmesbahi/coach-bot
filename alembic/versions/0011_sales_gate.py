from alembic import op


revision = "0011_sales_gate"
down_revision = "0010_support_media"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE IF NOT EXISTS sales_gate (
        id SMALLINT PRIMARY KEY CHECK (id=1),
        is_open BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    """)
    op.execute("INSERT INTO sales_gate(id,is_open) VALUES(1,TRUE) ON CONFLICT (id) DO NOTHING")


def downgrade():
    op.execute("DROP TABLE IF EXISTS sales_gate")
