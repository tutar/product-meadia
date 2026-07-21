"""Non-billable configuration verification.

This module intentionally exposes no generation operation. A provider without
a safe authentication/model-reachability probe remains unverified.
"""
from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass(frozen=True)
class VerificationResult:
    available: bool
    error: str | None = None


class SafeModelVerifier:
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
