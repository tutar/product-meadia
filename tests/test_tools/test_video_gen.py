import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.video_gen import generate_video


def _get_side_effect(status_url_prefix):
    """Return different responses based on URL: status check vs content download."""
    mock_status = MagicMock()
    mock_status.raise_for_status = MagicMock()
    mock_status.json.return_value = {"status": "completed"}

    mock_content = MagicMock()
    mock_content.raise_for_status = MagicMock()
    mock_content.content = b"fake-mp4-data"

    async def side_effect(url, **kwargs):
        if "/content" in url:
            return mock_content
        return mock_status

    return side_effect


@pytest.mark.asyncio
async def test_generate_video_text_to_video():
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"id": "vid_123", "status": "queued"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(side_effect=_get_side_effect(""))

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            with patch("tempfile.NamedTemporaryFile", MagicMock()):
                with patch("builtins.open", MagicMock()):
                    url = await generate_video("A cinematic perfume ad")
                    assert url.endswith(".mp4")
                    assert post_mock.call_count == 1


@pytest.mark.asyncio
async def test_generate_video_keyframe_mode():
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"id": "vid_456", "status": "queued"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(side_effect=_get_side_effect(""))

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            with patch("tempfile.NamedTemporaryFile", MagicMock()):
                with patch("builtins.open", MagicMock()):
                    url = await generate_video("Keyframe", image_urls=["https://img.example.com/1.png"])
                    assert url.endswith(".mp4")
                    assert post_mock.call_args.kwargs["json"]["mode"] == "keyframes"


@pytest.mark.asyncio
async def test_generate_video_failed_status():
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"id": "vid_fail", "status": "queued"}

    mock_status = MagicMock()
    mock_status.raise_for_status = MagicMock()
    mock_status.json.return_value = {"status": "failed", "error": "Generation timeout"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(return_value=mock_status)

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="Video generation failed"):
                await generate_video("test")
