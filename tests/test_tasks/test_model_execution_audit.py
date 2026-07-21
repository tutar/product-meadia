import pytest
from sqlalchemy import select

from src.models.generation_record import GenerationRecord
from src.models.model_configuration import ModelConfiguration, ProviderModelCatalog, StageModelSelection
from src.models.task import VideoTask
from src.models.user import User
from src.services.model_credentials import encrypt_credential


@pytest.mark.asyncio
async def test_frozen_fake_provider_invocation_persists_a_non_secret_generation_record(db_session):
    from src.services.generation_audit import persist_generation_record
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeLiteLLM:
        async def complete(self, *, provider, model_id, credential, messages, temperature):
            assert (provider, model_id, credential) == ("openai", "gpt-4.1-mini", "byok-only-at-invocation")
            assert messages == [{"role": "user", "content": "Draft the product script."}]
            return "A concise script"

    owner = User(email="execution-audit@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(
        provider="openai", model_id="gpt-4.1-mini", display_name="GPT",
        capabilities=["scriptwriting"], constraints={}, capability_revision=4,
    )
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(
        owner_user_id=owner.id, catalog_model_id=catalog.id,
        credential_ciphertext=encrypt_credential("byok-only-at-invocation"), verification_status="verified",
    )
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(
        task_id=task.id, stage="scriptwriting", model_configuration_id=configuration.id,
        resolution_snapshot={
            "provider": "openai", "model_id": "gpt-4.1-mini", "capability_revision": 4,
            "selection_version": 1, "uses_platform_default": False,
        },
    ))
    await db_session.commit()

    resolved = await ModelInvocationBoundary(FakeLiteLLM()).complete(
        db_session, task.id, "scriptwriting", [{"role": "user", "content": "Draft the product script."}], temperature=0.2,
    )
    await persist_generation_record(
        db_session, task_id=task.id, execution_stage="scripting", substep="generate_script", attempt=2,
        provider="openai", model="gpt-4.1-mini", parameters={"temperature": 0.2},
        normalized_input={"user": "Draft the product script."}, normalized_output={"content": resolved.content},
        provider_payload={"model": "gpt-4.1-mini"},
    )
    await db_session.commit()

    record = await db_session.scalar(select(GenerationRecord).where(GenerationRecord.task_id == task.id))
    assert record.model_resolution_snapshot == {
        **resolved.model_resolution_snapshot,
        "invocation_parameters": {"temperature": 0.2},
        "retry_count": 1,
    }
    assert "byok-only-at-invocation" not in str(record.model_resolution_snapshot)
