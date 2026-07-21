import pytest

from src.models.user import User


@pytest.mark.asyncio
async def test_user_can_create_and_edit_a_private_openai_compatible_model_without_exposing_byok(db_session):
    from src.api.model_configurations import create_model_configuration, update_model_configuration
    from src.schemas.model_configuration import ModelConfigurationCreate, ModelConfigurationUpdate

    user = User(email="private-model-owner@example.test", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    created = await create_model_configuration(
        ModelConfigurationCreate(
            display_name="My internal voice",
            adapter="openai_compatible",
            api_base="http://voice.internal/v1",
            model_id="my-tts",
            capabilities=["voice_generation"],
            constraints={"audio_format": "wav"},
            credential="private-byok",
        ),
        db_session,
        user,
    )
    updated = await update_model_configuration(
        created.id,
        ModelConfigurationUpdate(model_id="my-tts-v2"),
        db_session,
        user,
    )

    assert created.api_base == "http://voice.internal/v1"
    assert created.model_id == "my-tts"
    assert created.capabilities == ["voice_generation"]
    assert updated.model_id == "my-tts-v2"
    assert updated.revision == created.revision + 1
    assert "private-byok" not in str(created.model_dump())
    assert "private-byok" not in str(updated.model_dump())


@pytest.mark.asyncio
async def test_user_can_create_a_private_model_that_does_not_require_a_credential(db_session):
    from src.api.model_configurations import create_model_configuration, verify_model_configuration
    from src.schemas.model_configuration import ModelConfigurationCreate

    user = User(email="unauthenticated-private-model@example.test", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    configuration = await create_model_configuration(
        ModelConfigurationCreate(
            display_name="Local TTS", adapter="openai_compatible", api_base="http://tts.internal/v1",
            model_id="local-tts", capabilities=["voice_generation"],
        ),
        db_session, user,
    )

    assert configuration.model_id == "local-tts"
    assert configuration.verification_status == "unverified"

    verified = await verify_model_configuration(configuration.id, db_session, user)
    assert verified.verification_status == "unverified"
    assert "No credential is configured" in verified.verification_error


def test_private_model_endpoint_requires_https_when_it_is_public():
    from pydantic import ValidationError
    from src.schemas.model_configuration import ModelConfigurationCreate

    with pytest.raises(ValidationError, match="HTTPS"):
        ModelConfigurationCreate(
            display_name="Public voice", adapter="openai_compatible", api_base="http://voice.example.com/v1",
            model_id="voice-v1", capabilities=["voice_generation"], credential="secret",
        )

    configuration = ModelConfigurationCreate(
        display_name="Private voice", adapter="openai_compatible", api_base="http://voice.internal/v1",
        model_id="voice-v1", capabilities=["voice_generation"], credential="secret",
    )
    assert configuration.api_base == "http://voice.internal/v1"


@pytest.mark.asyncio
async def test_user_creates_a_capability_compatible_configuration_without_credential_redaction_leak(db_session):
    """The configuration API exposes selectable metadata, never the BYOK."""
    from src.api.model_configurations import (
        create_model_configuration,
        list_provider_model_catalog,
    )
    from src.schemas.model_configuration import ModelConfigurationCreate

    user = User(email="model-owner@example.test", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    image_models = await list_provider_model_catalog(capability="keyframe_image", db=db_session)
    assert [model.model_id for model in image_models] == ["gpt-image-1"]
    assert image_models[0].capabilities == ["keyframe_image"]

    configuration = await create_model_configuration(
        ModelConfigurationCreate(
            catalog_model_id=image_models[0].id,
            credential="byok-should-never-leave-the-server",
        ),
        db=db_session,
        user=user,
    )

    assert configuration.catalog_model_id == image_models[0].id
    assert configuration.verification_status == "unverified"
    assert "credential" not in configuration.model_dump()
    assert "byok-should-never-leave-the-server" not in str(configuration.model_dump())


@pytest.mark.asyncio
async def test_template_configuration_copies_runtime_fields_without_a_live_catalog_dependency(db_session):
    from src.api.model_configurations import create_model_configuration, list_provider_model_catalog
    from src.models.model_configuration import ProviderModelCatalog
    from src.schemas.model_configuration import ModelConfigurationCreate

    user = User(email="template-copy-owner@example.test", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    template = (await list_provider_model_catalog("keyframe_image", db_session))[0]
    configuration = await create_model_configuration(
        ModelConfigurationCreate(catalog_model_id=template.id, credential="template-copy-secret"), db_session, user,
    )

    stored_template = await db_session.get(ProviderModelCatalog, template.id)
    stored_template.model_id = "changed-template-model"
    stored_template.capabilities = ["voice_generation"]
    await db_session.commit()

    assert configuration.model_id == "gpt-image-1"
    assert configuration.capabilities == ["keyframe_image"]


@pytest.mark.asyncio
async def test_only_verified_capability_compatible_configurations_become_stage_defaults(db_session):
    from fastapi import HTTPException
    from src.api.model_configurations import (
        create_model_configuration, list_provider_model_catalog,
        set_stage_model_default, verify_model_configuration,
    )
    from src.schemas.model_configuration import ModelConfigurationCreate, StageModelDefaultUpsert
    from src.services.model_verification import VerificationResult

    class SafeProbe:
        async def verify_configuration(self, configuration):
            assert configuration.catalog_model.provider == "openai"
            assert configuration.catalog_model.model_id == "gpt-4.1-mini"
            assert configuration.credential_ciphertext != "secret-for-the-server-only"
            return VerificationResult(available=True)

    user = User(email="verified-owner@example.test", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    text_model = (await list_provider_model_catalog("creative_planning", db_session))[0]
    configuration = await create_model_configuration(
        ModelConfigurationCreate(catalog_model_id=text_model.id, credential="secret-for-the-server-only"),
        db_session, user,
    )

    verified = await verify_model_configuration(configuration.id, db_session, user, verifier=SafeProbe())
    default = await set_stage_model_default(
        "creative_planning", StageModelDefaultUpsert(model_configuration_id=configuration.id), db_session, user,
    )

    assert verified.verification_status == "verified"
    assert default.model_configuration_id == configuration.id
    with pytest.raises(HTTPException, match="not compatible") as error:
        await set_stage_model_default(
            "keyframe_image", StageModelDefaultUpsert(model_configuration_id=configuration.id), db_session, user,
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_configuration_without_a_safe_probe_stays_unverified_but_can_be_selected_for_first_use(db_session):
    from src.api.model_configurations import (
        create_model_configuration, list_provider_model_catalog, set_stage_model_default, verify_model_configuration,
    )
    from src.schemas.model_configuration import ModelConfigurationCreate, StageModelDefaultUpsert
    from src.services.model_verification import SAFE_PROBE_UNAVAILABLE, VerificationResult

    class NoSafeProbe:
        async def verify_configuration(self, configuration):
            return VerificationResult(False, SAFE_PROBE_UNAVAILABLE)

    owner = User(email="unprobeable-owner@example.test", hashed_password="x")
    db_session.add(owner)
    await db_session.commit()
    clip_template = (await list_provider_model_catalog("clip_video", db_session))[0]
    configuration = await create_model_configuration(
        ModelConfigurationCreate(catalog_model_id=clip_template.id, credential="private-video-secret"), db_session, owner,
    )

    checked = await verify_model_configuration(configuration.id, db_session, owner, verifier=NoSafeProbe())
    default = await set_stage_model_default(
        "clip_video", StageModelDefaultUpsert(model_configuration_id=configuration.id), db_session, owner,
    )

    assert checked.verification_status == "unverified"
    assert checked.verification_error == SAFE_PROBE_UNAVAILABLE
    assert default.model_configuration_id == configuration.id


@pytest.mark.asyncio
async def test_revocation_destroys_byok_and_only_never_referenced_configurations_can_be_deleted(db_session):
    from fastapi import HTTPException
    from sqlalchemy import select
    from src.api.model_configurations import (
        create_model_configuration, delete_model_configuration,
        list_provider_model_catalog, revoke_model_configuration,
    )
    from src.models.model_configuration import ModelConfiguration
    from src.schemas.model_configuration import ModelConfigurationCreate

    owner = User(email="revoke-owner@example.test", hashed_password="x")
    outsider = User(email="revoke-outsider@example.test", hashed_password="x")
    db_session.add_all([owner, outsider])
    await db_session.commit()
    catalog = (await list_provider_model_catalog("keyframe_image", db_session))[0]
    configuration = await create_model_configuration(
        ModelConfigurationCreate(catalog_model_id=catalog.id, credential="revoke-this-secret"), db_session, owner,
    )
    stored = await db_session.scalar(select(ModelConfiguration).where(ModelConfiguration.id == configuration.id))
    assert stored.credential_ciphertext != "revoke-this-secret"

    with pytest.raises(HTTPException) as forbidden:
        await revoke_model_configuration(configuration.id, db_session, outsider)
    assert forbidden.value.status_code == 404

    revoked = await revoke_model_configuration(configuration.id, db_session, owner)
    stored = await db_session.scalar(select(ModelConfiguration).where(ModelConfiguration.id == configuration.id))
    assert revoked.verification_status == "revoked"
    assert stored.credential_ciphertext is None

    await delete_model_configuration(configuration.id, db_session, owner)
    assert await db_session.scalar(select(ModelConfiguration).where(ModelConfiguration.id == configuration.id)) is None


@pytest.mark.asyncio
async def test_rotating_a_model_configuration_credential_requires_reverification_and_never_echoes_the_new_secret(db_session):
    from src.api.model_configurations import create_model_configuration, list_provider_model_catalog, update_model_configuration
    from src.schemas.model_configuration import ModelConfigurationCreate, ModelConfigurationUpdate

    owner = User(email="rotate-owner@example.test", hashed_password="x")
    db_session.add(owner)
    await db_session.commit()
    catalog = (await list_provider_model_catalog("scriptwriting", db_session))[0]
    configuration = await create_model_configuration(
        ModelConfigurationCreate(catalog_model_id=catalog.id, credential="old-secret"), db_session, owner,
    )

    updated = await update_model_configuration(
        configuration.id, ModelConfigurationUpdate(credential="rotated-secret"), db_session, owner,
    )

    assert updated.verification_status == "unverified"
    assert "rotated-secret" not in str(updated.model_dump())
