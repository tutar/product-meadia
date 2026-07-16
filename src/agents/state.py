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

    tts_audio_url: str
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
    messages: Annotated[list, add_messages]
