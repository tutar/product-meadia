import httpx
from src.config import settings
from langfuse.decorators import observe


@observe(name="transcribe_audio")
async def transcribe_audio(video_url: str) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{settings.funasr_base_url}/audio/transcriptions",
            data={"file": video_url, "model": "sensevoice"},
        )
        resp.raise_for_status()
        return resp.json()["text"]
