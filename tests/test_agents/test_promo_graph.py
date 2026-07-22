import pytest
from openai import OpenAIError
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.promo_graph import build_promo_graph, clip_segments_for_shot_plan, composition_options, keyframes_for_segments, promo_graph


@pytest.mark.asyncio
async def test_promo_graph_structure():
    """Verify the graph has all expected nodes and entry point."""
    nodes = list(promo_graph.nodes.keys())
    assert "generate_creative_brief" in nodes
    assert "wait_creative_brief_review" in nodes
    assert "generate_script" in nodes
    assert "wait_script_review" in nodes
    assert "generate_shot_plan" in nodes
    assert "wait_shot_plan_review" in nodes
    assert "generate_images" in nodes
    assert "wait_image_review" in nodes
    assert "generate_video_clips" in nodes
    assert "generate_voiceover" in nodes
    assert "composite_video" in nodes
    assert "render_composition" in nodes


def test_promo_graph_has_no_checkpointer_at_module_level():
    """Module-level graph has no checkpointer; Celery injects PostgresSaver at runtime."""
    assert promo_graph.checkpointer is None or promo_graph.checkpointer is False


@pytest.mark.asyncio
async def test_composition_feedback_falls_back_when_optional_llm_adjustment_is_unavailable():
    state = {"review_feedback": [{"target_type": "composition", "content": "Make subtitles lower."}]}
    with patch("src.agents.promo_graph.llm_chat", new_callable=AsyncMock, side_effect=OpenAIError("invalid model")) as llm:
        assert await composition_options(state) == {"clip_duration": 5, "subtitle_offset": 10, "subtitle_size": 32}
    llm.assert_not_awaited()


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
            "creative_brief": {"core_promise": "test"},
            "creative_brief_approved": True,
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
        graph = build_promo_graph(interrupt_before=["wait_script_review"])
        async for event in graph.astream(initial_state, config):
            events.append(event)

        # Should have generated script and hit interrupt
        event_keys = [list(e.keys())[0] for e in events if e]
        assert "generate_script" in event_keys
        assert "Reviewer improvement guidance" not in mock_llm.await_args.args[2]


@pytest.mark.asyncio
async def test_script_review_feedback_is_passed_to_the_next_generation():
    graph = build_promo_graph(interrupt_before=["wait_script_review"])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "script_content": "", "edited_script_content": "", "image_prompts": [], "voiceover_text": "",
        "generated_images": [], "video_clips": [], "tts_audio_url": "", "tts_words": [],
        "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {},
            "hyperframes_html": "", "final_video_path": "", "review_approved": False,
            "creative_brief": {"core_promise": "test"}, "creative_brief_approved": True,
            "script_approved": False, "images_approved": False, "character_approved": False,
        "review_feedback": [{"target_type": "script", "content": "Use a clearer opening hook."}], "messages": [],
    }
    response = '{"script": "script", "voiceover": "script", "image_prompts": ["prompt"]}'
    with patch("src.agents.promo_graph.llm_chat", new_callable=AsyncMock) as llm:
        llm.return_value = response
        async for _ in graph.astream(state, {"configurable": {"thread_id": "feedback"}}):
            pass
    assert "Use a clearer opening hook." in llm.await_args.args[2]


@pytest.mark.asyncio
async def test_approved_script_generates_shot_plan_before_images():
    graph = build_promo_graph(interrupt_before=["wait_shot_plan_review"])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "creative_brief": {"core_promise": "calm"}, "creative_brief_approved": True,
        "script_content": "script", "edited_script_content": "", "image_prompts": ["legacy prompt"], "voiceover_text": "voiceover",
        "shot_plan": [], "shot_plan_approved": False,
        "generated_images": [], "video_clips": [], "tts_audio_url": "", "tts_words": [], "lipsync_video_url": "",
        "character_image_url": "", "viral_url": "", "viral_analysis": {}, "hyperframes_html": "", "final_video_path": "",
        "review_approved": False, "script_approved": True, "images_approved": False, "character_approved": False,
        "review_feedback": [], "video_feedback_by_sort_order": {}, "messages": [],
    }
    with patch("src.agents.promo_graph.llm_chat", new_callable=AsyncMock) as llm:
        llm.return_value = '{"shots": [{"image_prompt": "planned image", "video_motion_prompt": "planned movement"}]}'
        events = [event async for event in graph.astream(state, {"configurable": {"thread_id": "shot-plan"}})]
    assert "generate_shot_plan" in [next(iter(event)) for event in events if event]
    assert llm.await_args.args[0] == "scriptwriter"


