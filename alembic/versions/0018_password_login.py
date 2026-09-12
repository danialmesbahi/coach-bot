"""Password-only staff login; Telegram identity is optional contact data."""
from alembic import op

revision = '0018_password_login'
down_revision = '0017_staff'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE staff_accounts ALTER COLUMN telegram_id DROP NOT NULL;
        ALTER TABLE staff_accounts DROP CONSTRAINT staff_accounts_auth_mode_check;
        ALTER TABLE staff_accounts ALTER COLUMN auth_mode SET DEFAULT 'password';
        UPDATE staff_accounts SET auth_mode='password', session_version=session_version+1,
            status=CASE WHEN password_hash IS NULL AND status='active' THEN 'invited' ELSE status END;
        ALTER TABLE staff_accounts ADD CONSTRAINT staff_accounts_auth_mode_check CHECK (auth_mode='password');
        ALTER TABLE audit_logs ALTER COLUMN actor_telegram_id DROP NOT NULL;
        ALTER TABLE support_messages ALTER COLUMN sender_telegram_id DROP NOT NULL;
        DELETE FROM staff_invites;
    """)


def downgrade():
    # Password-only identities cannot safely be converted into Telegram identities.
    raise RuntimeError('Restore the pre-upgrade backup to restore Telegram authentication')
