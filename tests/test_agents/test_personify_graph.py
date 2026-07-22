import pytest
from unittest.mock import AsyncMock, patch
from src.agents.personify_graph import personify_graph


@pytest.mark.asyncio
async def test_personify_retry_reuses_completed_media():
    from src.agents.personify_graph import build_personify_graph

    graph = build_personify_graph(interrupt_before=[])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "personify",
        "product_info": {"name": "Product", "scenarios": []}, "image_count": 1,
        "viral_url": "", "viral_analysis": {}, "script_content": "script",
        "edited_script_content": "", "voiceover_text": "script", "image_prompts": [],
        "generated_images": [], "video_clips": [], "tts_audio_url": "audio.mp3",
        "tts_words": [{"word": "hi", "start": 0, "end": 1}],
        "lipsync_video_url": "lipsync.mp4", "character_image_url": "character.png",
        "hyperframes_html": "", "final_video_path": "",
        "review_approved": True, "script_approved": True, "images_approved": True,
        "messages": [],
    }
    with (
        patch("src.agents.personify_graph.llm_chat", new_callable=AsyncMock) as llm,
        patch("src.agents.personify_graph.generate_image", new_callable=AsyncMock) as image,
        patch("src.agents.personify_graph.generate_tts", new_callable=AsyncMock) as tts,
        patch("src.agents.personify_graph.run_lipsync", new_callable=AsyncMock) as lipsync,
        patch("src.agents.personify_graph.render_hyperframes", new_callable=AsyncMock, return_value="final.mp4"),
    ):
        await graph.ainvoke(state)

    llm.assert_not_called()
    image.assert_not_called()
    tts.assert_not_called()
    lipsync.assert_not_called()


def test_personify_graph_structure():
    nodes = list(personify_graph.nodes.keys())
    assert "generate_character" in nodes
    assert "wait_character_review" in nodes
    assert "generate_script" in nodes
    assert "wait_script_review" in nodes
    assert "generate_voiceover" in nodes
    assert "wait_voice_review" in nodes
    assert "generate_lipsync" in nodes
    assert "composite" in nodes


def test_personify_graph_has_no_checkpointer_at_module_level():
    assert personify_graph.checkpointer is None or personify_graph.checkpointer is False


def test_personify_graph_interrupt_count():
    assert len(personify_graph.interrupt_before_nodes) == 2
