import json
import math
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
  .subtitle {{ position:absolute; bottom:{subtitle_offset}%; width:100%; text-align:center; color:#fff; font-size:{subtitle_size}px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="promo-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio id="voiceover" src="{audio_url}" data-start="0" data-duration="{total_duration}" data-track-index="10" data-volume="1"></audio>
  {video_elements}
  {subtitle_elements}
</div>
</body></html>"""


def review_guidance(state: VideoAgentState, target_type: str, target_id: str | None = None) -> str:
    guidance = [item["content"] for item in state.get("review_feedback", [])
                if item.get("target_type") == target_type and (target_id is None or item.get("target_id") == target_id)]
    return "\n\nReviewer improvement guidance:\n" + "\n".join(guidance) if guidance else ""


async def composition_options(state: VideoAgentState) -> dict:
    defaults = {"clip_duration": 5, "subtitle_offset": 10, "subtitle_size": 32}
    guidance = review_guidance(state, "composition")
    if not guidance:
        return defaults
    result = await llm_chat(
        "composition_designer",
        "Return only JSON with clip_duration (3-7), subtitle_offset (6-18), and subtitle_size (24-42).",
        "Adjust this video composition using the reviewer guidance:" + guidance,
        temperature=0.2,
    )
    try:
        proposed = json.loads(result)
        return {
            "clip_duration": min(7, max(3, int(proposed.get("clip_duration", 5)))),
            "subtitle_offset": min(18, max(6, int(proposed.get("subtitle_offset", 10)))),
            "subtitle_size": min(42, max(24, int(proposed.get("subtitle_size", 32)))),
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        return defaults


def composition_feedback_key(state: VideoAgentState) -> str:
    feedback_ids = [
        item["id"] for item in state.get("review_feedback", [])
        if item.get("target_type") == "composition" and item.get("id")
    ]
    return "feedback:" + ":".join(feedback_ids) if feedback_ids else "initial"


def build_promo_graph(checkpointer=None, interrupt_before=None) -> StateGraph:
    if interrupt_before is None:
        interrupt_before = ["wait_script_review", "wait_image_review"]
    graph = StateGraph(VideoAgentState)

    async def generate_script(state: VideoAgentState) -> dict:
        # Skip if script already loaded from DB on retry
        if state.get("script_content") and state.get("image_prompts"):
            return {}
        info = state["product_info"]
        prompt = format_product_context(info) + review_guidance(state, "script")
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
                url = await generate_image(
                    p + review_guidance(state, "image", old.get("id") if old else None),
                    ref_image_url=state.get("main_image_data_uri") or None,
                )
                images.append({"sort_order": i, "image_url": url, "status": "pending_review"})
        return {"generated_images": images}

    async def generate_video_clips(state: VideoAgentState) -> dict:
        feedback_by_index = state.get("video_feedback_by_sort_order", {})
        if state.get("video_clips") and not feedback_by_index:
            return {"video_clips": state["video_clips"], "video_clips_reused": True}
        approved_urls = [img["image_url"] for img in state.get("generated_images", []) if img.get("status") == "approved"]
        if state.get("video_clips") and feedback_by_index:
            clips = list(state["video_clips"])
            for index, guidance in feedback_by_index.items():
                if index >= len(approved_urls):
                    continue
                clips[index] = await generate_video(
                    prompt=f"Cinematic movement showcasing {state['product_info']['category']['name']} product {state['product_info']['name']}\n\nReviewer improvement guidance:\n{guidance}",
                    image_urls=[approved_urls[index]],
                )
            return {"video_clips": clips, "video_clips_reused": False, "regenerated_clip_indexes": list(feedback_by_index)}
        clips = []
        for url in approved_urls:
            clip_url = await generate_video(
                prompt=f"Cinematic movement showcasing {state['product_info']['category']['name']} product {state['product_info']['name']}" + review_guidance(state, "video_clip"),
                image_urls=[url],
            )
            clips.append(clip_url)
        return {"video_clips": clips, "video_clips_reused": False}

    async def generate_voiceover(state: VideoAgentState) -> dict:
        if state.get("tts_audio_url") and not review_guidance(state, "composition"):
            return {"tts_audio_url": state["tts_audio_url"], "tts_words": state["tts_words"]}
        voiceover = state.get("voiceover_text") or state.get("edited_script_content") or state["script_content"]
        result = await generate_tts(voiceover)
        return {
            "tts_audio_url": result["audio_url"],
            "tts_words": result["words"],
            "tts_duration_seconds": result["tts_duration_seconds"],
            "tts_generation_key": composition_feedback_key(state),
        }

    async def composite_video(state: VideoAgentState) -> dict:
        clips = state.get("video_clips", [])
        options = await composition_options(state)
        clip_duration = options["clip_duration"]
        visual_duration = len(clips) * clip_duration
        word_duration = max((word["end"] for word in state.get("tts_words", [])), default=0)
        total_duration = max(float(state.get("tts_duration_seconds") or 0), word_duration, visual_duration) or 30
        video_elements = ""
        for i in range(math.ceil(total_duration / clip_duration)):
            url = clips[i % len(clips)] if clips else ""
            duration = min(clip_duration, total_duration - i * clip_duration)
            video_elements += (
                f'<video id="clip-{i}" class="clip" src="{url}" data-start="{i * clip_duration}" '
                f'data-duration="{duration}" data-track-index="0" muted playsinline></video>\n'
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
            subtitle_offset=options["subtitle_offset"],
            subtitle_size=options["subtitle_size"],
        )
        path = await render_hyperframes(html)
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node(
        "generate_script",
        tracked_node(
            "generate_script",
            generate_script,
            should_report=lambda state: not (state.get("script_content") and state.get("image_prompts")),
        ),
    )
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
