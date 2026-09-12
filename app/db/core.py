import asyncpg
from app.config import get_settings

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        settings = get_settings()
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            command_timeout=10,
            max_inactive_connection_lifetime=120,
        )

    async def close(self):
        if self.pool:
            await self.pool.close()

    def acquire(self):
        if not self.pool:
            raise RuntimeError("Database is not connected")
        return self.pool.acquire()

db = Database(get_settings().database_url)
