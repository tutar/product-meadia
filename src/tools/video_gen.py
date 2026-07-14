import asyncio
import httpx
from src.config import settings
from langfuse import observe

HEADERS = {"Authorization": f"Bearer {settings.agnes_video_api_key}"}


@observe(name="generate_video")
async def generate_video(prompt: str, image_urls: list[str] | None = None) -> str:
    payload = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": 1152,
        "height": 768,
        "num_frames": 121,
        "frame_rate": 24,
    }
    if image_urls:
        payload["extra_body"] = {"image": image_urls, "mode": "keyframes"}

    async with httpx.AsyncClient(timeout=360) as client:
        resp = await client.post(
            f"{settings.agnes_video_base_url}/v1/videos", headers=HEADERS, json=payload
        )
        resp.raise_for_status()
        video_id = resp.json()["video_id"]

        while True:
            await asyncio.sleep(10)
            result = await client.get(
                f"{settings.agnes_video_base_url}/agnesapi",
                params={"video_id": video_id},
                headers=HEADERS,
            )
            result.raise_for_status()
            data = result.json()
            if data["status"] == "completed":
                return data["url"]
            if data["status"] == "failed":
                raise RuntimeError(f"Video generation failed: {data.get('error')}")
