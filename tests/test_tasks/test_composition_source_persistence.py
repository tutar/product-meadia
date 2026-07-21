from contextlib import asynccontextmanager

import pytest

from src.models.composition_source import CompositionSourceSnapshot
from src.models.media_asset import MediaAsset
from src.models.task import VideoTask
from src.models.user import User
from src.models.video_candidate import VideoCandidate
from src.media.storage import memory_storage


@pytest.mark.asyncio
async def test_snapshot_is_persisted_before_the_render_node_can_run(db_session, monkeypatch):
    from src.tasks import video_tasks

    owner = User(email="capture@composition-source.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task]); await db_session.flush()
    clip = MediaAsset(owner_user_id=owner.id, task_id=task.id, category="video_clip", bucket="media", object_key="clip", content_type="video/mp4", size_bytes=1, checksum="a" * 64)
    audio = MediaAsset(owner_user_id=owner.id, task_id=task.id, category="tts_audio", bucket="media", object_key="audio", content_type="audio/wav", size_bytes=1, checksum="b" * 64)
    db_session.add_all([clip, audio]); await db_session.flush()
    db_session.add(VideoCandidate(task_id=task.id, asset_id=clip.id, kind="clip", sort_order=0, version=1)); await db_session.commit()

    @asynccontextmanager
    async def session_factory():
        yield db_session
    monkeypatch.setattr(video_tasks, "SessionLocal", lambda: session_factory())
    storage = memory_storage()
    monkeypatch.setattr(video_tasks, "create_rustfs_storage", lambda _: storage)

    output = {"hyperframes_html": '<audio src="https://audio"></audio><video src="https://clip"></video>', "editing_blueprint": []}
    await video_tasks._persist_node_output(str(task.id), "composite_video", output)

    snapshot = await db_session.get(CompositionSourceSnapshot, output["composition_source_snapshot_id"])
    await db_session.refresh(snapshot, ["asset"])
    assert snapshot.candidate_id is None
    persisted = (await storage.download(snapshot.asset.bucket, snapshot.asset.object_key)).decode()
    assert "https://" not in persisted
    assert f"asset://{clip.id}" in persisted
    assert f"asset://{audio.id}" in persisted
