"""Versioned client records, order responses and private attachment index."""
from alembic import op

revision = '0025_client_records'
down_revision = '0024_delivery_and_broadcasts'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE users ADD COLUMN measurements jsonb NOT NULL DEFAULT '{}';
        CREATE TABLE record_revisions (
            id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id),
            order_id bigint REFERENCES orders(id), snapshot jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT NOW());
        CREATE INDEX record_revisions_user ON record_revisions(user_id,id DESC);
        CREATE FUNCTION preserve_client_record() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME='orders' THEN
                IF OLD.form_snapshot IS DISTINCT FROM NEW.form_snapshot THEN
                    INSERT INTO record_revisions(user_id,order_id,snapshot) VALUES(OLD.user_id,OLD.id,OLD.form_snapshot);
                END IF;
            ELSIF (to_jsonb(OLD)-'updated_at') IS DISTINCT FROM (to_jsonb(NEW)-'updated_at') THEN
                INSERT INTO record_revisions(user_id,snapshot) VALUES(OLD.id,to_jsonb(OLD));
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER preserve_order_record BEFORE UPDATE OF form_snapshot ON orders FOR EACH ROW EXECUTE FUNCTION preserve_client_record();
        CREATE TRIGGER preserve_user_record BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION preserve_client_record();
        CREATE TABLE order_info_requests (
            id bigserial PRIMARY KEY, order_id bigint NOT NULL REFERENCES orders(id),
            staff_id bigint REFERENCES staff_accounts(id), body text NOT NULL,
            status text NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','submitted','reviewed')),
            created_at timestamptz NOT NULL DEFAULT NOW(), submitted_at timestamptz,
            notification_sent boolean NOT NULL DEFAULT false);
        CREATE UNIQUE INDEX order_info_open ON order_info_requests(order_id) WHERE status='waiting';
        CREATE INDEX order_info_history ON order_info_requests(order_id,id DESC);
        -- Existing verified orders must not lose the old completion request on upgrade.
        -- No notification is sent during migration; the owner can open it from order details.
        INSERT INTO order_info_requests(order_id,body,created_at)
        SELECT o.id,LEFT(COALESCE(NULLIF((SELECT metadata->>'message' FROM audit_logs
            WHERE target_type='order' AND target_id=o.id AND action='web_needs_info'
            ORDER BY created_at DESC,id DESC LIMIT 1),''),'لطفاً اطلاعات تکمیلی موردنیاز مربی را برای بررسی این سفارش ارسال کن.'),1000),o.updated_at
        FROM orders o WHERE o.status='needs_info' AND o.paid_at IS NOT NULL
            AND COALESCE(o.product_snapshot->>'delivery_mode','manual')='manual';
        CREATE TABLE order_info_items (
            id bigserial PRIMARY KEY, request_id bigint NOT NULL REFERENCES order_info_requests(id),
            message_id bigint NOT NULL, content_type text NOT NULL, content_text text,
            file_id text, file_name text, file_size bigint, mime_type text,
            created_at timestamptz NOT NULL DEFAULT NOW(), UNIQUE(request_id,message_id));
        CREATE TABLE client_files (
            id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id),
            order_id bigint REFERENCES orders(id), source text NOT NULL,
            source_id bigint NOT NULL, file_id text, asset_id bigint REFERENCES product_assets(id),
            filename text NOT NULL, mime_type text, byte_size bigint,
            storage_key text, status text NOT NULL DEFAULT 'pending', error text,
            attempts smallint NOT NULL DEFAULT 0, next_at timestamptz NOT NULL DEFAULT NOW(),
            created_at timestamptz NOT NULL DEFAULT NOW(), UNIQUE(source,source_id,file_id));
        CREATE INDEX client_files_user ON client_files(user_id,id DESC);
        CREATE INDEX client_files_remote_identity ON client_files(file_id) WHERE file_id IS NOT NULL;
        CREATE INDEX client_files_due ON client_files(next_at,id) WHERE status='pending';
        CREATE INDEX client_files_leases ON client_files(next_at,id) WHERE status='archiving';
        CREATE UNIQUE INDEX client_files_asset ON client_files(source,source_id,asset_id) WHERE asset_id IS NOT NULL;
        CREATE TABLE client_archive_cursors(source text PRIMARY KEY,last_id bigint NOT NULL DEFAULT 0,last_asset_id bigint NOT NULL DEFAULT 0);
        INSERT INTO client_archive_cursors(source) VALUES('orders'),('users'),('support_messages'),('manual_delivery_items'),('user_profile_history'),('order_content_delivery');
        CREATE INDEX support_message_identity ON support_messages(user_id,message_id,direction);
        CREATE FUNCTION index_client_media() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE p jsonb; owner_id bigint; oid bigint;
        BEGIN
            IF TG_TABLE_NAME='orders' THEN
                FOR p IN SELECT value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(NEW.form_snapshot->'body_photo_file_ids')='array' THEN NEW.form_snapshot->'body_photo_file_ids' ELSE '[]'::jsonb END) LOOP
                    INSERT INTO client_files(user_id,order_id,source,source_id,file_id,filename,mime_type)
                    VALUES(NEW.user_id,NEW.id,'assessment',NEW.id,COALESCE(p->>'file_id',p#>>'{}'),'body-photo.jpg','image/jpeg') ON CONFLICT DO NOTHING;
                END LOOP;
            ELSIF TG_TABLE_NAME='users' THEN
                FOR p IN SELECT value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(NEW.body_photo_file_ids)='array' THEN NEW.body_photo_file_ids ELSE '[]'::jsonb END) LOOP
                    INSERT INTO client_files(user_id,source,source_id,file_id,filename,mime_type)
                    VALUES(NEW.id,'profile',NEW.id,COALESCE(p->>'file_id',p#>>'{}'),'body-photo.jpg','image/jpeg') ON CONFLICT DO NOTHING;
                END LOOP;
            ELSIF TG_TABLE_NAME IN ('record_revisions','user_profile_history') THEN
                FOR p IN SELECT value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(NEW.snapshot->'body_photo_file_ids')='array' THEN NEW.snapshot->'body_photo_file_ids' ELSE '[]'::jsonb END) LOOP
                    INSERT INTO client_files(user_id,order_id,source,source_id,file_id,filename,mime_type)
                    VALUES(NEW.user_id,NEW.order_id,TG_TABLE_NAME,NEW.id,COALESCE(p->>'file_id',p#>>'{}'),'body-photo.jpg','image/jpeg') ON CONFLICT DO NOTHING;
                END LOOP;
            ELSIF TG_TABLE_NAME='support_messages' THEN
              IF NEW.file_id IS NOT NULL THEN
                INSERT INTO client_files(user_id,source,source_id,file_id,filename,mime_type,byte_size)
                VALUES(NEW.user_id,'chat',NEW.id,NEW.file_id,COALESCE(NEW.file_name,CASE WHEN NEW.content_type='photo' THEN 'photo.jpg' ELSE 'attachment' END),NEW.mime_type,NEW.file_size) ON CONFLICT DO NOTHING;
              END IF;
            ELSIF TG_TABLE_NAME='order_info_items' THEN
              IF NEW.file_id IS NOT NULL THEN
                SELECT o.user_id,o.id INTO owner_id,oid FROM orders o JOIN order_info_requests r ON r.order_id=o.id WHERE r.id=NEW.request_id;
                INSERT INTO client_files(user_id,order_id,source,source_id,file_id,filename,mime_type,byte_size)
                VALUES(owner_id,oid,'information',NEW.id,NEW.file_id,COALESCE(NEW.file_name,CASE WHEN NEW.content_type='photo' THEN 'photo.jpg' ELSE 'attachment' END),NEW.mime_type,NEW.file_size) ON CONFLICT DO NOTHING;
              END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER index_order_media AFTER INSERT OR UPDATE OF form_snapshot ON orders FOR EACH ROW EXECUTE FUNCTION index_client_media();
        CREATE TRIGGER index_chat_media AFTER INSERT ON support_messages FOR EACH ROW EXECUTE FUNCTION index_client_media();
        CREATE TRIGGER index_info_media AFTER INSERT ON order_info_items FOR EACH ROW EXECUTE FUNCTION index_client_media();
        CREATE TRIGGER index_profile_media AFTER INSERT OR UPDATE OF body_photo_file_ids ON users FOR EACH ROW EXECUTE FUNCTION index_client_media();
        CREATE TRIGGER index_revision_media AFTER INSERT ON record_revisions FOR EACH ROW EXECUTE FUNCTION index_client_media();
        CREATE TRIGGER index_history_media AFTER INSERT ON user_profile_history FOR EACH ROW EXECUTE FUNCTION index_client_media();
        CREATE FUNCTION index_delivery_media() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.kind='file' THEN
                INSERT INTO client_files(user_id,order_id,source,source_id,asset_id,filename,storage_key,byte_size,status,file_id)
                SELECT o.user_id,o.id,'delivery',NEW.id,a.id,a.filename,a.storage_key,a.byte_size,
                    CASE WHEN a.storage_key IS NOT NULL THEN 'archived' ELSE 'pending' END,a.file_id
                FROM orders o JOIN product_assets a ON a.id=NEW.asset_id WHERE o.id=NEW.order_id;
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER index_delivery_media AFTER INSERT ON manual_delivery_items FOR EACH ROW EXECUTE FUNCTION index_delivery_media();
        CREATE FUNCTION index_content_media() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO client_files(user_id,order_id,source,source_id,asset_id,filename,storage_key,byte_size,status,file_id)
            SELECT o.user_id,o.id,'content',o.id,a.id,a.filename,a.storage_key,a.byte_size,
                CASE WHEN a.storage_key IS NOT NULL THEN 'archived' ELSE 'pending' END,NEW.file_id
            FROM orders o JOIN product_assets a ON a.id=NEW.asset_id WHERE o.id=NEW.order_id
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END $$;
        CREATE TRIGGER index_content_media AFTER INSERT ON order_content_delivery FOR EACH ROW EXECUTE FUNCTION index_content_media();
        UPDATE products SET form_fields=form_fields || '["measurements"]'::jsonb, version=version+1
        WHERE delivery_mode='manual' AND form_fields ? 'body_photo' AND NOT form_fields ? 'measurements';
        UPDATE products SET form_fields='["gender"]'::jsonb || form_fields, version=version+1
        WHERE form_fields ? 'body_photo' AND NOT form_fields ? 'gender';
    """)


def downgrade():
    raise RuntimeError('Client records contain history; restore a verified backup instead of discarding them.')
