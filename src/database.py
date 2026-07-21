from sqlalchemy import text
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
        # Development databases created before the catalog model was introduced
        # can still contain the legacy fragrance-only products table.  `create_all`
        # intentionally does not alter existing tables, so add the new nullable
        # columns idempotently before the first catalog write.
        legacy_columns = {
            "user_id": "UUID",
            "category_id": "UUID",
            "description": "TEXT",
            "selling_points": "JSONB NOT NULL DEFAULT '[]'::jsonb",
            "main_image_source": "VARCHAR(20)",
            "attributes": "JSONB NOT NULL DEFAULT '{}'::jsonb",
            "category_template_version": "INTEGER NOT NULL DEFAULT 1",
            "main_image_asset_id": "UUID REFERENCES media_assets(id) ON DELETE SET NULL",
        }
        for column, definition in legacy_columns.items():
            await connection.execute(text(
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS "
                f"{column} {definition}"
            ))
        legacy_task_columns = {
            "user_id": "UUID",
            "product_snapshot": "JSONB NOT NULL DEFAULT '{}'::jsonb",
        }
        for column, definition in legacy_task_columns.items():
            await connection.execute(text(
                "ALTER TABLE video_tasks ADD COLUMN IF NOT EXISTS "
                f"{column} {definition}"
            ))
        await connection.execute(text(
            "ALTER TABLE video_tasks ADD COLUMN IF NOT EXISTS "
            "result_video_asset_id UUID REFERENCES media_assets(id) ON DELETE SET NULL"
        ))
        await connection.execute(text(
            "ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS "
            "model_resolution_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb"
        ))
        await connection.execute(text(
            "ALTER TABLE stage_model_selections ADD COLUMN IF NOT EXISTS "
            "availability_status VARCHAR(30) NOT NULL DEFAULT 'available'"
        ))
        # Existing development databases predate the explicit video and final
        # composition review boundaries.  Replace the old status check so a
        # worker can persist those review states instead of failing after video
        # generation has already completed.
        await connection.execute(text(
            "ALTER TABLE video_tasks DROP CONSTRAINT IF EXISTS video_tasks_status_check"
        ))
        await connection.execute(text(
            "ALTER TABLE video_tasks ADD CONSTRAINT video_tasks_status_check "
            "CHECK (status IN ('pending', 'planning', 'creative_brief_review', 'shot_plan_review', 'scripting', 'script_review', 'imaging', "
            "'image_review', 'character_review', 'video_gen', 'video_review', "
            "'compositing', 'composition_review', 'cancellation_requested', 'cancelled', 'done', 'failed'))"
        ))
        await connection.execute(text(
            "ALTER TABLE generated_images ADD COLUMN IF NOT EXISTS "
            "asset_id UUID REFERENCES media_assets(id) ON DELETE SET NULL"
        ))
        await connection.execute(text(
            "ALTER TABLE generated_images ADD COLUMN IF NOT EXISTS "
            "generation_context JSONB NOT NULL DEFAULT '{}'::jsonb"
        ))
        await connection.execute(text(
            "ALTER TABLE video_candidates ADD COLUMN IF NOT EXISTS "
            "generation_context JSONB NOT NULL DEFAULT '{}'::jsonb"
        ))
        await connection.execute(text(
            "ALTER TABLE main_image_candidates ADD COLUMN IF NOT EXISTS "
            "asset_id UUID REFERENCES media_assets(id) ON DELETE SET NULL"
        ))
        for column in ("auto_approve_script", "auto_approve_images"):
            await connection.execute(text(
                f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} BOOLEAN NOT NULL DEFAULT FALSE"
            ))


async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
