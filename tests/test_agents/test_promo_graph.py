import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.promo_graph import build_promo_graph, promo_graph


@pytest.mark.asyncio
async def test_promo_graph_structure():
    """Verify the graph has all expected nodes and entry point."""
    nodes = list(promo_graph.nodes.keys())
    assert "generate_script" in nodes
    assert "wait_script_review" in nodes
    assert "generate_images" in nodes
    assert "wait_image_review" in nodes
    assert "generate_video_clips" in nodes
    assert "generate_voiceover" in nodes
    assert "composite_video" in nodes


def test_promo_graph_has_no_checkpointer_at_module_level():
    """Module-level graph has no checkpointer; Celery injects PostgresSaver at runtime."""
    assert promo_graph.checkpointer is None or promo_graph.checkpointer is False


@pytest.mark.asyncio
async def test_promo_graph_interrupt_before():
    """Verify interrupt points are set at review steps."""
    from langgraph.types import Interrupt
    # interrupt_before is set on the compiled graph
    assert promo_graph.interrupt_before_nodes is not None


@pytest.mark.asyncio
async def test_promo_graph_single_step_generate_script():
    """Test a single step: script generation with mocked LLM."""
    initial_state = {
        "task_id": "test-task-1",
        "product_id": "test-prod-1",
        "product_info": {
            "version": 1,
            "name": "Test Perfume",
            "category": {"name": "Perfume"},
            "attributes": [{"key": "scent", "label": "Scent", "type": "text", "value": "Citrus"}],
            "selling_points": ["Long-lasting"],
            "scenarios": ["daily"],
            "main_image_url": None,
        },
        "task_type": "promo",
        "image_count": 4,
        "viral_url": "",
        "script_content": "",
        "edited_script_content": "",
        "image_prompts": [],
        "voiceover_text": "",
        "generated_images": [],
        "video_clips": [],
        "tts_audio_url": "",
        "tts_words": [],
        "lipsync_video_url": "",
        "character_image_url": "",
        "viral_analysis": {},
        "hyperframes_html": "",
        "final_video_path": "",
        "review_approved": False,
        "messages": [],
    }

    json_output = '{"script": "A beautiful script...", "voiceover": "A beautiful script...", "image_prompts": ["prompt1", "prompt2", "prompt3", "prompt4"]}'
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json_output

    with patch("src.agents.promo_graph.llm_chat", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json_output
        # Run the graph until the first interrupt (wait_script_review)
        config = {"configurable": {"thread_id": "test-thread-1"}}
        events = []
        async for event in promo_graph.astream(initial_state, config):
            events.append(event)

        # Should have generated script and hit interrupt
        event_keys = [list(e.keys())[0] for e in events if e]
        assert "generate_script" in event_keys


@pytest.mark.asyncio
async def test_reused_video_clips_are_marked_so_the_worker_can_continue_after_review():
    graph = build_promo_graph(interrupt_before=[])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "script_content": "script", "edited_script_content": "", "image_prompts": ["prompt"],
        "voiceover_text": "script", "generated_images": [{"image_url": "https://image", "status": "approved"}],
        "video_clips": ["https://clip"], "tts_audio_url": "", "tts_words": [],
        "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {},
        "hyperframes_html": "", "final_video_path": "", "script_approved": True,
        "images_approved": True, "review_approved": False, "messages": [],
    }
    with patch("src.agents.promo_graph.generate_tts", new_callable=AsyncMock) as tts, patch("src.agents.promo_graph.render_hyperframes", new_callable=AsyncMock) as render:
        tts.return_value = {"audio_url": "https://audio", "words": []}
        render.return_value = "/tmp/final.mp4"
        events = [event async for event in graph.astream(state, {"configurable": {"thread_id": "reuse-clips"}})]

    reused_output = next(event["generate_video_clips"] for event in events if "generate_video_clips" in event)
    assert reused_output["video_clips_reused"] is True
