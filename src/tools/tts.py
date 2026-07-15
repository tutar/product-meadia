import tempfile
import os
from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async

client = AsyncOpenAI(base_url=settings.voxcpm2_base_url, api_key="not-needed")


@retry_async(max_attempts=3)
@observe(name="generate_tts")
async def generate_tts(text: str) -> dict:
    """Generate TTS audio via VoxCPM2 OpenAI-compatible /v1/audio/speech.

    Returns dict with audio_url (local file path or RustFS URL) and words (empty
    list — VoxCPM2 does not provide word-level timestamps; use FunASR
    post-processing when needed).
    """
    response = await client.audio.speech.create(
        model="openbmb/VoxCPM2",
        input=text,
        voice="default",
    )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(response.content)
        audio_path = f.name

    return {
        "audio_url": audio_path,
        "words": [],
    }
