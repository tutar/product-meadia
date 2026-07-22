import pytest
import sys
from types import SimpleNamespace

from src.models.model_configuration import ModelConfiguration, ProviderModelCatalog, StageModelSelection
from src.models.task import VideoTask
from src.models.user import User
from src.services.model_credentials import encrypt_credential


def test_litellm_client_does_not_duplicate_an_explicit_provider_prefix():
    from src.services.model_invocation import LiteLLMClient

    assert LiteLLMClient._model_name("openai", "agnes-image-2.1-flash") == "openai/agnes-image-2.1-flash"
    assert LiteLLMClient._model_name("openai", "openai/agnes-image-2.1-flash") == "openai/agnes-image-2.1-flash"


@pytest.mark.asyncio
async def test_litellm_video_polling_reuses_private_endpoint_and_credential(monkeypatch):
    from src.services.model_invocation import LiteLLMClient

    calls = {}

    async def generate(**_kwargs):
        return SimpleNamespace(id="video-1")

    async def status(**kwargs):
        calls["status"] = kwargs
        return SimpleNamespace(status="completed")

    async def content(**kwargs):
        calls["content"] = kwargs
        return b"video-bytes"

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(
        avideo_generation=generate, avideo_status=status, avideo_content=content,
    ))
    result = await LiteLLMClient().video(
        provider="openai", model_id="private-video", credential="secret", prompt="orbit",
        seconds=5, image_urls=[], api_base="https://video.example/v1",
    )

    assert result == b"video-bytes"
    assert calls["status"]["api_base"] == calls["content"]["api_base"] == "https://video.example/v1"
    assert calls["status"]["api_key"] == calls["content"]["api_key"] == "secret"


@pytest.mark.asyncio
async def test_stage_start_freezes_latest_private_configuration_and_passes_its_api_base(db_session):
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeLiteLLM:
        async def complete(self, *, provider, model_id, api_base, credential, messages, temperature):
            assert (provider, model_id, api_base, credential) == (
                "openai", "private-script-v2", "http://scripts.internal/v1", "secret-only-at-boundary",
            )
            return "draft"

    owner = User(email="private-stage-owner@example.test", hashed_password="x")
    configuration = ModelConfiguration(
        owner=owner, adapter="openai_compatible", api_base="http://scripts.internal/v1",
        model_id="private-script-v2", display_name="Private script", capabilities=["scriptwriting"],
        constraints={}, revision=2, credential_ciphertext=encrypt_credential("secret-only-at-boundary"),
        verification_status="verified",
    )
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, configuration, task])
    await db_session.flush()
    selection = StageModelSelection(task_id=task.id, stage="scriptwriting", model_configuration_id=configuration.id)
    db_session.add(selection)
    await db_session.commit()

    result = await ModelInvocationBoundary(FakeLiteLLM()).complete(
        db_session, task.id, "scriptwriting", [{"role": "user", "content": "draft"}],
    )

    await db_session.refresh(selection)
    assert selection.started_at is not None
    assert result.model_resolution_snapshot == {
        "configuration_id": str(configuration.id), "adapter": "openai_compatible",
        "api_base": "http://scripts.internal/v1", "model_id": "private-script-v2",
        "capabilities": ["scriptwriting"], "constraints": {}, "configuration_revision": 2,
        "selection_version": 1,
    }


