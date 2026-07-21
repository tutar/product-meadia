import pytest

from src.api.tasks import get_composition_source
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
