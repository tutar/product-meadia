"""Integration: LiteLLM → VoxCPM2 on localhost:4000"""
import pytest, os
from src.tools.tts import generate_tts

@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_tts_real_voxcpm2():
    result = await generate_tts("你好世界，TTS集成测试。")
    assert os.path.exists(result["audio_url"])
    assert os.path.getsize(result["audio_url"]) > 1000
