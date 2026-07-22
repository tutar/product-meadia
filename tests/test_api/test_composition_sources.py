import pytest
from unittest.mock import AsyncMock

from src.api.tasks import download_composition_source, get_composition_source, list_video_candidates, replay_composition_source, reconstruct_composition_source
from src.media.storage import memory_storage
from src.services.media_service import MediaService
from src.models.media_asset import MediaAsset
from src.models.editing_blueprint import EditingBlueprint
from src.models.composition_source import CompositionSourceSnapshot
from src.models.task import VideoTask
from src.models.user import User
from src.models.video_candidate import VideoCandidate


@pytest.mark.asyncio
async def test_task_owner_reads_a_candidate_composition_source_without_access_urls(db_session):
    owner = User(email="owner@composition-source.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task])
    await db_session.flush()
    candidate = VideoCandidate(
        task_id=task.id,
        kind="composition",
        sort_order=0,
        version=1,
        status="pending_review",
    )
    db_session.add(candidate)
    await db_session.flush()
    snapshot = CompositionSourceSnapshot(
        task_id=task.id,
        candidate_id=candidate.id,
        source_kind="captured",
        canonical_html_checksum="2a" * 32,
        input_asset_ids=["11111111-1111-1111-1111-111111111111"],
        render_spec={"hyperframes_version": "0.7.59", "fps": 30},
        provenance={"template_hash": "abc123"},
    )
    db_session.add(snapshot)
    await db_session.commit()

    source = await get_composition_source(task.id, candidate.id, db=db_session, user=owner)

    assert source.id == snapshot.id
    assert source.source_kind == "captured"
    assert source.input_asset_ids == ["11111111-1111-1111-1111-111111111111"]
    assert source.render_spec == {"hyperframes_version": "0.7.59", "fps": 30}
    assert "access_url" not in source.model_fields_set


@pytest.mark.asyncio
async def test_non_owner_cannot_read_a_candidate_composition_source(db_session):
    owner = User(email="owner-private@composition-source.test", hashed_password="x")
    outsider = User(email="outsider@composition-source.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, outsider, task])
    await db_session.flush()
    candidate = VideoCandidate(task_id=task.id, kind="composition", sort_order=0, version=1)
    db_session.add(candidate)
    await db_session.flush()
    db_session.add(CompositionSourceSnapshot(task_id=task.id, candidate_id=candidate.id, source_kind="captured", canonical_html_checksum="2a" * 32, input_asset_ids=[], render_spec={}, provenance={}))
    await db_session.commit()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await get_composition_source(task.id, candidate.id, db=db_session, user=outsider)

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_owner_downloads_composition_source_as_html_attachment(db_session):
    owner = User(email="download@composition-source.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task])
    await db_session.flush()
    candidate = VideoCandidate(task_id=task.id, kind="composition", sort_order=0, version=1)
    db_session.add(candidate)
    await db_session.flush()
    storage = memory_storage()
    media = MediaService(db_session, storage, bucket="media")
    asset = await media.create_asset(
        owner_user_id=owner.id,
        category="composition_source",
        data=b"<div>composition source</div>",
        content_type="text/html; charset=utf-8",
        filename="composition-source.html",
        task_id=task.id,
    )
    db_session.add(CompositionSourceSnapshot(
        task_id=task.id,
        candidate_id=candidate.id,
        asset_id=asset.id,
        source_kind="captured",
        canonical_html_checksum="2a" * 32,
        input_asset_ids=[],
        render_spec={},
        provenance={},
    ))
    await db_session.commit()

    response = await download_composition_source(task.id, candidate.id, db=db_session, user=owner, media=media)

    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="composition-source.html"'
    assert response.body == b"<div>composition source</div>"


@pytest.mark.asyncio
async def test_video_candidate_list_reports_whether_a_composition_source_is_retained(db_session):
    owner = User(email="source-availability@composition-source.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task])
    await db_session.flush()
    storage = memory_storage()
    media = MediaService(db_session, storage, bucket="media")
    legacy_asset = await media.create_asset(owner_user_id=owner.id, category="final_video", data=b"legacy", content_type="video/mp4", filename="legacy.mp4", task_id=task.id)
    captured_asset = await media.create_asset(owner_user_id=owner.id, category="final_video", data=b"captured", content_type="video/mp4", filename="captured.mp4", task_id=task.id)
    source_asset = await media.create_asset(owner_user_id=owner.id, category="composition_source", data=b"<div />", content_type="text/html", filename="source.html", task_id=task.id)
    legacy = VideoCandidate(task_id=task.id, asset_id=legacy_asset.id, kind="composition", sort_order=0, version=1)
    captured = VideoCandidate(task_id=task.id, asset_id=captured_asset.id, kind="composition", sort_order=0, version=2)
    db_session.add_all([legacy, captured])
    await db_session.flush()
    db_session.add(CompositionSourceSnapshot(task_id=task.id, candidate_id=captured.id, asset_id=source_asset.id, source_kind="captured", canonical_html_checksum="2a" * 32, input_asset_ids=[], render_spec={}, provenance={}))
    await db_session.commit()

    candidates = await list_video_candidates(task.id, db=db_session, user=owner, media=media)

    availability = {str(candidate["id"]): candidate["has_composition_source"] for candidate in candidates}
    assert availability == {str(legacy.id): False, str(captured.id): True}


@pytest.mark.asyncio
async def test_replay_creates_a_new_candidate_and_keeps_its_source(tmp_path, db_session, monkeypatch):
    owner = User(email="replay@composition-source.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task]); await db_session.flush()
    original = VideoCandidate(task_id=task.id, kind="composition", sort_order=0, version=1, status="pending_review")
    db_session.add(original); await db_session.flush()
    storage = memory_storage(); media = MediaService(db_session, storage, bucket="media")
    source_asset = await media.create_asset(owner_user_id=owner.id, category="composition_source", data=b'<div data-composition-id="x"></div>', content_type="text/html", filename="source.html", task_id=task.id)
    snapshot = CompositionSourceSnapshot(task_id=task.id, candidate_id=original.id, asset_id=source_asset.id, source_kind="captured", canonical_html_checksum="2a" * 32, input_asset_ids=[], render_spec={}, provenance={})
    db_session.add(snapshot); await db_session.commit()
    rendered = tmp_path / "rendered.mp4"; rendered.write_bytes(b"mp4")
    monkeypatch.setattr("src.api.tasks.render_hyperframes", AsyncMock(return_value=str(rendered)))

    replay = await replay_composition_source(task.id, original.id, db=db_session, user=owner, media=media)

    assert replay.version == 2
    assert original.is_current is False
    current = await db_session.get(VideoCandidate, replay.id)
    assert current.recomposed_from_candidate_id == original.id


@pytest.mark.asyncio
async def test_reconstruction_is_explicitly_marked_and_records_inferred_inputs(db_session):
    owner = User(email="legacy@composition-source.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task]); await db_session.flush()
    legacy = VideoCandidate(task_id=task.id, kind="composition", sort_order=0, version=1)
    db_session.add(legacy)
    storage = memory_storage(); media = MediaService(db_session, storage, bucket="media")
    clip_asset = await media.create_asset(owner_user_id=owner.id, category="video_clip", data=b"clip", content_type="video/mp4", filename="clip.mp4", task_id=task.id)
    audio_asset = await media.create_asset(owner_user_id=owner.id, category="tts_audio", data=b"audio", content_type="audio/wav", filename="voice.wav", task_id=task.id)
    db_session.add_all([VideoCandidate(task_id=task.id, asset_id=clip_asset.id, kind="clip", sort_order=0, version=1), EditingBlueprint(task_id=task.id, entries=[{"start_seconds": 0, "duration_seconds": 5}])])
    await db_session.commit()

    source = await reconstruct_composition_source(task.id, legacy.id, db=db_session, user=owner, media=media)

    assert source.source_kind == "reconstructed"
    assert "current retained clip candidates" in source.reconstruction_notes
    assert source.provenance["input_selection"] == "current_candidates"
