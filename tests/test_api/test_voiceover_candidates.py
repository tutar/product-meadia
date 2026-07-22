import pytest

from src.api.tasks import list_voiceover_candidates
from src.media.storage import memory_storage
from src.models.media_asset import MediaAsset
from src.models.task import VideoTask
from src.models.user import User
from src.models.voiceover_candidate import VoiceoverCandidate
from src.services.media_service import MediaService


@pytest.mark.asyncio
async def test_task_owner_lists_current_voiceover_candidate_with_audio_access(db_session):
    owner = User(email="voiceowner@example.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task])
    await db_session.flush()
    media = MediaService(db_session, memory_storage(), bucket="media")
    asset = await media.create_asset(
        owner_user_id=owner.id,
        category="tts_audio",
        data=b"voice",
        content_type="audio/wav",
        filename="voice.wav",
        task_id=task.id,
    )
    candidate = VoiceoverCandidate(
        task_id=task.id,
        asset_id=asset.id,
        narration_text="A concise narration.",
        duration_seconds=2.5,
        version=1,
        status="pending_review",
        is_current=True,
    )
    db_session.add(candidate)
    await db_session.commit()

    candidates = await list_voiceover_candidates(task.id, db=db_session, user=owner, media=media)

    assert candidates == [{
        "id": candidate.id,
        "task_id": task.id,
        "asset_id": asset.id,
        "access_url": "memory://media/" + asset.object_key + "?expires=3600",
        "narration_text": "A concise narration.",
        "duration_seconds": 2.5,
        "version": 1,
        "status": "pending_review",
        "is_current": True,
        "generation_context": {},
    }]
