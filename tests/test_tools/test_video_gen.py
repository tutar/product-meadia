import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.video_gen import generate_video


@pytest.mark.asyncio
async def test_generate_video_text_to_video():
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"video_id": "task_123", "status": "queued"}

    mock_resp2 = MagicMock()
    mock_resp2.raise_for_status = MagicMock()
    mock_resp2.json.return_value = {"status": "completed", "url": "https://video.example.com/output.mp4"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(return_value=mock_resp2)

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            url = await generate_video("A cinematic perfume ad")
            assert url == "https://video.example.com/output.mp4"
            assert post_mock.call_count == 1


@pytest.mark.asyncio
async def test_generate_video_keyframe_mode():
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"video_id": "task_456", "status": "queued"}

    mock_resp2 = MagicMock()
    mock_resp2.raise_for_status = MagicMock()
    mock_resp2.json.return_value = {"status": "completed", "url": "https://video.example.com/keyframe.mp4"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(return_value=mock_resp2)

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            url = await generate_video("Keyframe animation", image_urls=["https://img.example.com/1.png"])
            assert url == "https://video.example.com/keyframe.mp4"
            assert "extra_body" in post_mock.call_args.kwargs["json"]
            assert post_mock.call_args.kwargs["json"]["extra_body"]["mode"] == "keyframes"


@pytest.mark.asyncio
async def test_generate_video_failed_status():
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"video_id": "task_fail", "status": "queued"}

    mock_resp2 = MagicMock()
    mock_resp2.raise_for_status = MagicMock()
    mock_resp2.json.return_value = {"status": "failed", "error": "Generation timeout"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(return_value=mock_resp2)

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="Video generation failed"):
                await generate_video("test")