def test_long_shot_is_split_into_model_sized_clip_segments():
    segments = clip_segments_for_shot_plan([{"target_duration_seconds": 12, "image_prompt": "still", "video_motion_prompt": "move"}])
    assert [segment["target_duration_seconds"] for segment in segments] == [5, 5, 2]
    assert [(segment["shot_index"], segment["segment_index"]) for segment in segments] == [(0, 0), (0, 1), (0, 2)]


def test_clip_segment_planning_uses_the_frozen_video_model_duration_constraint():
    segments = clip_segments_for_shot_plan(
        [{"target_duration_seconds": 12, "image_prompt": "still", "video_motion_prompt": "move"}],
        max_duration_seconds=8,
    )

    assert [segment["target_duration_seconds"] for segment in segments] == [8, 4]


def test_each_clip_segment_has_start_and_end_keyframes_for_the_selected_model():
    segments = clip_segments_for_shot_plan([{"target_duration_seconds": 12, "image_prompt": "still", "video_motion_prompt": "move"}])

    keyframes = keyframes_for_segments(segments)

    assert len(keyframes) == 6
    assert [(keyframe["segment_index"], keyframe["keyframe_role"]) for keyframe in keyframes] == [
        (0, "start"), (0, "end"), (1, "start"), (1, "end"), (2, "start"), (2, "end"),
    ]


def test_keyframe_planning_honors_the_frozen_video_model_keyframe_constraint():
    keyframes = keyframes_for_segments(
        [{"shot_index": 0, "segment_index": 0, "image_prompt": "still"}], max_keyframes=1,
    )

    assert [(keyframe["segment_index"], keyframe["keyframe_role"]) for keyframe in keyframes] == [(0, "start")]


@pytest.mark.asyncio
async def test_keyframe_generation_uses_the_frozen_clip_model_constraints():
    graph = build_promo_graph(interrupt_before=["wait_image_review"])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}}, "main_image_data_uri": "",
        "creative_brief": {"core_promise": "test"}, "creative_brief_approved": True,
        "script_content": "script", "edited_script_content": "", "image_prompts": ["legacy"], "voiceover_text": "voiceover",
        "shot_plan": [{"target_duration_seconds": 12, "image_prompt": "still", "video_motion_prompt": "move"}], "shot_plan_approved": True,
        "clip_model_constraints": {"max_duration_seconds": 8, "max_keyframes": 1},
        "generated_images": [], "video_clips": [], "tts_audio_url": "", "tts_words": [], "lipsync_video_url": "", "character_image_url": "",
        "viral_url": "", "viral_analysis": {}, "hyperframes_html": "", "final_video_path": "", "review_approved": False,
        "script_approved": True, "images_approved": False, "character_approved": False, "review_feedback": [], "video_feedback_by_sort_order": {}, "messages": [],
    }
    with patch("src.agents.promo_graph.generate_image", new_callable=AsyncMock, return_value="https://image"):
        events = [event async for event in graph.astream(state, {"configurable": {"thread_id": "frozen-constraints"}})]

    generated = next(event["generate_images"] for event in events if "generate_images" in event)
    assert [segment["target_duration_seconds"] for segment in generated["clip_segments"]] == [8, 4]
    assert [image["keyframe_role"] for image in generated["generated_images"]] == ["start", "start"]


@pytest.mark.asyncio
async def test_promo_composition_keeps_clip_windows_at_their_planned_duration_when_tts_is_slow():
    state = {
        "task_id": "timing", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "creative_brief": {"core_promise": "test"}, "creative_brief_approved": True,
        "script_content": "script", "edited_script_content": "", "image_prompts": ["prompt"], "voiceover_text": "short narration",
        "shot_plan": [{"target_duration_seconds": 5, "voiceover_text": "short narration"}], "shot_plan_approved": True,
        "generated_images": [
            {"image_url": "https://image-start", "status": "approved", "shot_index": 0, "segment_index": 0, "keyframe_role": "start"},
            {"image_url": "https://image-end", "status": "approved", "shot_index": 0, "segment_index": 0, "keyframe_role": "end"},
        ],
        "video_clips": ["https://clip"], "tts_audio_url": "", "tts_duration_seconds": 0, "tts_words": [],
        "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {}, "hyperframes_html": "", "final_video_path": "",
        "script_approved": True, "images_approved": True, "character_approved": False, "review_approved": False,
        "review_feedback": [], "video_feedback_by_sort_order": {}, "messages": [],
    }
    with patch("src.agents.promo_graph.generate_tts", new_callable=AsyncMock) as tts, patch("src.agents.promo_graph.render_hyperframes", new_callable=AsyncMock) as render:
        tts.return_value = {"audio_url": "https://audio", "words": [], "tts_duration_seconds": 46.4}
        render.return_value = "/tmp/final.mp4"
        async for _ in build_promo_graph(interrupt_before=[]).astream(state, {"configurable": {"thread_id": "timing"}}):
            pass
    assert tts.await_args.kwargs == {"task_id": "timing"}
    assert 'data-duration="5.0" data-track-index="0"' in render.await_args.args[0]
    assert 'data-duration="46.4" data-track-index="0"' not in render.await_args.args[0]
    html = render.await_args.args[0]
    assert '<video id="clip-0" class="clip"' in html
    assert 'preload="auto"' in html
    assert '<audio id="voiceover" src="https://audio" data-start="0" data-duration=' not in html
    assert '.composition { position:relative; width:1152px; height:768px; overflow:hidden; }' in html


