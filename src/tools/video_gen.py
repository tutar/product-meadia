import asyncio
import httpx
from src.config import settings
from langfuse import observe

HEADERS = {
    "Authorization": f"Bearer {settings.litellm_api_key}",
    "Content-Type": "application/json",
}


@observe(name="generate_video")
async def generate_video(prompt: str, image_urls: list[str] | None = None) -> str:
    """Generate video via LiteLLM-proxied Agnes Video V2.0.

    Uses OpenAI-compatible /v1/videos endpoint (create + poll).
    """
    payload = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": 1152,
        "height": 768,
        "num_frames": 121,
        "frame_rate": 24,
    }
    if image_urls:
        payload["image"] = image_urls[0]
        payload["mode"] = "keyframes"

    async with httpx.AsyncClient(timeout=httpx.Timeout(360, connect=10)) as client:
        base = settings.litellm_base_url

        # Create video task
        resp = await client.post(f"{base}/v1/videos", headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()
        video_id = data["id"]

        # Poll until complete
        while True:
            await asyncio.sleep(10)
            resp = await client.get(f"{base}/v1/videos/{video_id}", headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            if data["status"] == "completed":
                return data["url"]
            if data["status"] == "failed":
                raise RuntimeError(f"Video generation failed: {data.get('error')}")
