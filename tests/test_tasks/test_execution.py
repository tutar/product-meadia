import pytest
from sqlalchemy.pool import NullPool

from src.tasks.execution import NodeExecutionError, tracked_node


@pytest.mark.asyncio
async def test_tracked_node_reports_the_node_that_raised():
    async def failing_node(_state):
        raise RuntimeError("tts unavailable")

    wrapped = tracked_node("generate_voiceover", failing_node)

    with pytest.raises(NodeExecutionError) as exc_info:
        await wrapped({})

    assert exc_info.value.node_name == "generate_voiceover"
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_video_worker_uses_loop_safe_database_connections():
    from src.tasks.video_tasks import engine

    assert isinstance(engine.pool, NullPool)