@pytest.mark.asyncio
async def test_promo_images_use_product_main_image_as_data_uri_reference():
    graph = build_promo_graph(interrupt_before=["wait_image_review"])
    reference_image = "data:image/png;base64,cHJvZHVjdA=="
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "main_image_data_uri": reference_image,
        "script_content": "script", "edited_script_content": "", "image_prompts": ["product scene"],
        "voiceover_text": "script", "generated_images": [], "video_clips": [], "tts_audio_url": "", "tts_words": [],
        "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {},
        "hyperframes_html": "", "final_video_path": "", "review_approved": False,
        "script_approved": True, "images_approved": False, "character_approved": False,
        "review_feedback": [], "video_feedback_by_sort_order": {}, "messages": [],
    }

    with patch("src.agents.promo_graph.generate_image", new_callable=AsyncMock) as generate:
        generate.return_value = "https://generated/image.png"
        async for _ in graph.astream(state, {"configurable": {"thread_id": "product-reference"}}):
            pass

    assert generate.await_args.kwargs["ref_image_url"] == reference_image


@pytest.mark.asyncio
async def test_reused_script_does_not_report_a_new_script_generation():
    from src.tasks.execution import reset_execution_reporter, set_execution_reporter

    graph = build_promo_graph()
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "script_content": "existing", "edited_script_content": "", "image_prompts": ["prompt"], "voiceover_text": "existing",
        "generated_images": [], "video_clips": [], "tts_audio_url": "", "tts_words": [],
        "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {},
        "hyperframes_html": "", "final_video_path": "", "review_approved": False,
        "script_approved": False, "images_approved": False, "character_approved": False,
        "review_feedback": [], "video_feedback_by_sort_order": {}, "messages": [],
    }
    started = []

    async def report(node_name):
        started.append(node_name)

    token = set_execution_reporter(report)
    try:
        async for _ in graph.astream(state, {"configurable": {"thread_id": "reused-script"}}):
            pass
    finally:
        reset_execution_reporter(token)

    assert "generate_script" not in started


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
        tts.return_value = {"audio_url": "https://audio", "words": [], "tts_duration_seconds": 12.5}
        render.return_value = "/tmp/final.mp4"
        events = [event async for event in graph.astream(state, {"configurable": {"thread_id": "reuse-clips"}})]

    reused_output = next(event["generate_video_clips"] for event in events if "generate_video_clips" in event)
    assert reused_output["video_clips_reused"] is True
    html = render.await_args.args[0]
    assert 'data-duration="5.0"' in html
    assert html.count('<video id="clip-') == 1


@pytest.mark.asyncio
async def test_editing_blueprint_records_rendered_transition_and_audio_marker():
    graph = build_promo_graph(interrupt_before=[])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "script_content": "script", "edited_script_content": "", "image_prompts": ["prompt"], "voiceover_text": "script",
        "shot_plan": [{"target_duration_seconds": 5, "voiceover_text": "first"}, {"target_duration_seconds": 5, "voiceover_text": "second"}],
        "creative_brief": {"core_promise": "test"}, "creative_brief_approved": True, "shot_plan_approved": True,
        "generated_images": [
            {"image_url": "https://image-1", "status": "approved"}, {"image_url": "https://image-2", "status": "approved"},
            {"image_url": "https://image-3", "status": "approved"}, {"image_url": "https://image-4", "status": "approved"},
        ],
        "video_clips": ["https://clip-1", "https://clip-2"], "tts_audio_url": "", "tts_words": [], "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {}, "hyperframes_html": "", "final_video_path": "", "script_approved": True, "images_approved": True, "review_approved": False, "review_feedback": [], "video_feedback_by_sort_order": {}, "messages": [],
    }
    with patch("src.agents.promo_graph.generate_tts", new_callable=AsyncMock) as tts, patch("src.agents.promo_graph.render_hyperframes", new_callable=AsyncMock) as render:
        tts.return_value = {"audio_url": "https://audio", "words": [], "tts_duration_seconds": 10}
        render.return_value = "/tmp/final.mp4"
        events = [event async for event in graph.astream(state, {"configurable": {"thread_id": "blueprint"}})]
    blueprint = next(event["composite_video"]["editing_blueprint"] for event in events if "composite_video" in event)
    assert blueprint[1]["transition"] == "cut"
    assert blueprint[1]["audio_marker_seconds"] == 5


