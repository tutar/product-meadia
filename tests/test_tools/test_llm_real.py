"""Integration tests: require LiteLLM running on localhost:4000"""
import pytest
from src.tools.llm_tools import llm_chat


@pytest.mark.integration
@pytest.mark.skip(reason="LiteLLM DeepSeek API key needs updating in infra litellm/config.yaml")
@pytest.mark.asyncio
async def test_llm_chat_real_scriptwriter():
    result = await llm_chat(
        "scriptwriter",
        "You are a helpful assistant. Reply in JSON.",
        'Say hello. Return JSON: {"greeting": "..."}',
        temperature=0.7,
    )
    assert len(result) > 10


@pytest.mark.integration
@pytest.mark.skip(reason="LiteLLM DeepSeek API key needs updating in infra litellm/config.yaml")
@pytest.mark.asyncio
async def test_llm_chat_real_researcher():
    result = await llm_chat(
        "researcher",
        "You are a video analyst. Be concise.",
        "What are 3 key elements of a viral short video?",
        temperature=0.2,
    )
    assert len(result) > 20
