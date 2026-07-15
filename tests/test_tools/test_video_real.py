"""Integration test: requires LiteLLM + Agnes Video on localhost:4000"""
import os, pytest
from src.tools.video_gen import generate_video


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_video_real_text_to_video():
    url = await generate_video("A luxury perfume bottle on a dark marble surface, soft golden light, cinematic")
    assert url
    assert os.path.exists(url)
    size = os.path.getsize(url)
    assert size > 5000, f"Video file too small: {size} bytes"
