import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.tts import generate_tts


@pytest.mark.asyncio
async def test_generate_tts_returns_audio_url_and_words():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "audio_url": "https://audio.example.com/voice.wav",
        "words": [{"word": "Hello", "start": 0.0, "end": 0.5}, {"word": "World", "start": 0.5, "end": 1.0}],
    }

    post_mock = AsyncMock(return_value=mock_resp)
    with patch("src.tools.tts.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        result = await generate_tts("Hello World")
        assert result["audio_url"] == "https://audio.example.com/voice.wav"
        assert len(result["words"]) == 2
        assert result["words"][0]["word"] == "Hello"


@pytest.mark.asyncio
async def test_generate_tts_no_timestamps():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"audio_url": "https://audio.example.com/voice2.wav"}

    post_mock = AsyncMock(return_value=mock_resp)
    with patch("src.tools.tts.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = post_mock
        result = await generate_tts("Test")
        assert result["audio_url"] == "https://audio.example.com/voice2.wav"
        assert result["words"] == []
