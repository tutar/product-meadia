import asyncio
import base64
import tempfile
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from src.config import settings
from langfuse import observe
from src.tasks.generation_records import record_generation

HEADERS = {
    "Authorization": f"Bearer {settings.litellm_api_key}",
    "Content-Type": "application/json",
}


@dataclass(frozen=True)
class VideoModelCapability:
    model: str
    max_duration_seconds: int
    max_keyframes: int


# Keep this capability beside the provider request.  Planning must use the
# same limit that generation can actually honour.
SELECTED_VIDEO_MODEL = VideoModelCapability(
    model="agnes-video-v2.0", max_duration_seconds=5, max_keyframes=2,
)


def _is_private_image_url(url: str) -> bool:
    return urlparse(url).hostname in {"rustfs", "localhost", "127.0.0.1"}


async def _provider_image_urls(client: httpx.AsyncClient, image_urls: list[str]) -> list[str]:
    provider_urls = []
    for image_url in image_urls:
        if not _is_private_image_url(image_url):
            provider_urls.append(image_url)
            continue
        response = await client.get(image_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise ValueError(f"Private media URL did not return an image: {image_url}")
        encoded = base64.b64encode(response.content).decode("ascii")
        provider_urls.append(f"data:{content_type};base64,{encoded}")
    return provider_urls


@observe(name="generate_video")
async def generate_video(prompt: str, image_urls: list[str] | None = None) -> str:
    """Generate video via LiteLLM-proxied Agnes Video V2.0.

    Uses OpenAI-compatible /v1/videos endpoint (create + poll).
    """
    payload = {
        "model": SELECTED_VIDEO_MODEL.model,
        "prompt": prompt,
        "width": 1152,
        "height": 768,
        "num_frames": 121,
        "frame_rate": 24,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(360, connect=10)) as client:
        base = settings.litellm_base_url
        if image_urls:
            provider_urls = await _provider_image_urls(client, image_urls)
            if len(provider_urls) >= 2:
                payload["image"] = provider_urls
                payload["mode"] = "keyframes"
            else:
                payload["image"] = provider_urls[0]

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
                    await record_generation(
                        "litellm", SELECTED_VIDEO_MODEL.model,
                        {"width": 1152, "height": 768, "num_frames": 121, "frame_rate": 24},
                        {"prompt": prompt, "keyframe_count": len(image_urls or [])},
                        {"result": "video generated"},
                        {"model": SELECTED_VIDEO_MODEL.model, "prompt": prompt, "keyframe_count": len(image_urls or []), "mode": payload.get("mode")},
                    )
                    return f.name
            if data["status"] == "failed":
                raise RuntimeError(f"Video generation failed: {data.get('error')}")