@pytest.mark.asyncio
async def test_credential_free_private_endpoint_is_invoked_without_an_api_key(db_session):
    from src.services.model_invocation import ModelInvocationBoundary
    from src.services.model_verification import NO_CREDENTIAL_PROBE

    class FakeLiteLLM:
        async def complete(self, *, provider, model_id, api_base, credential, messages, temperature):
            assert (provider, model_id, api_base, credential) == (
                "openai", "local-script", "http://scripts.internal/v1", None,
            )
            return "local draft"

    owner = User(email="credential-free-invocation@example.test", hashed_password="x")
    configuration = ModelConfiguration(
        owner=owner, adapter="openai_compatible", api_base="http://scripts.internal/v1",
        model_id="local-script", display_name="Local script", capabilities=["scriptwriting"], constraints={},
        credential_ciphertext=None, verification_status="unverified", verification_error=NO_CREDENTIAL_PROBE,
    )
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, configuration, task])
    await db_session.flush()
    selection = StageModelSelection(task_id=task.id, stage="scriptwriting", model_configuration_id=configuration.id)
    db_session.add(selection)
    await db_session.commit()

    result = await ModelInvocationBoundary(FakeLiteLLM()).complete(
        db_session, task.id, "scriptwriting", [{"role": "user", "content": "draft"}],
    )

    await db_session.refresh(configuration)
    assert result.content == "local draft"
    assert configuration.verification_status == "verified"


@pytest.mark.asyncio
async def test_invocation_uses_frozen_selection_and_decrypts_byok_only_at_the_boundary(db_session):
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeLiteLLM:
        async def complete(self, *, provider, model_id, credential, messages, temperature):
            assert (provider, model_id, credential) == ("openai", "gpt-4.1-mini", "secret-only-at-boundary")
            assert messages == [{"role": "user", "content": "draft a script"}]
            return "draft"

    owner = User(email="invocation-owner@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="gpt-4.1-mini", display_name="GPT", capabilities=["scriptwriting"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext=encrypt_credential("secret-only-at-boundary"), verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(
        task_id=task.id, stage="scriptwriting", model_configuration_id=configuration.id,
        resolution_snapshot={"configuration_id": str(configuration.id), "provider": "openai", "model_id": "gpt-4.1-mini", "capability_revision": 1, "selection_version": 1, "uses_platform_default": False},
    ))
    await db_session.commit()

    result = await ModelInvocationBoundary(FakeLiteLLM()).complete(
        db_session, task.id, "scriptwriting", [{"role": "user", "content": "draft a script"}], temperature=0.2,
    )

    assert result.content == "draft"
    assert result.model_resolution_snapshot["model_id"] == "gpt-4.1-mini"
    assert "credential" not in result.model_resolution_snapshot


