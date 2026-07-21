import pytest

from src.api.tasks import export_generation_records, list_generation_records
from src.models.generation_record import GenerationRecord
from src.models.task import VideoTask
from src.models.user import User
from src.schemas.task import GenerationRecordExportRequest


@pytest.mark.asyncio
async def test_task_owner_reads_latest_generation_material_without_sensitive_payload_data(db_session):
    owner = User(email="owner@generation-record.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task])
    await db_session.flush()
    db_session.add_all([
        GenerationRecord(
            task_id=task.id, stage="planning", substep="generate_creative_brief", attempt=1,
            provider="litellm", model="scriptwriter", parameters={"temperature": 0.4},
            normalized_input={"user": "Product: Cedar candle"},
            normalized_output={"creative_brief": {"core_promise": "Quiet focus"}},
            provider_payload={"messages": [{"role": "user", "content": "Product: Cedar candle"}]},
            provenance={"workflow_commit": "abc123"},
            model_resolution_snapshot={"provider": "openai", "model_id": "gpt-4.1-mini", "selection_version": 1},
        ),
        GenerationRecord(
            task_id=task.id, stage="planning", substep="generate_creative_brief", attempt=2,
            provider="litellm", model="scriptwriter", parameters={"temperature": 0.4},
            normalized_input={"user": "Product: Cedar candle, softer"},
            normalized_output={"creative_brief": {"core_promise": "Slow ritual"}},
            provider_payload={"messages": [{"role": "user", "content": "Product: Cedar candle, softer"}], "authorization": "redacted"},
            provenance={"workflow_commit": "def456"},
        ),
    ])
    await db_session.commit()

    records = await list_generation_records(task.id, db=db_session, user=owner)

    assert [record.attempt for record in records] == [2, 1]
    assert records[0].normalized_output == {"creative_brief": {"core_promise": "Slow ritual"}}
    assert records[0].provider_payload == {"messages": [{"role": "user", "content": "Product: Cedar candle, softer"}]}
    assert records[1].model_resolution_snapshot == {"provider": "openai", "model_id": "gpt-4.1-mini", "selection_version": 1}


@pytest.mark.asyncio
async def test_generation_material_is_not_visible_to_another_task_owner(db_session):
    owner = User(email="owner-private@generation-record.test", hashed_password="x")
    outsider = User(email="outsider@generation-record.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, outsider, task])
    await db_session.commit()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await list_generation_records(task.id, db=db_session, user=outsider)

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_owner_explicitly_exports_only_approved_training_candidates(db_session):
    owner = User(email="export@generation-record.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task])
    await db_session.flush()
    approved = GenerationRecord(task_id=task.id, stage="scripting", substep="generate_script", attempt=1, provider="litellm", model="scriptwriter", parameters={}, normalized_input={}, normalized_output={"script": "Approved"}, provider_payload={}, provenance={}, training_candidate="approved")
    negative = GenerationRecord(task_id=task.id, stage="scripting", substep="generate_script", attempt=2, provider="litellm", model="scriptwriter", parameters={}, normalized_input={}, normalized_output={"script": "Rejected"}, provider_payload={}, provenance={}, training_candidate="negative")
    db_session.add_all([approved, negative])
    await db_session.commit()

    exported = await export_generation_records(task.id, GenerationRecordExportRequest(record_ids=[approved.id, negative.id]), db=db_session, user=owner)

    assert [record.id for record in exported] == [approved.id]
