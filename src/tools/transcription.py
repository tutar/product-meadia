import httpx
import tempfile
import os
from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@retry_async(max_attempts=3)
@observe(name="transcribe_audio")
async def transcribe_audio(video_url: str) -> str:
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
        with open(tmp_path, "rb") as audio_file:
            result = await client.audio.transcriptions.create(
                model="sensevoice",
                file=audio_file,
            )
        return result.text
    finally:
        os.unlink(tmp_path)
