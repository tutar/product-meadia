import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.video_gen import generate_video


def _get_side_effect():
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
    get_mock = AsyncMock(side_effect=_get_side_effect())

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
async def test_generate_video_single_image():
    """Single image: image_url set, no keyframes mode."""
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"id": "vid_456", "status": "queued"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(side_effect=_get_side_effect())

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            with patch("tempfile.NamedTemporaryFile", MagicMock()):
                with patch("builtins.open", MagicMock()):
                    url = await generate_video("Single img", image_urls=["https://img.example.com/1.png"])
                    assert url.endswith(".mp4")
                    json_body = post_mock.call_args.kwargs["json"]
                    assert json_body["image"] == "https://img.example.com/1.png"
                    assert "mode" not in json_body


@pytest.mark.asyncio
async def test_generate_video_embeds_private_rustfs_image():
    mock_create = MagicMock()
    mock_create.raise_for_status = MagicMock()
    mock_create.json.return_value = {"id": "vid_private", "status": "queued"}

    mock_image = MagicMock()
    mock_image.raise_for_status = MagicMock()
    mock_image.headers = {"content-type": "image/png"}
    mock_image.content = b"private-png"

    post_mock = AsyncMock(return_value=mock_create)
    poll_mock = AsyncMock(side_effect=_get_side_effect())

    async def get_mock(url, **kwargs):
        if url.startswith("http://rustfs:8001/"):
            return mock_image
        return await poll_mock(url, **kwargs)

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            with patch("tempfile.NamedTemporaryFile", MagicMock()):
                with patch("builtins.open", MagicMock()):
                    await generate_video(
                        "Private image",
                        image_urls=["http://rustfs:8001/product-media/image.png?signature=secret"],
                    )

    assert post_mock.call_args.kwargs["json"]["image"] == "data:image/png;base64,cHJpdmF0ZS1wbmc="


@pytest.mark.asyncio
async def test_generate_video_keyframe_mode():
    """2+ images: keyframes mode with image list."""
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status = MagicMock()
    mock_resp1.json.return_value = {"id": "vid_789", "status": "queued"}

    post_mock = AsyncMock(return_value=mock_resp1)
    get_mock = AsyncMock(side_effect=_get_side_effect())

    with patch("src.tools.video_gen.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        mock_client.return_value.__aenter__.return_value.get = get_mock
        with patch("src.tools.video_gen.asyncio.sleep", new_callable=AsyncMock):
            with patch("tempfile.NamedTemporaryFile", MagicMock()):
                with patch("builtins.open", MagicMock()):
                    imgs = ["https://img.example.com/1.png", "https://img.example.com/2.png"]
                    url = await generate_video("Keyframe", image_urls=imgs)
                    assert url.endswith(".mp4")
                    json_body = post_mock.call_args.kwargs["json"]
                    assert json_body["image"] == imgs
                    assert json_body["mode"] == "keyframes"


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
