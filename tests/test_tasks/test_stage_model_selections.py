import pytest
from uuid import uuid4
from sqlalchemy import select

from src.models.model_configuration import (
    ModelConfiguration, ProviderModelCatalog, StageModelDefault, StageModelSelection,
)
from src.models.task import VideoTask
from src.models.user import User


def test_explicit_regeneration_request_can_name_the_replacement_model_configuration():
    from src.schemas.task import RegenerateRequest

    replacement = uuid4()
    request = RegenerateRequest(feedback="Use a calmer camera move.", model_configuration_id=replacement)

    assert request.model_configuration_id == replacement


@pytest.mark.asyncio
async def test_task_freezes_its_compatible_user_default_and_keeps_a_non_secret_resolution_snapshot(db_session):
    from src.services.stage_model_selections import freeze_stage_model_selections

    owner = User(email="selection-owner@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(
        provider="openai", model_id="gpt-4.1-mini", display_name="GPT-4.1 mini",
        capabilities=["creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation"], constraints={"max_duration_seconds": 8, "max_keyframes": 2}, capability_revision=7,
    )
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(
        owner_user_id=owner.id, catalog_model_id=catalog.id,
        credential_ciphertext="encrypted-not-a-secret", verification_status="verified",
    )
    db_session.add(configuration)
    await db_session.flush()
    db_session.add_all([
        StageModelDefault(owner_user_id=owner.id, stage=stage, model_configuration_id=configuration.id)
        for stage in ("creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation")
    ])
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add(task)
    await db_session.flush()

    selections = await freeze_stage_model_selections(db_session, task, owner.id)
    await db_session.commit()

    stored = await db_session.scalar(select(StageModelSelection).where(
        StageModelSelection.task_id == task.id, StageModelSelection.stage == "creative_planning",
    ))
    assert [selection.stage for selection in selections] == ["creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation"]
    assert stored.model_configuration_id == configuration.id
    assert stored.resolution_snapshot == {
        "configuration_id": str(configuration.id), "selection_version": 1,
        "provider": "openai", "model_id": "gpt-4.1-mini",
        "capability_revision": 7, "constraints": {"max_duration_seconds": 8, "max_keyframes": 2},
        "uses_platform_default": False,
    }
    assert "encrypted-not-a-secret" not in str(stored.resolution_snapshot)


@pytest.mark.asyncio
async def test_user_can_replace_only_an_unstarted_frozen_stage_selection(db_session):
    from fastapi import HTTPException
    from src.services.stage_model_selections import replace_stage_model_selection

    owner = User(email="replace-selection@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(
        provider="openai", model_id="gpt-4.1", display_name="GPT-4.1",
        capabilities=["scriptwriting"], constraints={}, capability_revision=3,
    )
    db_session.add_all([owner, catalog])
    await db_session.flush()
    previous = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext="old", verification_status="verified")
    replacement = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext="new", verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([previous, replacement, task])
    await db_session.flush()
    selection = StageModelSelection(
        task_id=task.id, stage="scriptwriting", model_configuration_id=previous.id,
        resolution_snapshot={"configuration_id": str(previous.id)},
    )
    db_session.add(selection)
    await db_session.commit()

    updated = await replace_stage_model_selection(db_session, task, owner.id, "scriptwriting", replacement.id)
    assert updated.model_configuration_id == replacement.id
    assert updated.selection_version == 2
    assert updated.resolution_snapshot["configuration_id"] == str(replacement.id)

    updated.started_at = updated.created_at
    await db_session.commit()
    with pytest.raises(HTTPException, match="already started") as error:
        await replace_stage_model_selection(db_session, task, owner.id, "scriptwriting", previous.id)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_explicit_regeneration_can_replace_a_started_clip_selection(db_session):
    from src.services.stage_model_selections import replace_stage_model_selection

    owner = User(email="regenerate-selection@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="veo", display_name="Veo", capabilities=["clip_video"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    previous = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext="old", verification_status="verified")
    replacement = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext="new", verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([previous, replacement, task])
    await db_session.flush()
    selection = StageModelSelection(task_id=task.id, stage="clip_video", model_configuration_id=previous.id, resolution_snapshot={"model_id": "veo"}, started_at=task.created_at)
    db_session.add(selection)
    await db_session.commit()

    updated = await replace_stage_model_selection(
        db_session, task, owner.id, "clip_video", replacement.id, explicit_regeneration=True,
    )

    assert updated.model_configuration_id == replacement.id
    assert updated.selection_version == 2


@pytest.mark.asyncio
async def test_revoking_a_frozen_configuration_marks_unstarted_stage_as_waiting_for_explicit_replacement(db_session):
    from src.api.model_configurations import revoke_model_configuration
    from src.api.tasks import list_stage_model_selections

    owner = User(email="revoked-selection@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="gpt-4.1", display_name="GPT", capabilities=["creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext="encrypted", verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(
        task_id=task.id, stage="scriptwriting", model_configuration_id=configuration.id,
        resolution_snapshot={"configuration_id": str(configuration.id)},
    ))
    await db_session.commit()

    await revoke_model_configuration(configuration.id, db_session, owner)
    selections = await list_stage_model_selections(task.id, db_session, owner)

    assert selections[0].stage == "scriptwriting"
    assert selections[0].availability_status == "replacement_required"


@pytest.mark.asyncio
async def test_task_creation_can_freeze_a_verified_compatible_stage_override_instead_of_the_default(db_session):
    from src.services.stage_model_selections import freeze_stage_model_selections

    owner = User(email="selection-override@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="gpt-4.1", display_name="GPT", capabilities=["creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext="encrypted", verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()

    selections = await freeze_stage_model_selections(db_session, task, owner.id, overrides={
        stage: configuration.id
        for stage in ("creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation")
    })

    assert [(selection.stage, selection.model_configuration_id) for selection in selections] == [
        (stage, configuration.id)
        for stage in ("creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation")
    ]


@pytest.mark.asyncio
async def test_task_cannot_start_until_every_applicable_stage_has_a_frozen_selection(db_session):
    from src.services.stage_model_selections import ModelSelectionUnavailableError, freeze_stage_model_selections

    owner = User(email="selection-missing@example.test", hashed_password="x")
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, task])
    await db_session.flush()

    with pytest.raises(ModelSelectionUnavailableError, match="scriptwriting"):
        await freeze_stage_model_selections(db_session, task, owner.id)
