from alembic import op
import sqlalchemy as sa

revision='0001_initial'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.execute(open('app/db/schema.sql', encoding='utf-8').read())
    op.execute("""
      INSERT INTO products(code,title,description,price_irr,sort_order) VALUES
      ('nutrition','🥗 برنامه تغذیه','برنامه غذایی متناسب با اطلاعات شما',399000,1),
      ('training','🏋️ برنامه تمرینی','برنامه تمرینی متناسب با هدف و سابقه تمرین شما',499000,2),
      ('complete','🔥 برنامه غذایی + تمرینی','برنامه کامل تغذیه و تمرین',799000,3)
      ON CONFLICT (code) DO NOTHING
    """)

def downgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nutrition_training_days SMALLINT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS workout_days SMALLINT")
    op.execute('DROP TABLE IF EXISTS orders CASCADE')
    op.execute('DROP TABLE IF EXISTS products CASCADE')
    op.execute('DROP TABLE IF EXISTS users CASCADE')
