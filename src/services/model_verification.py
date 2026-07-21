"""Non-billable configuration verification.

This module intentionally exposes no generation operation. A provider without
a safe authentication/model-reachability probe remains unverified.
"""
from dataclasses import dataclass

from openai import AsyncOpenAI

from src.models.model_configuration import ModelConfiguration
from src.services.model_credentials import decrypt_credential

SAFE_PROBE_UNAVAILABLE = "No safe verification probe is configured; availability will be established on first use"
NO_CREDENTIAL_PROBE = "No credential is configured; availability will be established on first use"


@dataclass(frozen=True)
class VerificationResult:
    available: bool
    error: str | None = None


def is_selectable(configuration: ModelConfiguration) -> bool:
    """Unprobeable configurations are eligible for their first real use."""
    return configuration.verification_status == "verified" or (
        configuration.verification_status == "unverified"
        and configuration.verification_error in {SAFE_PROBE_UNAVAILABLE, NO_CREDENTIAL_PROBE}
    )


class SafeModelVerifier:
    async def verify_configuration(self, configuration: ModelConfiguration) -> VerificationResult:
        """Resolve the credential transiently inside the server-side probe boundary."""
        credential = decrypt_credential(configuration.credential_ciphertext)
        template = configuration.catalog_model
        return await self.verify(
            provider=configuration.adapter or (template.provider if template else "openai"),
            model_id=configuration.model_id or (template.model_id if template else ""),
            api_base=configuration.api_base,
            credential=credential,
        )

    async def verify(self, *, provider: str, model_id: str, credential: str | None, api_base: str | None = None) -> VerificationResult:
        if not credential:
            return VerificationResult(False, NO_CREDENTIAL_PROBE)
        if provider not in {"openai", "openai_compatible"}:
            return VerificationResult(False, SAFE_PROBE_UNAVAILABLE)
        try:
            # Model retrieval authenticates and checks reachability without a
            # completion/image/video generation side effect.
            await AsyncOpenAI(api_key=credential, base_url=api_base).models.retrieve(model_id)
            return VerificationResult(True)
        except Exception as error:
            return VerificationResult(False, "Credential or model verification failed")
