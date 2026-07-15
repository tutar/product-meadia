import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.tools.transcription import transcribe_audio


@pytest.mark.asyncio
async def test_transcribe_audio_returns_text():
    mock_transcription = MagicMock()
    mock_transcription.text = "This is transcribed text from the video."

    mock_create = AsyncMock(return_value=mock_transcription)
    mock_dl = MagicMock()
    mock_dl.content = b"fake audio"
    mock_dl_resp = MagicMock()
    mock_dl_resp.raise_for_status = MagicMock()
    mock_dl_resp.content = b"fake audio"

    with patch("src.tools.transcription.client.audio.transcriptions.create", mock_create):
        with patch("src.tools.transcription.httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_dl_resp)
            mock_client.return_value.__aenter__.return_value.get = mock_get
            with patch("builtins.open", MagicMock()):
                with patch("os.unlink"):
                    text = await transcribe_audio("https://example.com/video.mp4")
                    assert text == "This is transcribed text from the video."
                    mock_create.assert_called_once()
