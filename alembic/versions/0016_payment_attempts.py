"""Keep every issued authority attributable, including older retry links."""
from alembic import op

revision = '0016_payment_attempts'
down_revision = '0015_support_media'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE TABLE payment_attempts (
            authority TEXT PRIMARY KEY,
            order_id BIGINT NOT NULL REFERENCES orders(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')
    op.execute('CREATE INDEX idx_payment_attempts_order ON payment_attempts(order_id)')
    op.execute('''
        INSERT INTO payment_attempts(authority, order_id)
        SELECT payment_authority, id FROM orders WHERE payment_authority IS NOT NULL
        ON CONFLICT DO NOTHING
    ''')


def downgrade():
    op.execute('DROP TABLE payment_attempts')
