from unittest.mock import Mock

import pytest

from src.api.tasks import review_voiceover_candidate
from src.models.task import VideoTask
from src.models.user import User
from src.models.voiceover_candidate import VoiceoverCandidate
from src.schemas.task import VoiceoverReview


@pytest.mark.asyncio
async def test_voiceover_approval_advances_only_to_composition(db_session, monkeypatch):
    owner = User(email="voice-review-action@example.test", hashed_password="x")
    task = VideoTask(
        user=owner, product_snapshot={}, type="promo", image_count=1,
        status="voice_review", voiceover_review_enabled=True,
    )
    candidate = VoiceoverCandidate(
        task=task, narration_text="Approved narration", duration_seconds=2.0,
        status="pending_review", is_current=True,
    )
    db_session.add_all([owner, task, candidate])
    await db_session.commit()

    from src.tasks import video_tasks
    monkeypatch.setattr(video_tasks.run_video_task, "delay", Mock())

    response = await review_voiceover_candidate(
        task.id, candidate.id, VoiceoverReview(action="approve"), db=db_session, user=owner,
    )

    await db_session.refresh(task)
    await db_session.refresh(candidate)
    assert response == {"status": "queued"}
    assert candidate.status == "approved"
    assert task.status == "compositing"
    video_tasks.run_video_task.delay.assert_called_once_with(str(task.id))
