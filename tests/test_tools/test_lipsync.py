import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.lipsync import run_lipsync


@pytest.mark.asyncio
async def test_run_lipsync_returns_video_url():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"video_url": "https://video.example.com/lipsync.mp4"}

    post_mock = AsyncMock(return_value=mock_resp)
    with patch("src.tools.lipsync.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        url = await run_lipsync("https://img.example.com/char.png", "https://audio.example.com/voice.wav")
        assert url == "https://video.example.com/lipsync.mp4"
        call_args = post_mock.call_args
        assert call_args.kwargs["json"]["image_url"] == "https://img.example.com/char.png"
        assert call_args.kwargs["json"]["audio_url"] == "https://audio.example.com/voice.wav"
