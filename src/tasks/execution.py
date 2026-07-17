from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from datetime import datetime
from functools import wraps
from typing import Any


ARTIFACT_STATE_KEYS = (
    "video_clip_asset_ids",
    "tts_audio_asset_id",
    "tts_words",
    "lipsync_video_asset_id",
    "character_image_asset_id",
    "final_video_asset_id",
)

NODE_TO_STAGE = {
    "generate_script": "scripting",
    "generate_rewritten_script": "scripting",
    "generate_images": "imaging",
    "generate_video_clips": "video_gen",
    "generate_clips_and_voiceover": "video_gen",
    "generate_voiceover": "video_gen",
    "generate_tts_and_lipsync": "video_gen",
    "composite_video": "compositing",
    "composite": "compositing",
}


ExecutionReporter = Callable[[str], Awaitable[None]]
_execution_reporter: ContextVar[ExecutionReporter | None] = ContextVar("execution_reporter", default=None)


def set_execution_reporter(reporter: ExecutionReporter) -> Token:
    """Attach a task-local reporter used while workflow nodes execute."""
    return _execution_reporter.set(reporter)


def reset_execution_reporter(token: Token) -> None:
    _execution_reporter.reset(token)


def execution_stage(node_name: str | None) -> str:
    """Return the user-visible Execution Stage for a workflow node."""
    if node_name == "analyze_source":
        return "analysis"
    if node_name == "generate_character":
        return "character"
    return NODE_TO_STAGE.get(node_name or "", "other")


def execution_timing(started_at: str, finished_at: str) -> int:
    """Return an Execution Substep duration in milliseconds."""
    started = datetime.fromisoformat(started_at.removesuffix("Z") + "+00:00")
    finished = datetime.fromisoformat(finished_at.removesuffix("Z") + "+00:00")
    return max(0, int((finished - started).total_seconds() * 1000))


class NodeExecutionError(RuntimeError):
    def __init__(self, node_name: str, cause: Exception):
        super().__init__(str(cause))
        self.node_name = node_name
        self.__cause__ = cause


def tracked_node(
    node_name: str,
    node: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
):
    @wraps(node)
    async def wrapped(state):
        try:
            reporter = _execution_reporter.get()
            if reporter:
                await reporter(node_name)
            return await node(state)
        except NodeExecutionError:
            raise
        except Exception as exc:
            raise NodeExecutionError(node_name, exc) from exc

    return wrapped


def stage_for_node(node_name: str | None) -> str | None:
    return NODE_TO_STAGE.get(node_name) if node_name else None
