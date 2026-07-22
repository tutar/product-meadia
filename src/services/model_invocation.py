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
from src.services.model_verification import is_selectable
from src.services.stage_model_selections import resolve_stage_model_selection


class ModelAvailabilityFailure(RuntimeError):
    """The frozen selection cannot serve; callers must request replacement."""


@dataclass(frozen=True)
class InvocationResult:
    content: str
    model_resolution_snapshot: dict


class LiteLLMClient:
    @staticmethod
    def _model_name(provider: str, model_id: str) -> str:
        """Preserve an explicit provider prefix from a user configuration."""
        return model_id if model_id.startswith(f"{provider}/") else f"{provider}/{model_id}"

    async def complete(self, *, provider: str, model_id: str, credential: str | None, messages: list[dict], temperature: float, api_base: str | None = None) -> str:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        params = {"model": self._model_name(provider, model_id), "messages": messages, "temperature": temperature}
        if credential: params["api_key"] = credential
        if api_base: params["api_base"] = api_base
        response = await litellm.acompletion(**params)
        return response.choices[0].message.content or ""

    async def image(self, *, provider: str, model_id: str, credential: str | None, prompt: str, size: str, reference_image_url: str | None = None, api_base: str | None = None) -> str:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        params = {"model": self._model_name(provider, model_id), "prompt": prompt, "size": size}
        if credential: params["api_key"] = credential
        if reference_image_url:
            params["image"] = [reference_image_url]
        if api_base:
            params["api_base"] = api_base
        response = await litellm.aimage_generation(**params)
        return response.data[0].url

    async def speech(self, *, provider: str, model_id: str, credential: str | None, text: str, voice: str, api_base: str | None = None) -> bytes:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        params = {"model": self._model_name(provider, model_id), "input": text, "voice": voice}
        if credential: params["api_key"] = credential
        if api_base: params["api_base"] = api_base
        response = await litellm.aspeech(**params)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file:
            path = Path(file.name)
        try:
            response.stream_to_file(path)
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    async def transcription(self, *, provider: str, model_id: str, credential: str | None, file_path: Path, api_base: str | None = None) -> str:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        with file_path.open("rb") as audio_file:
            params = {"model": self._model_name(provider, model_id), "file": audio_file}
            if credential: params["api_key"] = credential
            if api_base: params["api_base"] = api_base
            response = await litellm.atranscription(**params)
        return response.text

    async def video(self, *, provider: str, model_id: str, credential: str | None, prompt: str, seconds: int, image_urls: list[str], api_base: str | None = None) -> bytes:
        try:
            import litellm
        except ImportError as error:  # pragma: no cover - packaging protects deployed environments
            raise RuntimeError("LiteLLM SDK is required for model invocation") from error
        reference_path = None
        reference_file = None
        try:
            params = {"model": self._model_name(provider, model_id), "prompt": prompt, "seconds": str(seconds), "size": "1152x768"}
            if credential: params["api_key"] = credential
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
            if api_base:
                params["api_base"] = api_base
            created = await litellm.avideo_generation(**params)
            while True:
                status = await litellm.avideo_status(
                    video_id=created.id, api_base=api_base, api_key=credential,
                )
                if status.status == "completed":
                    return await litellm.avideo_content(
                        video_id=created.id, api_base=api_base, api_key=credential,
                    )
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
        if selection.started_at is None:
            try:
                selection = await resolve_stage_model_selection(db, task_id, stage)
                await db.commit()
            except Exception as error:
                await db.rollback()
                raise ModelAvailabilityFailure(f"Model selection for {stage} cannot start") from error
        if selection.availability_status != "available":
            raise ModelAvailabilityFailure(f"Frozen model selection for {stage} requires explicit replacement")
        configuration = selection.model_configuration
        if not is_selectable(configuration) or configuration.revoked_at is not None:
            raise ModelAvailabilityFailure(f"Frozen model selection for {stage} is unavailable")
        credential = (
            settings.platform_default_model_api_key
            if configuration.uses_platform_default
            else decrypt_credential(configuration.credential_ciphertext) if configuration.credential_ciphertext else None
        )
        return selection, credential

    @staticmethod
    def _provider(snapshot: dict) -> str:
        return "openai" if snapshot.get("adapter") == "openai_compatible" else snapshot.get("adapter", "openai")

    @classmethod
    def _call_parameters(cls, snapshot: dict, **kwargs) -> dict:
        if snapshot.get("api_base"):
            kwargs["api_base"] = snapshot["api_base"]
        kwargs["provider"] = cls._provider(snapshot)
        kwargs["model_id"] = snapshot["model_id"]
        return kwargs

    async def _record_failure(self, db: AsyncSession, selection: StageModelSelection, configuration: ModelConfiguration) -> None:
        configuration.verification_status = "unavailable"
        # A failed invocation produced no candidate. It must wait for an
        # explicit replacement, rather than looking like a completed stage.
        selection.availability_status = "replacement_required"
        await db.commit()

    async def _record_success(self, db: AsyncSession, selection: StageModelSelection) -> None:
        selection.started_at = selection.started_at or datetime.now(timezone.utc)
        if selection.model_configuration.verification_status == "unverified":
            selection.model_configuration.verification_status = "verified"
            selection.model_configuration.verification_error = None
            selection.model_configuration.verified_at = datetime.now(timezone.utc)
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
        selection, credential = await self._selection_and_credential(db, task_id, stage)
        configuration = selection.model_configuration
        snapshot = dict(selection.resolution_snapshot)
        content = await self._invoke_same_selection(db, selection, configuration, stage, lambda: self.client.complete(**self._call_parameters(snapshot, credential=credential, messages=messages, temperature=temperature)))
        await self._record_success(db, selection)
        return InvocationResult(content=content, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def generate_image(
        self, db: AsyncSession, task_id: UUID, prompt: str, *, size: str = "1024x1024", reference_image_url: str | None = None,
    ) -> InvocationResult:
        selection, credential = await self._selection_and_credential(db, task_id, "keyframe_image")
        configuration = selection.model_configuration
        snapshot = dict(selection.resolution_snapshot)
        url = await self._invoke_same_selection(db, selection, configuration, "keyframe_image", lambda: self.client.image(**self._call_parameters(snapshot, credential=credential, prompt=prompt, size=size, reference_image_url=reference_image_url)))
        await self._record_success(db, selection)
        return InvocationResult(content=url, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def generate_speech(
        self, db: AsyncSession, task_id: UUID, text: str, *, voice: str = "default",
    ) -> InvocationResult:
        selection, credential = await self._selection_and_credential(db, task_id, "voice_generation")
        configuration = selection.model_configuration
        snapshot = dict(selection.resolution_snapshot)
        audio = await self._invoke_same_selection(db, selection, configuration, "voice_generation", lambda: self.client.speech(**self._call_parameters(snapshot, credential=credential, text=text, voice=voice)))
        await self._record_success(db, selection)
        return InvocationResult(content=audio, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def transcribe(self, db: AsyncSession, task_id: UUID, file_path: Path) -> InvocationResult:
        selection, credential = await self._selection_and_credential(db, task_id, "viral_analysis")
        configuration = selection.model_configuration
        snapshot = dict(selection.resolution_snapshot)
        transcript = await self._invoke_same_selection(db, selection, configuration, "viral_analysis", lambda: self.client.transcription(**self._call_parameters(snapshot, credential=credential, file_path=file_path)))
        await self._record_success(db, selection)
        return InvocationResult(content=transcript, model_resolution_snapshot=dict(selection.resolution_snapshot))

    async def generate_video(
        self, db: AsyncSession, task_id: UUID, prompt: str, *, seconds: int, image_urls: list[str],
    ) -> InvocationResult:
        selection, credential = await self._selection_and_credential(db, task_id, "clip_video")
        configuration = selection.model_configuration
        snapshot = dict(selection.resolution_snapshot)
        maximum = int((snapshot.get("constraints") or {}).get("max_duration_seconds", seconds))
        if seconds > maximum:
            raise ModelAvailabilityFailure("Requested clip duration exceeds the frozen model constraint")
        video = await self._invoke_same_selection(db, selection, configuration, "clip_video", lambda: self.client.video(**self._call_parameters(snapshot, credential=credential, prompt=prompt, seconds=seconds, image_urls=image_urls)))
        await self._record_success(db, selection)
        return InvocationResult(content=video, model_resolution_snapshot=dict(selection.resolution_snapshot))
