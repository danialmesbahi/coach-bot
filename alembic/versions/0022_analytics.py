"""Bounded operational telemetry and KPI query indexes."""
from alembic import op

revision = '0022_analytics'
down_revision = '0021_product_catalog'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE analytics_buckets (
            hour timestamptz NOT NULL, source text NOT NULL, event text NOT NULL,
            dimension text NOT NULL, outcome text NOT NULL,
            count bigint NOT NULL, elapsed_ms double precision NOT NULL, slow_count bigint NOT NULL,
            PRIMARY KEY(hour,source,event,dimension,outcome)
        );
        CREATE TABLE analytics_collectors (
            source text PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT NOW(),
            last_seen timestamptz NOT NULL DEFAULT NOW(), dropped bigint NOT NULL DEFAULT 0
        );
        CREATE INDEX analytics_audit_time ON audit_logs(created_at,actor_staff_id);
        CREATE INDEX analytics_messages_author_time ON support_messages(sender_staff_id,created_at) WHERE direction='sensi';
        CREATE INDEX analytics_orders_created ON orders(created_at);
        UPDATE staff_accounts SET permissions=array_append(permissions,'analytics.self')
            WHERE role='staff' AND NOT 'analytics.self'=ANY(permissions);
    """)


def downgrade():
    op.execute("""
        UPDATE staff_accounts SET permissions=array_remove(permissions,'analytics.self');
        DROP INDEX analytics_orders_created;
        DROP INDEX analytics_messages_author_time;
        DROP INDEX analytics_audit_time;
        DROP TABLE analytics_buckets,analytics_collectors;
    """)
