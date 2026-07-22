import pytest
import httpx
from openai import NotFoundError

from src.models.model_configuration import ModelConfiguration


@pytest.mark.asyncio
async def test_credential_free_private_configuration_skips_safe_probe_without_crashing():
    from src.services.model_verification import NO_CREDENTIAL_PROBE, SafeModelVerifier

    configuration = ModelConfiguration(
        adapter="openai_compatible", api_base="http://tts.internal/v1", model_id="VoxCPM2",
        display_name="VoxCPM2", capabilities=["voice_generation"], constraints={}, credential_ciphertext=None,
    )

    result = await SafeModelVerifier().verify_configuration(configuration)

    assert result.available is False
    assert result.error == NO_CREDENTIAL_PROBE


@pytest.mark.asyncio
async def test_openai_compatible_endpoint_without_models_probe_is_eligible_for_first_use(monkeypatch):
    from src.services.model_verification import SAFE_PROBE_UNAVAILABLE, SafeModelVerifier

    class Models:
        async def retrieve(self, _model_id):
            raise NotFoundError(
                "The endpoint does not implement model retrieval",
                response=httpx.Response(404, request=httpx.Request("GET", "http://images.internal/v1/models/agnes")),
                body=None,
            )

    class Client:
        models = Models()

    monkeypatch.setattr("src.services.model_verification.AsyncOpenAI", lambda **_kwargs: Client())

    result = await SafeModelVerifier().verify(
        provider="openai_compatible", model_id="agnes-image-2.1-flash",
        api_base="http://images.internal/v1", credential="private-key",
    )

    assert result.available is False
    assert result.error == SAFE_PROBE_UNAVAILABLE
