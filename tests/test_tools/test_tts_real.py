"""Integration test: requires VoxCPM2 running on localhost:8022"""
import pytest
import os
from src.tools.tts import generate_tts


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_tts_real_voxcpm2():
    result = await generate_tts("你好世界，这是集成测试。")
    assert "audio_url" in result
    assert os.path.exists(result["audio_url"])
    size = os.path.getsize(result["audio_url"])
    assert size > 1000, f"Audio file too small: {size} bytes"
    assert result["words"] == []
