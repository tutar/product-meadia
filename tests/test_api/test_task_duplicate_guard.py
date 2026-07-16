from src.api.tasks import ACTIVE_TASK_STATUSES


def test_duplicate_guard_covers_every_active_task_status():
    assert set(ACTIVE_TASK_STATUSES) == {
        "pending", "scripting", "script_review", "imaging",
        "image_review", "video_gen", "compositing",
    }
    assert "done" not in ACTIVE_TASK_STATUSES
    assert "failed" not in ACTIVE_TASK_STATUSES


def test_task_create_endpoint_enqueues_video_work():
    from pathlib import Path

    source = Path("src/api/tasks.py").read_text()
    create_section = source[source.index("async def create_task"):source.index("@router.get(\"\")")]
    assert "run_video_task.delay(str(task.id))" in create_section
    assert "task.celery_task_id = celery_result.id" in create_section
