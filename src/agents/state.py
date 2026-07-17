from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class ProductContext(TypedDict):
    version: int
    name: str
    category: dict
    attributes: list[dict]
    selling_points: list[str]
    scenarios: list[str]
    main_image_asset_id: str


class VideoAgentState(TypedDict):
    task_id: str
    product_id: str
    product_info: ProductContext
    task_type: str
    image_count: int

    script_content: str
    edited_script_content: str
    image_prompts: list[str]
    voiceover_text: str

    generated_images: list[dict]
    video_clips: list[str]
    video_clips_reused: bool
    regenerated_clip_indexes: list[int]

    tts_audio_url: str
    tts_duration_seconds: float
    tts_words: list[dict]

    lipsync_video_url: str
    character_image_url: str

    viral_url: str
    viral_analysis: dict

    hyperframes_html: str
    final_video_path: str

    review_approved: bool
    script_approved: bool
    images_approved: bool
    character_approved: bool
    review_feedback: list[dict]
    video_feedback_by_sort_order: dict[int, str]
    messages: Annotated[list, add_messages]
