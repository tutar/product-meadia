import json

import httpx
import pytest

from src.services.agnes_video_v2 import AgnesVideoV2Client, AgnesVideoV2Failure


@pytest.mark.asyncio
async def test_agnes_video_v2_rejects_a_private_keyframe_url_before_creating_a_video():
    client = AgnesVideoV2Client(transport=httpx.MockTransport(lambda request: pytest.fail(f"Unexpected request: {request.url}")))

    with pytest.raises(AgnesVideoV2Failure, match="publicly reachable"):
        await client.generate(
            api_base="https://apihub.agnes-ai.com", model_id="agnes-video-v2.0", credential="byok",
            prompt="Animate the product", seconds=5, image_urls=["http://localhost:8001/private/keyframe.png"],
        )


@pytest.mark.asyncio
async def test_agnes_video_v2_creates_polls_and_downloads_a_video_candidate():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/v1/videos"
            assert json.loads(request.content) == {
                "model": "agnes-video-v2.0", "prompt": "Animate the product", "width": 1152,
                "height": 768, "num_frames": 121, "frame_rate": 24,
                "image": "https://storage.example/keyframe.png",
            }
            return httpx.Response(200, json={"video_id": "video-123", "status": "queued"})
        if request.url.host == "apihub.agnes-ai.com":
            assert request.url.path == "/agnesapi"
            assert request.url.params["video_id"] == "video-123"
            return httpx.Response(200, json={"status": "completed", "metadata": {"url": "https://output.agnes-ai.com/video.mp4"}})
        return httpx.Response(200, content=b"mp4-bytes")

    client = AgnesVideoV2Client(transport=httpx.MockTransport(respond), poll_interval_seconds=0)
    result = await client.generate(
        api_base="https://apihub.agnes-ai.com", model_id="agnes-video-v2.0", credential="byok",
        prompt="Animate the product", seconds=5, image_urls=["https://storage.example/keyframe.png"],
    )

    assert result == b"mp4-bytes"
    assert len(requests) == 3