@pytest.mark.asyncio
async def test_availability_failure_requires_and_allows_an_explicit_replacement_before_stage_starts(db_session):
    from src.services.model_invocation import ModelAvailabilityFailure, ModelInvocationBoundary
    from src.services.stage_model_selections import replace_stage_model_selection

    class FailingLiteLLM:
        calls = 0
        async def complete(self, **_kwargs):
            self.calls += 1
            raise RuntimeError("provider unavailable")

    owner = User(email="replacement-after-failure@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="gpt-4.1-mini", display_name="GPT", capabilities=["scriptwriting"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    original = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext=encrypt_credential("old"), verification_status="verified")
    replacement = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext=encrypt_credential("new"), verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([original, replacement, task])
    await db_session.flush()
    selection = StageModelSelection(task_id=task.id, stage="scriptwriting", model_configuration_id=original.id, resolution_snapshot={"provider": "openai", "model_id": "gpt-4.1-mini"})
    db_session.add(selection)
    await db_session.commit()

    client = FailingLiteLLM()
    with pytest.raises(ModelAvailabilityFailure):
        await ModelInvocationBoundary(client).complete(db_session, task.id, "scriptwriting", [])

    assert client.calls == 3

    await db_session.refresh(selection)
    assert selection.started_at is not None
    assert selection.availability_status == "replacement_required"
    updated = await replace_stage_model_selection(db_session, task, owner.id, "scriptwriting", replacement.id)
    assert updated.model_configuration_id == replacement.id
    assert updated.availability_status == "available"


@pytest.mark.asyncio
async def test_image_invocation_uses_the_frozen_keyframe_selection(db_session):
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeLiteLLM:
        async def image(self, *, provider, model_id, credential, prompt, size, reference_image_url):
            assert (provider, model_id, credential, prompt, size) == ("openai", "gpt-image-1", "image-secret", "Cinematic candle", "1024x1024")
            return "https://provider.example/generated.png"

    owner = User(email="image-invocation-owner@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="gpt-image-1", display_name="Image", capabilities=["keyframe_image"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext=encrypt_credential("image-secret"), verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(task_id=task.id, stage="keyframe_image", model_configuration_id=configuration.id, resolution_snapshot={"provider": "openai", "model_id": "gpt-image-1"}))
    await db_session.commit()

    result = await ModelInvocationBoundary(FakeLiteLLM()).generate_image(db_session, task.id, "Cinematic candle", size="1024x1024")

    assert result.content == "https://provider.example/generated.png"


@pytest.mark.asyncio
async def test_speech_invocation_uses_the_frozen_voice_selection(db_session):
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeLiteLLM:
        async def speech(self, *, provider, model_id, credential, text, voice):
            assert (provider, model_id, credential, text, voice) == ("openai", "gpt-4o-mini-tts", "voice-secret", "Narrate this", "default")
            return b"wave-bytes"

    owner = User(email="speech-invocation-owner@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="gpt-4o-mini-tts", display_name="Voice", capabilities=["voice_generation"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext=encrypt_credential("voice-secret"), verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(task_id=task.id, stage="voice_generation", model_configuration_id=configuration.id, resolution_snapshot={"provider": "openai", "model_id": "gpt-4o-mini-tts"}))
    await db_session.commit()

    result = await ModelInvocationBoundary(FakeLiteLLM()).generate_speech(db_session, task.id, "Narrate this")

    assert result.content == b"wave-bytes"


@pytest.mark.asyncio
async def test_transcription_invocation_uses_the_frozen_viral_analysis_selection(db_session, tmp_path):
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeLiteLLM:
        async def transcription(self, *, provider, model_id, credential, file_path):
            assert (provider, model_id, credential) == ("openai", "gpt-4o-transcribe", "transcribe-secret")
            assert file_path.read_bytes() == b"audio"
            return "transcript"

    owner = User(email="transcribe-invocation-owner@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="gpt-4o-transcribe", display_name="Transcribe", capabilities=["viral_analysis"], constraints={})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext=encrypt_credential("transcribe-secret"), verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="viral", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(task_id=task.id, stage="viral_analysis", model_configuration_id=configuration.id, resolution_snapshot={"provider": "openai", "model_id": "gpt-4o-transcribe"}))
    await db_session.commit()
    audio = tmp_path / "source.wav"; audio.write_bytes(b"audio")

    result = await ModelInvocationBoundary(FakeLiteLLM()).transcribe(db_session, task.id, audio)

    assert result.content == "transcript"


@pytest.mark.asyncio
async def test_video_invocation_uses_the_frozen_clip_selection(db_session):
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeLiteLLM:
        async def video(self, *, provider, model_id, credential, prompt, seconds, image_urls):
            assert (provider, model_id, credential, prompt, seconds, image_urls) == ("openai", "sora-2", "video-secret", "Orbit", 5, ["https://image"])
            return b"mp4-bytes"

    owner = User(email="video-invocation-owner@example.test", hashed_password="x")
    catalog = ProviderModelCatalog(provider="openai", model_id="sora-2", display_name="Video", capabilities=["clip_video"], constraints={"max_duration_seconds": 5})
    db_session.add_all([owner, catalog])
    await db_session.flush()
    configuration = ModelConfiguration(owner_user_id=owner.id, catalog_model_id=catalog.id, credential_ciphertext=encrypt_credential("video-secret"), verification_status="verified")
    task = VideoTask(user_id=owner.id, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(task_id=task.id, stage="clip_video", model_configuration_id=configuration.id, resolution_snapshot={"provider": "openai", "model_id": "sora-2"}))
    await db_session.commit()

    result = await ModelInvocationBoundary(FakeLiteLLM()).generate_video(db_session, task.id, "Orbit", seconds=5, image_urls=["https://image"])

    assert result.content == b"mp4-bytes"


@pytest.mark.asyncio
async def test_agnes_video_v2_invocation_uses_the_frozen_clip_selection(db_session):
    from src.services.model_invocation import ModelInvocationBoundary

    class FakeAgnesVideo:
        async def generate(self, *, api_base, model_id, credential, prompt, seconds, image_urls):
            assert api_base == "https://apihub.agnes-ai.com"
            assert model_id == "agnes-video-v2.0"
            assert credential == "agnes-video-secret"
            assert prompt == "Animate the bottle"
            assert seconds == 5
            assert image_urls == ["https://media.example/keyframe.png"]
            return b"agnes-mp4-bytes"

    owner = User(email="agnes-video-invocation-owner@example.test", hashed_password="x")
    configuration = ModelConfiguration(
        owner=owner, adapter="agnes_video_v2", api_base="https://apihub.agnes-ai.com",
        model_id="agnes-video-v2.0", display_name="Agnes Video", capabilities=["clip_video"],
        constraints={"max_duration_seconds": 5}, credential_ciphertext=encrypt_credential("agnes-video-secret"),
        verification_status="unverified", verification_error="No safe verification probe is configured; availability will be established on first use",
    )
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, configuration, task])
    await db_session.flush()
    db_session.add(StageModelSelection(
        task_id=task.id, stage="clip_video", model_configuration_id=configuration.id,
        resolution_snapshot={"adapter": "agnes_video_v2", "api_base": "https://apihub.agnes-ai.com", "model_id": "agnes-video-v2.0", "constraints": {"max_duration_seconds": 5}},
    ))
    await db_session.commit()

    result = await ModelInvocationBoundary(agnes_video_client=FakeAgnesVideo()).generate_video(
        db_session, task.id, "Animate the bottle", seconds=5, image_urls=["https://media.example/keyframe.png"],
    )

    assert result.content == b"agnes-mp4-bytes"


@pytest.mark.asyncio
async def test_agnes_video_v2_failure_records_a_safe_availability_summary(db_session):
    from src.services.agnes_video_v2 import AgnesVideoV2Failure
    from src.services.model_invocation import ModelAvailabilityFailure, ModelInvocationBoundary

    class FailingAgnesVideo:
        async def generate(self, **_kwargs):
            raise AgnesVideoV2Failure("Agnes video service request failed")

    owner = User(email="agnes-video-failure-owner@example.test", hashed_password="x")
    configuration = ModelConfiguration(
        owner=owner, adapter="agnes_video_v2", api_base="https://apihub.agnes-ai.com",
        model_id="agnes-video-v2.0", display_name="Agnes Video", capabilities=["clip_video"],
        constraints={"max_duration_seconds": 5}, credential_ciphertext=encrypt_credential("secret"),
        verification_status="unverified", verification_error="No safe verification probe is configured; availability will be established on first use",
    )
    task = VideoTask(user=owner, product_snapshot={}, type="promo", image_count=1)
    db_session.add_all([owner, configuration, task])
    await db_session.flush()
    selection = StageModelSelection(
        task_id=task.id, stage="clip_video", model_configuration_id=configuration.id,
        resolution_snapshot={"adapter": "agnes_video_v2", "api_base": "https://apihub.agnes-ai.com", "model_id": "agnes-video-v2.0", "constraints": {"max_duration_seconds": 5}},
    )
    db_session.add(selection)
    await db_session.commit()

    with pytest.raises(ModelAvailabilityFailure):
        await ModelInvocationBoundary(agnes_video_client=FailingAgnesVideo()).generate_video(
            db_session, task.id, "Animate", seconds=5, image_urls=["https://storage.example/keyframe.png"],
        )

    await db_session.refresh(configuration)
    assert configuration.verification_status == "unavailable"
    assert configuration.verification_error == "Agnes video service request failed"
