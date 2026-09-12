from alembic import op


revision = "0012_realtime_events"
down_revision = "0011_sales_gate"
branch_labels = None
depends_on = None


TABLES = ("users", "products", "orders", "support_messages", "user_profile_history", "sales_gate")


def upgrade():
    op.execute("""
      CREATE OR REPLACE FUNCTION notify_coach_update() RETURNS trigger AS $$
      DECLARE
        row_data JSONB := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
      BEGIN
        PERFORM pg_notify('coach_updates', jsonb_build_object(
          'table', TG_TABLE_NAME,
          'action', lower(TG_OP),
          'id', row_data->>'id',
          'userId', COALESCE(row_data->>'user_id', row_data->>'id'),
          'direction', row_data->>'direction',
          'readAt', row_data->>'read_at'
        )::text);
        IF TG_OP = 'DELETE' THEN
          RETURN OLD;
        END IF;
        RETURN NEW;
      END;
      $$ LANGUAGE plpgsql;
    """)
    for table in TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS coach_update_notify ON {table}")
        op.execute(
            f"CREATE TRIGGER coach_update_notify AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION notify_coach_update()"
        )


def downgrade():
    for table in TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS coach_update_notify ON {table}")
    op.execute("DROP FUNCTION IF EXISTS notify_coach_update()")
