import pytest
from openai import AsyncOpenAI
from src.config import settings

@pytest.mark.integration
@pytest.mark.asyncio
async def test_transcribe_audio_real_sensevoice():
    tts = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)
    resp = await tts.audio.speech.create(model="voxcpm2", input="你好世界这是集成测试", voice="default")
    stt_result = await tts.audio.transcriptions.create(model="sensevoice", file=("test.wav", resp.content, "audio/wav"))
    assert len(stt_result.text) > 0
