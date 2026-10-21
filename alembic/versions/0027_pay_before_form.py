"""Checkout collects contact details, then payment, then the questionnaire.

Orders created before this revision filled the whole form before paying, so
they are marked complete. A new order stays incomplete until the customer
submits the questionnaire after a verified payment.
"""
from alembic import op

revision = '0027_pay_before_form'
down_revision = '0026_record_edit_origin'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE orders ADD COLUMN form_completed_at timestamptz;
        UPDATE orders SET form_completed_at=created_at;
        CREATE INDEX orders_form_pending ON orders(paid_at) WHERE form_completed_at IS NULL AND paid_at IS NOT NULL;
        CREATE OR REPLACE FUNCTION preserve_client_record() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE source text := CASE WHEN current_setting('app.record_edit',true)='staff' THEN 'staff' ELSE 'profile' END;
        BEGIN
            IF TG_TABLE_NAME='orders' THEN
                -- The customer's own first submission of the questionnaire is not an edit.
                IF OLD.form_snapshot IS DISTINCT FROM NEW.form_snapshot
                   AND current_setting('app.record_edit',true) IS DISTINCT FROM 'questionnaire' THEN
                    INSERT INTO record_revisions(user_id,order_id,snapshot,origin) VALUES(OLD.user_id,OLD.id,OLD.form_snapshot,source);
                END IF;
            ELSIF (to_jsonb(OLD)-'updated_at') IS DISTINCT FROM (to_jsonb(NEW)-'updated_at') THEN
                INSERT INTO record_revisions(user_id,snapshot,origin) VALUES(OLD.id,to_jsonb(OLD),source);
            END IF;
            RETURN NEW;
        END $$;
    """)


def downgrade():
    raise RuntimeError('Restore a verified backup; incomplete paid questionnaires cannot be represented by the previous revision.')
