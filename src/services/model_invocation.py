"""The sole business boundary for invoking a selected provider model.

Callers receive content and a non-sensitive resolution snapshot; the decrypted
BYOK exists only as a local variable while the LiteLLM SDK call is in flight.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import asyncio
from uuid import UUID
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.models.model_configuration import ModelConfiguration, StageModelSelection
from src.services.model_credentials import decrypt_credential


class ModelAvailabilityFailure(RuntimeError):
    """The frozen selection cannot serve; callers must request replacement."""


@dataclass(frozen=True)
class InvocationResult:
    content: str
    model_resolution_snapshot: dict


class LiteLLMClient:
    async def complete(self, *, provider: str, model_id: str, credential: str, messages: list[dict], temperature: float) -> str:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        response = await litellm.acompletion(
            model=f"{provider}/{model_id}", api_key=credential, messages=messages, temperature=temperature,
        )
        return response.choices[0].message.content or ""

    async def image(self, *, provider: str, model_id: str, credential: str, prompt: str, size: str, reference_image_url: str | None = None) -> str:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        params = {"model": f"{provider}/{model_id}", "api_key": credential, "prompt": prompt, "size": size}
        if reference_image_url:
            params["image"] = [reference_image_url]
        response = await litellm.aimage_generation(**params)
        return response.data[0].url

    async def speech(self, *, provider: str, model_id: str, credential: str, text: str, voice: str) -> bytes:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        response = await litellm.aspeech(
            model=f"{provider}/{model_id}", api_key=credential, input=text, voice=voice,
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file:
            path = Path(file.name)
        try:
            response.stream_to_file(path)
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    async def transcription(self, *, provider: str, model_id: str, credential: str, file_path: Path) -> str:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        with file_path.open("rb") as audio_file:
            response = await litellm.atranscription(
                model=f"{provider}/{model_id}", api_key=credential, file=audio_file,
            )
        return response.text

    async def video(self, *, provider: str, model_id: str, credential: str, prompt: str, seconds: int, image_urls: list[str]) -> bytes:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        reference_path = None
        reference_file = None
        try:
            params = {"model": f"{provider}/{model_id}", "api_key": credential, "prompt": prompt, "seconds": str(seconds), "size": "1152x768"}
            if image_urls:
                import httpx
                async with httpx.AsyncClient(timeout=60) as http:
                    response = await http.get(image_urls[0])
                    response.raise_for_status()
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
                    image_file.write(response.content)
                    reference_path = Path(image_file.name)
                reference_file = reference_path.open("rb")
                params["input_reference"] = reference_file
            created = await litellm.avideo_generation(**params)
            while True:
                status = await litellm.avideo_status(video_id=created.id)
                if status.status == "completed":
                    return await litellm.avideo_content(video_id=created.id)
                if status.status == "failed":
                    raise RuntimeError("Video provider reported failure")
                await asyncio.sleep(10)
        finally:
            if reference_file:
                reference_file.close()
            if reference_path:
                reference_path.unlink(missing_ok=True)


class ModelInvocationBoundary:
    def __init__(self, client=None):
        self.client = client or LiteLLMClient()

    async def _selection_and_credential(self, db: AsyncSession, task_id: UUID, stage: str):
        selection = await db.scalar(select(StageModelSelection).options(
            selectinload(StageModelSelection.model_configuration).selectinload(ModelConfiguration.catalog_model)
        ).where(StageModelSelection.task_id == task_id, StageModelSelection.stage == stage))
        if selection is None:
            raise ModelAvailabilityFailure(f"No frozen model selection for {stage}")
        if selection.availability_status != "available":
            raise ModelAvailabilityFailure(f"Frozen model selection for {stage} requires explicit replacement")
        configuration = selection.model_configuration
        if configuration.verification_status != "verified" or configuration.revoked_at is not None:
            raise ModelAvailabilityFailure(f"Frozen model selection for {stage} is unavailable")
        credential = (
            settings.platform_default_model_api_key
            if configuration.uses_platform_default
            else decrypt_credential(configuration.credential_ciphertext)
        )
        if not credential:
            raise ModelAvailabilityFailure(f"Frozen model selection for {stage} has no credential")
        return selection, configuration.catalog_model, credential

    async def _record_failure(self, db: AsyncSession, selection: StageModelSelection, configuration: ModelConfiguration) -> None:
        configuration.verification_status = "unavailable"
        # A failed invocation produced no candidate. It must wait for an
        # explicit replacement, rather than looking like a completed stage.
        selection.availability_status = "replacement_required"
        await db.commit()

    async def _record_success(self, db: AsyncSession, selection: StageModelSelection) -> None:
        selection.started_at = selection.started_at or datetime.now(timezone.utc)
        await db.commit()

    async def _invoke_same_selection(
        self, db: AsyncSession, selection: StageModelSelection, configuration: ModelConfiguration,
        stage: str, request: Callable[[], Awaitable[object]],
    ) -> object:
        """Retry only the frozen configuration; never resolve a fallback model."""
        for attempt in range(3):
            try:
                return await request()
            except Exception as error:
                if attempt == 2:
                    await self._record_failure(db, selection, configuration)
                    raise ModelAvailabilityFailure(f"Frozen model selection for {stage} is unavailable") from error
        raise AssertionError("unreachable")

    async def complete(
        self, db: AsyncSession, task_id: UUID, stage: str, messages: list[dict], *, temperature: float = 0.7,
    ) -> InvocationResult:
        selection, catalog, credential = await self._selection_and_credential(db, task_id, stage)
        configuration = selection.model_configuration
        content = await self._invoke_same_selection(db, selection, configuration, stage, lambda: self.client.complete(
                provider=catalog.provider, model_id=catalog.model_id, credential=credential,
                messages=messages, temperature=temperature,
            ))
        await self._record_success(db, selection)
        return InvocationResult(content=content, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def generate_image(
        self, db: AsyncSession, task_id: UUID, prompt: str, *, size: str = "1024x1024", reference_image_url: str | None = None,
    ) -> InvocationResult:
        selection, catalog, credential = await self._selection_and_credential(db, task_id, "keyframe_image")
        configuration = selection.model_configuration
        url = await self._invoke_same_selection(db, selection, configuration, "keyframe_image", lambda: self.client.image(
                provider=catalog.provider, model_id=catalog.model_id, credential=credential, prompt=prompt, size=size, reference_image_url=reference_image_url,
            ))
        await self._record_success(db, selection)
        return InvocationResult(content=url, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def generate_speech(
        self, db: AsyncSession, task_id: UUID, text: str, *, voice: str = "default",
    ) -> InvocationResult:
        selection, catalog, credential = await self._selection_and_credential(db, task_id, "voice_generation")
        configuration = selection.model_configuration
        audio = await self._invoke_same_selection(db, selection, configuration, "voice_generation", lambda: self.client.speech(
                provider=catalog.provider, model_id=catalog.model_id, credential=credential, text=text, voice=voice,
            ))
        await self._record_success(db, selection)
        return InvocationResult(content=audio, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def transcribe(self, db: AsyncSession, task_id: UUID, file_path: Path) -> InvocationResult:
        selection, catalog, credential = await self._selection_and_credential(db, task_id, "viral_analysis")
        configuration = selection.model_configuration
        transcript = await self._invoke_same_selection(db, selection, configuration, "viral_analysis", lambda: self.client.transcription(
                provider=catalog.provider, model_id=catalog.model_id, credential=credential, file_path=file_path,
            ))
        await self._record_success(db, selection)
        return InvocationResult(content=transcript, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def generate_video(
        self, db: AsyncSession, task_id: UUID, prompt: str, *, seconds: int, image_urls: list[str],
    ) -> InvocationResult:
        selection, catalog, credential = await self._selection_and_credential(db, task_id, "clip_video")
        configuration = selection.model_configuration
        maximum = int((catalog.constraints or {}).get("max_duration_seconds", seconds))
        if seconds > maximum:
            raise ModelAvailabilityFailure("Requested clip duration exceeds the frozen model constraint")
        video = await self._invoke_same_selection(db, selection, configuration, "clip_video", lambda: self.client.video(
                provider=catalog.provider, model_id=catalog.model_id, credential=credential,
                prompt=prompt, seconds=seconds, image_urls=image_urls,
            ))
        await self._record_success(db, selection)
        return InvocationResult(content=video, model_resolution_snapshot=dict(selection.resolution_snapshot))
