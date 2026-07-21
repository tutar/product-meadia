import pytest

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
