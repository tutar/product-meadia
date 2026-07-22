"""Agnes Video V2.0's asynchronous video-generation protocol."""
import asyncio
from ipaddress import ip_address
from urllib.parse import urlparse

import httpx


class AgnesVideoV2Failure(RuntimeError):
    """A safe, provider-independent failure summary for Agnes invocation."""


class AgnesVideoV2Client:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, poll_interval_seconds: float = 10):
        self._transport = transport
        self._poll_interval_seconds = poll_interval_seconds

    async def generate(
        self, *, api_base: str, model_id: str, credential: str | None, prompt: str,
        seconds: int, image_urls: list[str],
    ) -> bytes:
        for image_url in image_urls:
            parsed = urlparse(image_url)
            hostname = parsed.hostname
            if parsed.scheme != "https" or not hostname:
                raise AgnesVideoV2Failure("Agnes keyframes must use publicly reachable HTTPS URLs")
            try:
                if ip_address(hostname).is_private or ip_address(hostname).is_loopback:
                    raise AgnesVideoV2Failure("Agnes keyframes must use publicly reachable HTTPS URLs")
            except ValueError:
                if hostname == "localhost" or hostname.endswith(".local") or hostname.endswith(".internal"):
                    raise AgnesVideoV2Failure("Agnes keyframes must use publicly reachable HTTPS URLs")
        base = api_base.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        payload = {
            "model": model_id,
            "prompt": prompt,
            "width": 1152,
            "height": 768,
            "num_frames": seconds * 24 + 1,
            "frame_rate": 24,
        }
        if len(image_urls) == 1:
            payload["image"] = image_urls[0]
        elif len(image_urls) > 1:
            payload["extra_body"] = {"image": image_urls, "mode": "keyframes"}

        timeout = httpx.Timeout(360, connect=10)
        async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
            try:
                created = await client.post(f"{base}/v1/videos", headers=headers, json=payload)
                created.raise_for_status()
                task = created.json()
                video_id = task.get("video_id") or task.get("id")
                if not video_id:
                    raise AgnesVideoV2Failure("Agnes did not return a video identifier")
                while True:
                    await asyncio.sleep(self._poll_interval_seconds)
                    result = await client.get(f"{base}/agnesapi", headers=headers, params={"video_id": video_id})
                    result.raise_for_status()
                    body = result.json()
                    if body.get("status") == "completed":
                        output_url = (body.get("metadata") or {}).get("url")
                        if not output_url:
                            raise AgnesVideoV2Failure("Agnes completed without a video output")
                        output = await client.get(output_url)
                        output.raise_for_status()
                        return output.content
                    if body.get("status") == "failed":
                        raise AgnesVideoV2Failure("Agnes video generation failed")
            except AgnesVideoV2Failure:
                raise
            except httpx.HTTPError as error:
                raise AgnesVideoV2Failure("Agnes video service request failed") from error
