"""Database-backed staff, revocable access and collaborative attribution."""
from alembic import op

revision = '0017_staff'
down_revision = '0016_payment_attempts'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE TABLE staff_accounts (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL UNIQUE CHECK (telegram_id > 0),
            username TEXT NOT NULL UNIQUE CHECK (username = lower(username)),
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('platform','leader','staff')),
            permissions TEXT[] NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','active','disabled')),
            auth_mode TEXT NOT NULL DEFAULT 'password_telegram' CHECK (auth_mode IN ('telegram','password_telegram')),
            password_hash TEXT,
            session_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX staff_single_leader ON staff_accounts(role) WHERE role='leader';
        CREATE TABLE staff_invites (
            token_hash TEXT PRIMARY KEY,
            staff_id BIGINT NOT NULL UNIQUE REFERENCES staff_accounts(id),
            expires_at TIMESTAMPTZ NOT NULL,
            created_by BIGINT NOT NULL REFERENCES staff_accounts(id)
        );
        ALTER TABLE support_messages ADD COLUMN sender_staff_id BIGINT REFERENCES staff_accounts(id);
        ALTER TABLE support_messages ADD COLUMN sender_name TEXT;
        ALTER TABLE audit_logs ADD COLUMN actor_staff_id BIGINT REFERENCES staff_accounts(id);
        ALTER TABLE audit_logs ADD COLUMN actor_name TEXT;
        CREATE INDEX audit_staff_created ON audit_logs(actor_staff_id, id DESC);
        CREATE TABLE staff_assignments (
            target_type TEXT NOT NULL CHECK (target_type IN ('thread','order')),
            target_id BIGINT NOT NULL,
            staff_id BIGINT REFERENCES staff_accounts(id),
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (target_type,target_id)
        );
        CREATE TABLE staff_notes (
            id BIGSERIAL PRIMARY KEY,
            target_type TEXT NOT NULL CHECK (target_type IN ('thread','order')),
            target_id BIGINT NOT NULL,
            staff_id BIGINT NOT NULL REFERENCES staff_accounts(id),
            author_name TEXT NOT NULL,
            body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX staff_notes_target ON staff_notes(target_type,target_id,id DESC);
    ''')
    for table in ('staff_accounts', 'staff_assignments', 'staff_notes'):
        op.execute(f'CREATE TRIGGER coach_update_notify AFTER INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION notify_coach_update()')


def downgrade():
    op.execute('DROP TABLE staff_notes, staff_assignments, staff_invites')
    op.execute('ALTER TABLE support_messages DROP COLUMN sender_staff_id, DROP COLUMN sender_name')
    op.execute('ALTER TABLE audit_logs DROP COLUMN actor_staff_id, DROP COLUMN actor_name')
    op.execute('DROP TABLE staff_accounts')
