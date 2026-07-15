import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.tts import generate_tts


@pytest.mark.asyncio
async def test_generate_tts_returns_audio_path():
    mock_response = MagicMock()
    mock_response.content = b"RIFF...WAV data..."

    mock_create = AsyncMock(return_value=mock_response)
    with patch("src.tools.tts.client.audio.speech.create", mock_create):
        result = await generate_tts("Hello World")
        assert result["audio_url"].endswith(".wav")
        assert result["words"] == []
        mock_create.assert_called_once_with(
            model="openbmb/VoxCPM2",
            input="Hello World",
            voice="default",
        )


@pytest.mark.asyncio
async def test_generate_tts_retries_then_raises():
    mock_create = AsyncMock(side_effect=Exception("TTS down"))
    with patch("src.tools.tts.client.audio.speech.create", mock_create):
        with pytest.raises(Exception):
            await generate_tts("test")
        assert mock_create.call_count == 3
