import pytest
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
