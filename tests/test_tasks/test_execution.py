import pytest
from sqlalchemy.pool import NullPool

from src.tasks.execution import (
    NodeExecutionError, execution_stage, execution_timing, reset_execution_reporter,
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


async def _result(value):
    return value


def test_video_worker_uses_loop_safe_database_connections():
    from src.tasks.video_tasks import engine

    assert isinstance(engine.pool, NullPool)


def test_workflow_nodes_have_user_visible_execution_stages():
    assert execution_stage("generate_script") == "scripting"
    assert execution_stage("generate_tts_and_lipsync") == "video_gen"
    assert execution_stage("generate_character") == "character"
    assert execution_stage("unknown") == "other"


def test_execution_timing_reports_elapsed_milliseconds():
    assert execution_timing("2026-07-17T10:00:00Z", "2026-07-17T10:00:01.250000Z") == 1250
