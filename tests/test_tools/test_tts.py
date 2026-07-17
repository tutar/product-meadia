from io import BytesIO
import wave

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.tts import generate_tts


@pytest.mark.asyncio
async def test_generate_tts_returns_audio_path():
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\0\0" * 12000)
    mock_response = MagicMock()
    mock_response.content = buffer.getvalue()

    mock_create = AsyncMock(return_value=mock_response)
    with patch("src.tools.tts.client.audio.speech.create", mock_create):
        result = await generate_tts("Hello")
        assert result["audio_url"].endswith(".wav")
        assert result["words"] == []
        assert result["tts_duration_seconds"] == 0.5
        mock_create.assert_called_once_with(model="voxcpm2", input="Hello", voice="default")


@pytest.mark.asyncio
async def test_generate_tts_retries_then_raises():
    mock_create = AsyncMock(side_effect=Exception("TTS down"))
    with patch("src.tools.tts.client.audio.speech.create", mock_create):
        with pytest.raises(Exception):
            await generate_tts("test")
        assert mock_create.call_count == 3
