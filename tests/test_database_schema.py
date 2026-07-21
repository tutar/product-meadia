import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_ensure_schema_adds_legacy_product_columns(monkeypatch):
    import src.database as database

    statements = []

    class Connection:
        async def run_sync(self, callback):
            return None

        async def execute(self, statement):
            statements.append(str(statement))

    class Begin:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *args):
            return None

    class Engine:
        def begin(self):
            return Begin()

    monkeypatch.setattr(database, "engine", Engine())
    await database.ensure_schema()

    assert any("ADD COLUMN IF NOT EXISTS user_id UUID" in statement for statement in statements)
    assert any("ADD COLUMN IF NOT EXISTS category_id UUID" in statement for statement in statements)
    assert any("ADD COLUMN IF NOT EXISTS main_image_source VARCHAR(20)" in statement for statement in statements)
    assert any("ALTER TABLE video_tasks ADD COLUMN IF NOT EXISTS user_id UUID" in statement for statement in statements)
    assert any("ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS model_resolution_snapshot" in statement for statement in statements)
    assert any("ALTER TABLE stage_model_selections ADD COLUMN IF NOT EXISTS availability_status" in statement for statement in statements)
    assert any("ALTER TABLE video_tasks ADD COLUMN IF NOT EXISTS product_snapshot JSONB" in statement for statement in statements)
    assert any("ALTER TABLE video_tasks DROP CONSTRAINT IF EXISTS video_tasks_status_check" in statement for statement in statements)
    assert any("video_review" in statement and "composition_review" in statement for statement in statements)
    assert any("composition_source" in statement for statement in statements)
