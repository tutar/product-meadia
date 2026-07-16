from datetime import datetime, timedelta, timezone

from src.services.media_lifecycle import due_for_cleanup


def test_cleanup_only_selects_expired_superseded_assets():
    now = datetime.now(timezone.utc)
    assert due_for_cleanup("superseded", now - timedelta(seconds=1), now)
    assert not due_for_cleanup("available", now - timedelta(seconds=1), now)
    assert not due_for_cleanup("superseded", now + timedelta(seconds=1), now)