@pytest.mark.asyncio
async def test_composition_feedback_does_not_regenerate_tts_from_clean_voiceover_text():
    graph = build_promo_graph(interrupt_before=[])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 1,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "script_content": "[Scene 1] raw production script", "edited_script_content": "",
        "voiceover_text": "Clean narration for speech.", "image_prompts": ["prompt"],
        "generated_images": [{"image_url": "https://image", "status": "approved"}],
        "video_clips": ["https://clip"], "tts_audio_url": "https://old-audio", "tts_words": [],
        "tts_duration_seconds": 5, "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {},
        "hyperframes_html": "", "final_video_path": "", "script_approved": True, "images_approved": True,
        "review_approved": False, "review_feedback": [{"id": "feedback-1", "target_type": "composition", "content": "Fix the spoken language."}],
        "video_feedback_by_sort_order": {}, "messages": [],
    }
    with patch("src.agents.promo_graph.llm_chat", new_callable=AsyncMock) as llm, patch("src.agents.promo_graph.generate_tts", new_callable=AsyncMock) as tts, patch("src.agents.promo_graph.render_hyperframes", new_callable=AsyncMock, return_value="final.mp4"):
        llm.return_value = '{"clip_duration": 5, "subtitle_offset": 10, "subtitle_size": 32}'
        tts.return_value = {"audio_url": "https://new-audio", "words": [], "tts_duration_seconds": 12}
        events = [event async for event in graph.astream(state, {"configurable": {"thread_id": "composition-feedback"}})]

    voiceover = next(event["generate_voiceover"] for event in events if "generate_voiceover" in event)
    tts.assert_not_awaited()
    assert voiceover["tts_audio_url"] == "https://old-audio"


@pytest.mark.asyncio
async def test_clip_feedback_replaces_only_the_rejected_clip():
    graph = build_promo_graph(interrupt_before=[])
    state = {
        "task_id": "task", "product_id": "product", "task_type": "promo", "image_count": 2,
        "product_info": {"version": 1, "name": "Test", "category": {"name": "Perfume"}},
        "script_content": "script", "edited_script_content": "", "image_prompts": ["one", "two"], "voiceover_text": "script",
        "generated_images": [
            {"image_url": "https://image-1", "status": "approved"}, {"image_url": "https://image-2", "status": "approved"},
            {"image_url": "https://image-3", "status": "approved"}, {"image_url": "https://image-4", "status": "approved"},
        ],
        "video_clips": ["https://clip-1", "https://clip-2"], "tts_audio_url": "", "tts_words": [],
        "lipsync_video_url": "", "character_image_url": "", "viral_url": "", "viral_analysis": {},
        "hyperframes_html": "", "final_video_path": "", "script_approved": True, "images_approved": True,
        "character_approved": False, "review_approved": False, "review_feedback": [],
        "shot_plan": [{"target_duration_seconds": 5, "video_motion_prompt": "Slow orbit around the bottle."}, {"target_duration_seconds": 5, "video_motion_prompt": "Tilt toward the label."}],
        "video_feedback_by_sort_order": {1: "Make the movement more energetic."}, "messages": [],
    }
    with patch("src.agents.promo_graph.generate_video", new_callable=AsyncMock) as video, patch("src.agents.promo_graph.generate_tts", new_callable=AsyncMock) as tts, patch("src.agents.promo_graph.render_hyperframes", new_callable=AsyncMock) as render:
        video.return_value = "https://replacement"
        tts.return_value = {"audio_url": "https://audio", "words": [], "tts_duration_seconds": 10}
        render.return_value = "/tmp/final.mp4"
        events = [event async for event in graph.astream(state, {"configurable": {"thread_id": "single-clip"}})]
    output = next(event["generate_video_clips"] for event in events if "generate_video_clips" in event)
    assert output["video_clips"] == ["https://clip-1", "https://replacement"]
    assert output["regenerated_clip_indexes"] == [1]
    assert video.await_count == 1
    assert "Tilt toward the label." in video.await_args.kwargs["prompt"]
    assert "Make the movement more energetic." in video.await_args.kwargs["prompt"]
