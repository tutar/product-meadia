from collections.abc import Awaitable, Callable
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
            return await node(state)
        except NodeExecutionError:
            raise
        except Exception as exc:
            raise NodeExecutionError(node_name, exc) from exc

    return wrapped


def stage_for_node(node_name: str | None) -> str | None:
    return NODE_TO_STAGE.get(node_name) if node_name else None
