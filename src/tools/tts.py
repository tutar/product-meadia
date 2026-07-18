import tempfile
import wave
from io import BytesIO
from pathlib import Path
import re
import subprocess
from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


def wav_duration_seconds(audio: bytes) -> float:
    """Return the intrinsic duration of provider WAV bytes."""
    with wave.open(BytesIO(audio), "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate()


def estimate_speech_duration_seconds(text: str) -> float:
    """Estimate a natural narration duration without slowing speech unnaturally."""
    english_words = len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", text))
    cjk_characters = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    return max(0.5, english_words / 2.5 + cjk_characters / 4.5)


def _atempo_filter(tempo: float) -> str:
    factors: list[float] = []
    while tempo > 2:
        factors.append(2)
        tempo /= 2
    while tempo < 0.5:
        factors.append(0.5)
        tempo /= 0.5
    factors.append(tempo)
    return ",".join(f"atempo={factor:.6g}" for factor in factors)


def normalize_tts_audio(audio: bytes, target_duration_seconds: float) -> bytes:
    """Speed up an unusually slow WAV without changing pitch.

    The provider occasionally emits speech far below a natural narration rate.
    `atempo` preserves pitch and supports chained filters for large corrections.
    """
    source_duration = wav_duration_seconds(audio)
    if target_duration_seconds <= 0 or source_duration <= target_duration_seconds * 1.05:
        return audio
    tempo = source_duration / target_duration_seconds
    source_path = output_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as source_file:
            source_file.write(audio)
            source_path = source_file.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output_file:
            output_path = output_file.name
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", source_path, "-filter:a", _atempo_filter(tempo), "-c:a", "pcm_s16le", output_path],
            check=True,
        )
        return Path(output_path).read_bytes()
    finally:
        for path in (source_path, output_path):
            if path:
                Path(path).unlink(missing_ok=True)


@retry_async(max_attempts=3)
@observe(name="generate_tts")
async def generate_tts(text: str, *, target_duration_seconds: float | None = None) -> dict:
    """Generate TTS audio via LiteLLM (VoxCPM2), OpenAI-compatible /v1/audio/speech."""
    response = await client.audio.speech.create(
        model="voxcpm2",
        input=text,
        voice="default",
    )
    audio = response.content
    target_duration = target_duration_seconds or estimate_speech_duration_seconds(text)
    audio = normalize_tts_audio(audio, target_duration)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio)
        audio_path = f.name
    return {
        "audio_url": audio_path,
        "words": [],
        "tts_duration_seconds": wav_duration_seconds(audio),
    }
