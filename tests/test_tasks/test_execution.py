import pytest
import inspect
from sqlalchemy.pool import NullPool

from src.tasks.execution import (
    NodeExecutionError, execution_stage, execution_timing, reset_execution_reporter,
    next_execution_attempt, review_status_for_node, safe_error_summary,
    set_execution_reporter, tracked_node,
)


@pytest.mark.asyncio
async def test_tracked_node_reports_the_node_that_raised():
    async def failing_node(_state):
        raise RuntimeError("tts unavailable")

    wrapped = tracked_node("generate_voiceover", failing_node)

    with pytest.raises(NodeExecutionError) as exc_info:
        await wrapped({})

    assert exc_info.value.node_name == "generate_voiceover"
    assert isinstance(exc_info.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_tracked_node_reports_when_a_substep_starts():
    started = []

    async def report(node_name):
        started.append(node_name)

    token = set_execution_reporter(report)
    try:
        assert await tracked_node("generate_script", lambda _state: _result({"script_content": "x"}))({}) == {"script_content": "x"}
    finally:
        reset_execution_reporter(token)

    assert started == ["generate_script"]


@pytest.mark.asyncio
async def test_tracked_node_does_not_report_a_skipped_substep():
    started = []

    async def report(node_name):
        started.append(node_name)

    token = set_execution_reporter(report)
    try:
        wrapped = tracked_node(
            "generate_script",
            lambda _state: _result({}),
            should_report=lambda state: not state["already_generated"],
        )
        assert await wrapped({"already_generated": True}) == {}
    finally:
        reset_execution_reporter(token)

    assert started == []


async def _result(value):
    return value


@pytest.mark.asyncio
async def test_fetch_provider_media_keeps_wav_content_type(tmp_path):
    from src.tasks.video_tasks import _fetch_provider_media

    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"wav")

    data, content_type = await _fetch_provider_media(str(audio))

    assert data == b"wav"
    assert content_type == "audio/x-wav"


def test_video_worker_uses_loop_safe_database_connections():
    from src.tasks.video_tasks import engine

    assert isinstance(engine.pool, NullPool)


def test_video_task_runner_does_not_shadow_its_datetime_alias():
    from src.tasks.video_tasks import _async_run

    assert "import datetime as _dt" not in inspect.getsource(_async_run)


def test_workflow_nodes_have_user_visible_execution_stages():
    assert execution_stage("generate_script") == "scripting"
    assert execution_stage("generate_tts_and_lipsync") == "video_gen"
    assert execution_stage("generate_character") == "character"
    assert execution_stage("unknown") == "other"


def test_execution_timing_reports_elapsed_milliseconds():
    assert execution_timing("2026-07-17T10:00:00Z", "2026-07-17T10:00:01.250000Z") == 1250


def test_retry_creates_a_new_execution_attempt_but_review_resume_does_not():
    history = [{"attempt": 1}, {"attempt": 2}]

    assert next_execution_attempt(history, is_retry=False) == 2
    assert next_execution_attempt(history, is_retry=True) == 3


def test_review_waits_are_mapped_to_the_relevant_user_review():
    assert review_status_for_node("generate_script") == "script_review"
    assert review_status_for_node("generate_images") == "image_review"
    assert review_status_for_node("generate_character") == "character_review"


def test_error_summary_does_not_expose_provider_payloads():
    assert safe_error_summary(RuntimeError("prompt=secret model response=private")) == "RuntimeError: substep failed"
