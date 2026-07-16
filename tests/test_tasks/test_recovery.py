from datetime import datetime, timedelta, timezone

from src.tasks.recovery import is_stale_task


def test_active_task_becomes_recoverable_after_lease_expires():
    now = datetime.now(timezone.utc)
    assert is_stale_task(
        status="video_gen",
        updated_at=now - timedelta(minutes=16),
        now=now,
    )


def test_recent_active_task_is_not_stale():
    now = datetime.now(timezone.utc)
    assert not is_stale_task(
        status="video_gen",
        updated_at=now - timedelta(minutes=2),
        now=now,
    )


def test_terminal_and_review_tasks_are_never_stale():
    now = datetime.now(timezone.utc)
    for status in ("done", "failed", "script_review", "image_review"):
        assert not is_stale_task(
            status=status,
            updated_at=now - timedelta(hours=2),
            now=now,
        )
