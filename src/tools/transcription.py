import httpx
import tempfile
import os
from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async
from src.database import AsyncSessionLocal
from src.services.model_invocation import ModelInvocationBoundary
from src.tasks.generation_records import record_generation

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@retry_async(max_attempts=3)
@observe(name="transcribe_audio")
async def transcribe_audio(video_url: str, *, task_id: str | None = None) -> str:
    """Transcribe audio via LiteLLM (FunASR/SenseVoice), OpenAI-compatible /v1/audio/transcriptions.

    Downloads media from URL first, then uploads to LiteLLM.
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as dl:
        dl_resp = await dl.get(video_url)
        dl_resp.raise_for_status()
        content = dl_resp.content

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        if task_id:
            from pathlib import Path
            from uuid import UUID
            async with AsyncSessionLocal() as db:
                resolved = await ModelInvocationBoundary().transcribe(db, UUID(task_id), Path(tmp_path))
            snapshot = resolved.model_resolution_snapshot
            provider, model, transcript = snapshot.get("provider") or snapshot["adapter"], snapshot["model_id"], resolved.content
        else:
            with open(tmp_path, "rb") as audio_file:
                result = await client.audio.transcriptions.create(model="sensevoice", file=audio_file)
            provider, model, transcript = "litellm", "sensevoice", result.text
        await record_generation(provider, model, {}, {"source_media": "provided"}, {"transcript": "generated"}, {"model": model})
        return transcript
    finally:
        os.unlink(tmp_path)
