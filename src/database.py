from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from src.models.base import Base
from src import models  # noqa: F401 - register all model metadata before create_all

engine = create_async_engine(settings.database_url, echo=(settings.app_env == "development"))
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ensure_schema() -> None:
    """Create tables missing from an existing development database.

    This is intentionally idempotent. It closes the gap where new model
    tables (such as the catalog tables) are added after a database was first
    initialized from an older schema. Destructive or altering migrations
    still belong in an explicit migration system.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
