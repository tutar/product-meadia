import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from src.agents.state import VideoAgentState
from src.tools.image_gen import generate_image
from src.tools.video_gen import generate_video
from src.tools.tts import generate_tts
from src.tools.render import render_hyperframes
from src.config import settings
from src.tools.llm_tools import llm_chat

SCRIPT_SYSTEM = """You are a perfume video scriptwriter. Given a perfume product, write:
1. A video script (narration text) with structure: opening → middle notes → base notes → scenarios → CTA
2. Voiceover text (same as script, cleaned for TTS)
3. {image_count} image generation prompts. Each prompt describes a cinematic perfume-ad visual scene.
   Match the script's narrative flow. Style: luxury, cinematic lighting, product-focused.

Return ONLY JSON: {{"script": "...", "voiceover": "...", "image_prompts": ["prompt1", ...]}}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .clip {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .subtitle {{ position:absolute; bottom:10%; width:100%; text-align:center; color:#fff; font-size:32px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="promo-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio src="{audio_url}" data-start="0"></audio>
  {video_elements}
  {subtitle_elements}
</div>
</body></html>"""


def build_promo_graph() -> StateGraph:
    graph = StateGraph(VideoAgentState)

    async def generate_script(state: VideoAgentState) -> dict:
        info = state["product_info"]
        prompt = (
            f"Product: {info['name']}\\n"
            f"Top notes: {info.get('top_note','')}\\n"
            f"Middle notes: {info.get('middle_note','')}\\n"
            f"Base notes: {info.get('base_note','')}\\n"
            f"Scenarios: {info.get('scenarios',[])}"
        )
        system = SCRIPT_SYSTEM.format(image_count=state["image_count"])
        result = await llm_chat("scriptwriter", system, prompt, temperature=0.7)
        data = json.loads(result)
        return {
            "script_content": data["script"],
            "voiceover_text": data["voiceover"],
            "image_prompts": data["image_prompts"][: state["image_count"]],
        }

    async def wait_script_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_images(state: VideoAgentState) -> dict:
        prompts = state.get("image_prompts", [])
        images = []
        for i, p in enumerate(prompts):
            url = await generate_image(p)
            images.append({"sort_order": i, "image_url": url, "status": "pending_review"})
        return {"generated_images": images}

    async def wait_image_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_video_clips(state: VideoAgentState) -> dict:
        approved_urls = [img["image_url"] for img in state.get("generated_images", []) if img.get("status") == "approved"]
        clips = []
        for url in approved_urls:
            clip_url = await generate_video(
                prompt="Cinematic camera movement, smooth panning, luxury perfume advertisement style",
                image_urls=[url],
            )
            clips.append(clip_url)
        return {"video_clips": clips}

    async def generate_voiceover(state: VideoAgentState) -> dict:
        script = state.get("edited_script_content") or state["script_content"]
        result = await generate_tts(script)
        return {"tts_audio_url": result["audio_url"], "tts_words": result["words"]}

    async def composite_video(state: VideoAgentState) -> dict:
        total_duration = len(state.get("video_clips", [])) * 5 or 30
        video_elements = ""
        for i, url in enumerate(state.get("video_clips", [])):
            video_elements += (
                f'<video class="clip" src="{url}" data-start="{i * 5}" '
                f'data-duration="5" muted playsinline></video>\n'
            )

        subtitle_elements = ""
        for w in state.get("tts_words", []):
            subtitle_elements += (
                f'<div class="subtitle" data-start="{w["start"]}" '
                f'data-duration="{w["end"] - w["start"]}">{w["word"]}</div>\n'
            )

        html = HTML_TEMPLATE.format(
            total_duration=total_duration,
            audio_url=state["tts_audio_url"],
            video_elements=video_elements,
            subtitle_elements=subtitle_elements,
        )
        path = await render_hyperframes(html, "/tmp")
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node("generate_script", generate_script)
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_images", generate_images)
    graph.add_node("wait_image_review", wait_image_review)
    graph.add_node("generate_video_clips", generate_video_clips)
    graph.add_node("generate_voiceover", generate_voiceover)
    graph.add_node("composite_video", composite_video)

    graph.set_entry_point("generate_script")
    graph.add_edge("generate_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_images")
    graph.add_edge("generate_images", "wait_image_review")
    graph.add_edge("wait_image_review", "generate_video_clips")
    graph.add_edge("generate_video_clips", "generate_voiceover")
    graph.add_edge("generate_voiceover", "composite_video")
    graph.add_edge("composite_video", END)

    return graph.compile(
        checkpointer=PostgresSaver(conn=settings.database_url),
        interrupt_before=["wait_script_review", "wait_image_review"],
    )


promo_graph = build_promo_graph()
