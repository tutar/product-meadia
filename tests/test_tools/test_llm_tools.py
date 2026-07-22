import pytest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.llm_tools import llm_chat, analyze_video_structure


@pytest.mark.asyncio
async def test_llm_chat_calls_litellm():
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "Generated response"

    mock_create = AsyncMock(return_value=mock_resp)
    with patch("src.tools.llm_tools.client.chat.completions.create", mock_create):
        result = await llm_chat("scriptwriter", "You are helpful.", "Write a script", temperature=0.7)
        assert result == "Generated response"
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_task_scoped_llm_chat_records_an_adapter_snapshot():
    """Resolved snapshots use adapter; provider is a legacy optional alias."""
    @asynccontextmanager
    async def session():
        yield object()

    class Boundary:
        async def complete(self, *_args, **_kwargs):
            return SimpleNamespace(
                content="Generated response",
                model_resolution_snapshot={"adapter": "openai", "model_id": "deepseek-v4-flash"},
            )

    recorder = AsyncMock()
    with patch("src.tools.llm_tools.AsyncSessionLocal", lambda: session()), \
         patch("src.tools.llm_tools.ModelInvocationBoundary", Boundary), \
         patch("src.tools.llm_tools.record_generation", recorder):
        result = await llm_chat("scriptwriter", "You are helpful.", "Write a script", task_id="00000000-0000-0000-0000-000000000001", model_stage="creative_planning")

    assert result == "Generated response"
    assert recorder.await_args.args[:2] == ("openai", "deepseek-v4-flash")


@pytest.mark.asyncio
async def test_analyze_video_structure_parses_json():
    json_output = '{"script_structure": {"hook": "test"}, "shot_list": [], "style_params": {}}'
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json_output

    mock_create = AsyncMock(return_value=mock_resp)
    with patch("src.tools.llm_tools.client.chat.completions.create", mock_create):
        result = await analyze_video_structure("Some transcript text")
        assert result["script_structure"] == {"hook": "test"}
        assert result["shot_list"] == []


@pytest.mark.asyncio
async def test_analyze_video_structure_strips_code_fences():
    json_output = "```json\n{\"script_structure\": {\"hook\": \"x\"}, \"shot_list\": [], \"style_params\": {}}\n```"
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json_output

    mock_create = AsyncMock(return_value=mock_resp)
    with patch("src.tools.llm_tools.client.chat.completions.create", mock_create):
        result = await analyze_video_structure("Transcript")
        assert result["script_structure"] == {"hook": "x"}
