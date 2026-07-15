"""Integration tests: require LiteLLM running on localhost:4000"""
import pytest
from src.tools.llm_tools import llm_chat


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llm_chat_real_scriptwriter():
    result = await llm_chat(
        "scriptwriter",
        "You are a helpful assistant. Reply in JSON only.",
        'Say hello. Return ONLY: {"greeting": "hello"}',
        temperature=0.7,
    )
    assert len(result) > 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llm_chat_real_researcher():
    result = await llm_chat(
        "researcher",
        "Be concise. Reply in one sentence.",
        "What makes a short video go viral?",
        temperature=0.2,
    )
    assert len(result) > 10
