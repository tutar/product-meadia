from datetime import datetime, timedelta, timezone


ACTIVE_STATUSES = {"pending", "scripting", "imaging", "video_gen", "compositing"}
TASK_LEASE = timedelta(minutes=15)


def is_stale_task(
    status: str,
    updated_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    if status not in ACTIVE_STATUSES or updated_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return now - updated_at > TASK_LEASE
