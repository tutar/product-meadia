import asyncio
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from src.config import settings

_pool: AsyncConnectionPool | None = None
_saver: PostgresSaver | None = None


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        # Parse conninfo from database_url (postgresql+asyncpg:// -> postgresql://)
        conninfo = settings.database_url.replace("+asyncpg", "")
        _pool = AsyncConnectionPool(conninfo=conninfo, open=False)
        await _pool.open()
    return _pool


async def get_checkpointer() -> PostgresSaver:
    global _saver
    if _saver is None:
        pool = await get_pool()
        _saver = PostgresSaver(conn=pool)
        await _saver.setup()
    return _saver


async def close_checkpointer():
    global _pool, _saver
    if _pool:
        await _pool.close()
        _pool = None
    _saver = None
