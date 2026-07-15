import asyncio
import tempfile
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
        if len(image_urls) >= 2:
            payload["image"] = image_urls
            payload["mode"] = "keyframes"
        else:
            payload["image"] = image_urls[0]

    async with httpx.AsyncClient(timeout=httpx.Timeout(360, connect=10)) as client:
        base = settings.litellm_base_url

        # Create video task
        # Create with rate limit handling (1 req/min)
        for attempt in range(3):
            resp = await client.post(f"{base}/videos", headers=HEADERS, json=payload)
            if resp.status_code == 429:
                await asyncio.sleep(65)  # Wait for rate limit window
                continue
            resp.raise_for_status()
            break
        data = resp.json()
        video_id = data["id"]

        # Poll until complete
        while True:
            await asyncio.sleep(10)
            resp = await client.get(f"{base}/videos/{video_id}", headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            if data["status"] == "completed":
                # Fetch video content and save to temp file
                vresp = await client.get(f"{base}/videos/{video_id}/content", headers=HEADERS)
                vresp.raise_for_status()
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                    f.write(vresp.content)
                    return f.name
            if data["status"] == "failed":
                raise RuntimeError(f"Video generation failed: {data.get('error')}")
