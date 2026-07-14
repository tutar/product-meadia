import httpx
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async


@retry_async(max_attempts=3)
@observe(name="generate_tts")
async def generate_tts(text: str) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.voxcpm2_base_url}/v1/tts",
            json={"text": text, "return_timestamps": True},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "audio_url": data["audio_url"],
            "words": data.get("words", []),
        }
