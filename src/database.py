from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from src.config import settings
from src.models.base import Base
from src import models  # noqa: F401 - register all model metadata before create_all

# Celery runs async task bodies through asyncio.run(), which creates a new
# event loop per invocation. asyncpg connections are loop-bound, so a shared
# pooled connection can otherwise be reused by a later task on another loop.
engine = create_async_engine(
    settings.database_url,
    echo=(settings.app_env == "development"),
    poolclass=NullPool,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ensure_model_configuration_compatibility(connection) -> None:
    """Upgrade the unreleased development schema without losing local data.

    `create_all()` adds tables only; it cannot add the copied runtime fields
    introduced when template rows stopped being live model configurations.
    """
    columns = {
        "adapter": "VARCHAR(80) NOT NULL DEFAULT 'openai'",
        "api_base": "VARCHAR(1000)",
        "model_id": "VARCHAR(255)",
        "display_name": "VARCHAR(255)",
        "capabilities": "JSONB NOT NULL DEFAULT '[]'::jsonb",
        "constraints": "JSONB NOT NULL DEFAULT '{}'::jsonb",
        "revision": "INTEGER NOT NULL DEFAULT 1",
    }
    for column, definition in columns.items():
        await connection.execute(text(
            "ALTER TABLE model_configurations ADD COLUMN IF NOT EXISTS "
            f"{column} {definition}"
        ))
    await connection.execute(text(
        "ALTER TABLE model_configurations ALTER COLUMN catalog_model_id DROP NOT NULL"
    ))
    # Older pre-release tables required either a platform default or a
    # ciphertext. Private endpoints may now use their own unauthenticated or
    # network-level authentication, so remove only that legacy credential check.
    await connection.execute(text("""
        DO $$
        DECLARE legacy_constraint text;
        BEGIN
            SELECT conname INTO legacy_constraint
            FROM pg_constraint
            WHERE conrelid = 'model_configurations'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) LIKE '%credential_ciphertext%';
            IF legacy_constraint IS NOT NULL THEN
                EXECUTE format('ALTER TABLE model_configurations DROP CONSTRAINT %I', legacy_constraint);
            END IF;
        END $$;
    """))


async def ensure_schema() -> None:
    """Create tables missing from an existing development database.

    This is intentionally idempotent. It closes the gap where new model
    tables (such as the catalog tables) are added after a database was first
    initialized from an older schema. Destructive or altering migrations
    still belong in an explicit migration system.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await ensure_model_configuration_compatibility(connection)
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
            "voiceover_review_enabled": "BOOLEAN NOT NULL DEFAULT FALSE",
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
            "'image_review', 'character_review', 'video_gen', 'video_review', 'voice_review', 'editing_blueprint_review', "
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
        # Composition Source Snapshots are task-owned HTML Media Assets. Older
        # development databases have a category check that predates them.
        await connection.execute(text(
            "ALTER TABLE media_assets DROP CONSTRAINT IF EXISTS media_assets_category_check"
        ))
        await connection.execute(text(
            "ALTER TABLE media_assets ADD CONSTRAINT media_assets_category_check "
            "CHECK (category IN ('product_image', 'source_video', 'generated_image', 'video_clip', "
            "'tts_audio', 'lipsync_video', 'character_image', 'final_video', 'composition_source'))"
        ))
        await connection.execute(text(
            "ALTER TABLE video_candidates ADD COLUMN IF NOT EXISTS "
            "generation_context JSONB NOT NULL DEFAULT '{}'::jsonb"
        ))
        await connection.execute(text(
            "ALTER TABLE video_candidates ADD COLUMN IF NOT EXISTS "
            "recomposed_from_candidate_id UUID REFERENCES video_candidates(id) ON DELETE SET NULL"
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
