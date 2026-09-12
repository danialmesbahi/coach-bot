from alembic import context
from sqlalchemy import create_engine
from app.config import get_settings

config = context.config


def database_url():
    url = get_settings().database_url
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    return url


def run_migrations_offline():
    context.configure(url=database_url(),target_metadata=None,literal_binds=True,dialect_opts={'paramstyle':'named'})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    url = database_url()
    connectable = create_engine(url, pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
