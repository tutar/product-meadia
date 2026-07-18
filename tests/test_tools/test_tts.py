from io import BytesIO
import wave

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.tts import estimate_speech_duration_seconds, generate_tts


def test_estimated_speech_duration_uses_a_normal_narration_rate():
    assert estimate_speech_duration_seconds("one two three four five") == 2.0
    assert estimate_speech_duration_seconds("你好世界") == pytest.approx(4 / 4.5)


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
async def test_generate_tts_speeds_up_abnormally_slow_provider_audio():
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\0\0" * 48000)
    mock_response = MagicMock(content=buffer.getvalue())

    with patch("src.tools.tts.client.audio.speech.create", AsyncMock(return_value=mock_response)):
        result = await generate_tts("Hello", target_duration_seconds=0.5)

    assert result["tts_duration_seconds"] == pytest.approx(0.5, abs=0.03)


@pytest.mark.asyncio
async def test_generate_tts_retries_then_raises():
    mock_create = AsyncMock(side_effect=Exception("TTS down"))
    with patch("src.tools.tts.client.audio.speech.create", mock_create):
        with pytest.raises(Exception):
            await generate_tts("test")
        assert mock_create.call_count == 3
