"""Integration tests: require LiteLLM + Agnes Image running on localhost:4000"""
import pytest
from src.tools.image_gen import generate_image


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_image_real_agnes():
    url = await generate_image("A luxury perfume bottle on a marble surface, cinematic lighting, minimalist")
    assert url
    assert url.startswith("http")
    assert len(url) > 20
