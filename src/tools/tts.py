import tempfile
import wave
from io import BytesIO
from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


def wav_duration_seconds(audio: bytes) -> float:
    """Return the intrinsic duration of provider WAV bytes."""
    with wave.open(BytesIO(audio), "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate()


@retry_async(max_attempts=3)
@observe(name="generate_tts")
async def generate_tts(text: str) -> dict:
    """Generate TTS audio via LiteLLM (VoxCPM2), OpenAI-compatible /v1/audio/speech."""
    response = await client.audio.speech.create(
        model="voxcpm2",
        input=text,
        voice="default",
    )
    audio = response.content
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio)
        audio_path = f.name
    return {
        "audio_url": audio_path,
        "words": [],
        "tts_duration_seconds": wav_duration_seconds(audio),
    }
