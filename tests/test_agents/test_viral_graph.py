import pytest
from unittest.mock import AsyncMock, patch
from src.agents.viral_graph import viral_graph


@pytest.mark.asyncio
async def test_viral_retry_reuses_completed_media():
    from src.agents.viral_graph import build_viral_graph

    graph = build_viral_graph(interrupt_before=[])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "viral",
        "product_info": {"name": "Product"}, "image_count": 1,
        "viral_url": "source.mp4", "viral_analysis": {"done": True},
        "script_content": "script", "edited_script_content": "",
        "voiceover_text": "script", "image_prompts": ["prompt"],
        "generated_images": [{"image_url": "image.png", "status": "approved", "sort_order": 0}],
        "video_clips": ["clip.mp4"], "tts_audio_url": "audio.mp3",
        "tts_words": [{"word": "hi", "start": 0, "end": 1}],
        "lipsync_video_url": "", "character_image_url": "",
        "hyperframes_html": "", "final_video_path": "",
        "review_approved": True, "script_approved": True, "images_approved": True,
        "messages": [],
    }
    with (
        patch("src.agents.viral_graph.transcribe_audio", new_callable=AsyncMock) as transcribe,
        patch("src.agents.viral_graph.generate_image", new_callable=AsyncMock) as image,
        patch("src.agents.viral_graph.generate_video", new_callable=AsyncMock) as video,
        patch("src.agents.viral_graph.generate_tts", new_callable=AsyncMock) as tts,
        patch("src.agents.viral_graph.render_hyperframes", new_callable=AsyncMock, return_value="final.mp4") as render,
    ):
        await graph.ainvoke(state)

    transcribe.assert_not_called()
    image.assert_not_called()
    video.assert_not_called()
    tts.assert_not_called()
    html = render.await_args.args[0]
    assert '<video id="clip-0" class="clip"' in html
    assert 'preload="auto"' in html
    assert '<audio id="voiceover" src="audio.mp3" data-start="0" data-duration=' not in html
    assert '.composition { position:relative; width:1152px; height:768px; overflow:hidden; }' in html


def test_viral_graph_structure():
    nodes = list(viral_graph.nodes.keys())
    assert "analyze_source" in nodes
    assert "wait_viral_confirm" in nodes
    assert "generate_rewritten_script" in nodes
    assert "wait_script_review" in nodes
    assert "generate_images" in nodes
    assert "wait_image_review" in nodes
    assert "generate_clips_and_voiceover" in nodes
    assert "composite" in nodes


def test_viral_graph_has_no_checkpointer_at_module_level():
    assert viral_graph.checkpointer is None or viral_graph.checkpointer is False


def test_viral_graph_interrupt_count():
    assert len(viral_graph.interrupt_before_nodes) == 3
