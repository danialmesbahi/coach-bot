"""Separate explicit staff corrections from automatic profile refreshes."""
from alembic import op

revision = '0026_record_edit_origin'
down_revision = '0025_client_records'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE record_revisions ADD COLUMN origin text NOT NULL DEFAULT 'profile';
        UPDATE record_revisions r SET origin='staff' WHERE EXISTS (
            SELECT 1 FROM audit_logs a WHERE a.action='record_updated'
            AND a.created_at=r.created_at AND
            ((r.order_id IS NOT NULL AND a.target_type='order' AND a.target_id=r.order_id)
             OR (r.order_id IS NULL AND a.target_type='customer' AND a.target_id=r.user_id)));
        CREATE INDEX record_revisions_staff ON record_revisions(user_id,id DESC) WHERE origin='staff';
        CREATE OR REPLACE FUNCTION preserve_client_record() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE source text := CASE WHEN current_setting('app.record_edit',true)='staff' THEN 'staff' ELSE 'profile' END;
        BEGIN
            IF TG_TABLE_NAME='orders' THEN
                IF OLD.form_snapshot IS DISTINCT FROM NEW.form_snapshot THEN
                    INSERT INTO record_revisions(user_id,order_id,snapshot,origin) VALUES(OLD.user_id,OLD.id,OLD.form_snapshot,source);
                END IF;
            ELSIF (to_jsonb(OLD)-'updated_at') IS DISTINCT FROM (to_jsonb(NEW)-'updated_at') THEN
                INSERT INTO record_revisions(user_id,snapshot,origin) VALUES(OLD.id,to_jsonb(OLD),source);
            END IF;
            RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION index_client_media() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE p jsonb; owner_id bigint; oid bigint; photos jsonb; src text; sid bigint;
        BEGIN
            IF TG_TABLE_NAME='orders' THEN
                owner_id:=NEW.user_id; oid:=NEW.id; sid:=NEW.id; src:='assessment'; photos:=NEW.form_snapshot->'body_photo_file_ids';
            ELSIF TG_TABLE_NAME='users' THEN
                owner_id:=NEW.id; sid:=NEW.id; src:='profile'; photos:=NEW.body_photo_file_ids;
            ELSIF TG_TABLE_NAME IN ('record_revisions','user_profile_history') THEN
                owner_id:=NEW.user_id; oid:=NEW.order_id; sid:=NEW.id; src:=TG_TABLE_NAME; photos:=NEW.snapshot->'body_photo_file_ids';
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
            FOR p IN SELECT value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(photos)='array' THEN photos ELSE '[]'::jsonb END) LOOP
                IF p ? 'client_file_id' THEN CONTINUE; END IF;
                IF jsonb_typeof(p)='object' AND p->>'file_id' IS NULL THEN CONTINUE; END IF;
                INSERT INTO client_files(user_id,order_id,source,source_id,file_id,filename,mime_type)
                VALUES(owner_id,oid,src,sid,COALESCE(p->>'file_id',p#>>'{}'),'body-photo.jpg','image/jpeg') ON CONFLICT DO NOTHING;
            END LOOP;
            RETURN NEW;
        END $$;
    """)


def downgrade():
    raise RuntimeError('Restore a verified backup to preserve revision provenance.')
