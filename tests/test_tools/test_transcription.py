import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.transcription import transcribe_audio


@pytest.mark.asyncio
async def test_transcribe_audio_returns_text():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"text": "This is the transcribed video script."}

    post_mock = AsyncMock(return_value=mock_resp)
    with patch("src.tools.transcription.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        text = await transcribe_audio("https://video.example.com/source.mp4")
        assert text == "This is the transcribed video script."
