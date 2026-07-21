"""Non-billable configuration verification.

This module intentionally exposes no generation operation. A provider without
a safe authentication/model-reachability probe remains unverified.
"""
from dataclasses import dataclass

from openai import AsyncOpenAI

from src.config import settings
from src.models.model_configuration import ModelConfiguration
from src.services.model_credentials import decrypt_credential


@dataclass(frozen=True)
class VerificationResult:
    available: bool
    error: str | None = None


class SafeModelVerifier:
    async def verify_configuration(self, configuration: ModelConfiguration) -> VerificationResult:
        """Resolve the credential transiently inside the server-side probe boundary."""
        credential = (
            settings.platform_default_model_api_key
            if configuration.uses_platform_default
            else decrypt_credential(configuration.credential_ciphertext)
        )
        return await self.verify(
            provider=configuration.catalog_model.provider,
            model_id=configuration.catalog_model.model_id,
            credential=credential,
        )

    async def verify(self, *, provider: str, model_id: str, credential: str | None) -> VerificationResult:
        if not credential:
            return VerificationResult(False, "No credential is available for verification")
        if provider != "openai":
            return VerificationResult(False, "This provider has no configured safe verification probe")
        try:
            # Model retrieval authenticates and checks reachability without a
            # completion/image/video generation side effect.
            await AsyncOpenAI(api_key=credential).models.retrieve(model_id)
            return VerificationResult(True)
        except Exception as error:
            return VerificationResult(False, "Credential or model verification failed")
