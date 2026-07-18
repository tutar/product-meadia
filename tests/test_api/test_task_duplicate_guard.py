from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.api.tasks import ACTIVE_TASK_STATUSES, blocks_new_task


def test_duplicate_guard_covers_every_active_task_status():
    assert set(ACTIVE_TASK_STATUSES) == {
        "pending", "planning", "creative_brief_review", "shot_plan_review", "scripting", "script_review", "imaging",
        "image_review", "character_review", "video_gen", "video_review", "compositing", "composition_review", "cancellation_requested",
    }
    assert "done" not in ACTIVE_TASK_STATUSES
    assert "failed" not in ACTIVE_TASK_STATUSES


def test_task_create_endpoint_enqueues_video_work():
    from pathlib import Path

    source = Path("src/api/tasks.py").read_text()
    create_section = source[source.index("async def create_task"):source.index("@router.get(\"\")")]
    assert "run_video_task.delay(str(task.id))" in create_section
    assert "task.celery_task_id = celery_result.id" in create_section


def test_stale_active_task_does_not_block_a_new_task():
    stale = SimpleNamespace(status="imaging", updated_at=datetime.now(timezone.utc) - timedelta(hours=16))
    current = SimpleNamespace(status="imaging", updated_at=datetime.now(timezone.utc))

    assert not blocks_new_task(stale)
    assert blocks_new_task(current)
