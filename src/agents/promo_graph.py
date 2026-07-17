import json
from langgraph.graph import StateGraph, END
from src.agents.state import VideoAgentState
from src.tools.image_gen import generate_image
from src.tools.video_gen import generate_video
from src.tools.tts import generate_tts
from src.tools.render import render_hyperframes
from src.tools.llm_tools import llm_chat
from src.tasks.execution import tracked_node
from src.services.product_context import format_product_context

SCRIPT_SYSTEM = """You are a product video scriptwriter. Given a product context, write:
1. A video script with structure: hook → need or scene → selling points → attribute evidence → CTA
2. Voiceover text (same as script, cleaned for TTS)
3. {image_count} category-appropriate cinematic image prompts matching the narrative flow.
   Keep prompts safe, product-focused, and grounded in supplied attributes and use scenes.

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


def build_promo_graph(checkpointer=None, interrupt_before=None) -> StateGraph:
    if interrupt_before is None:
        interrupt_before = ["wait_script_review", "wait_image_review"]
    graph = StateGraph(VideoAgentState)

    async def generate_script(state: VideoAgentState) -> dict:
        # Skip if script already loaded from DB on retry
        if state.get("script_content") and state.get("image_prompts"):
            return {}
        info = state["product_info"]
        prompt = format_product_context(info)
        system = SCRIPT_SYSTEM.format(image_count=state["image_count"])
        result = await llm_chat("scriptwriter", system, prompt, temperature=0.7)
        data = json.loads(result)
        return {
            "script_content": data["script"],
            "voiceover_text": data["voiceover"],
            "image_prompts": data["image_prompts"][: state["image_count"]],
        }

    async def wait_script_review(state: VideoAgentState) -> dict:
        if state.get("script_approved"):
            return {}
        return {"__status": "script_review"}

    async def wait_image_review(state: VideoAgentState) -> dict:
        if state.get("images_approved"):
            return {}
        return {"__status": "image_review"}

    async def generate_images(state: VideoAgentState) -> dict:
        prompts = state.get("image_prompts", [])
        existing = state.get("generated_images", [])
        images = []
        for i, p in enumerate(prompts):
            # Reuse existing approved/pending images on retry
            old = existing[i] if i < len(existing) else None
            if old and old.get("image_url") and old.get("status") in ("approved", "pending_review"):
                images.append(old)
            else:
                url = await generate_image(p)
                images.append({"sort_order": i, "image_url": url, "status": "pending_review"})
        return {"generated_images": images}

    async def generate_video_clips(state: VideoAgentState) -> dict:
        if state.get("video_clips"):
            return {"video_clips": state["video_clips"], "video_clips_reused": True}
        approved_urls = [img["image_url"] for img in state.get("generated_images", []) if img.get("status") == "approved"]
        clips = []
        for url in approved_urls:
            clip_url = await generate_video(
                prompt=f"Cinematic movement showcasing {state['product_info']['category']['name']} product {state['product_info']['name']}",
                image_urls=[url],
            )
            clips.append(clip_url)
        return {"video_clips": clips, "video_clips_reused": False}

    async def generate_voiceover(state: VideoAgentState) -> dict:
        if state.get("tts_audio_url") and state.get("tts_words"):
            return {"tts_audio_url": state["tts_audio_url"], "tts_words": state["tts_words"]}
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
        path = await render_hyperframes(html)
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node("generate_script", tracked_node("generate_script", generate_script))
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_images", tracked_node("generate_images", generate_images))
    graph.add_node("wait_image_review", wait_image_review)
    graph.add_node("generate_video_clips", tracked_node("generate_video_clips", generate_video_clips))
    graph.add_node("generate_voiceover", tracked_node("generate_voiceover", generate_voiceover))
    graph.add_node("composite_video", tracked_node("composite_video", composite_video))

    graph.set_entry_point("generate_script")
    graph.add_edge("generate_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_images")
    graph.add_edge("generate_images", "wait_image_review")
    graph.add_edge("wait_image_review", "generate_video_clips")
    graph.add_edge("generate_video_clips", "generate_voiceover")
    graph.add_edge("generate_voiceover", "composite_video")
    graph.add_edge("composite_video", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )


promo_graph = build_promo_graph()
