import httpx
from src.config import settings
from langfuse.decorators import observe


@observe(name="lipsync")
async def run_lipsync(image_url: str, audio_url: str) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{settings.latentsync_base_url}/v1/lipsync",
            json={"image_url": image_url, "audio_url": audio_url},
        )
        resp.raise_for_status()
        return resp.json()["video_url"]
