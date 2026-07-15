import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from src.config import settings

_saver: PostgresSaver | None = None


def get_checkpointer_sync() -> PostgresSaver:
    global _saver
    if _saver is None:
        conninfo = settings.database_url.replace("+asyncpg", "")
        conn = psycopg.connect(conninfo, autocommit=True)
        _saver = PostgresSaver(conn=conn)
        _saver.setup()
    return _saver


async def get_checkpointer() -> PostgresSaver:
    return get_checkpointer_sync()


def close_checkpointer():
    global _saver
    _saver = None
