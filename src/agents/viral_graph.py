import json
import math
from openai import OpenAIError
from langgraph.graph import StateGraph, END
from src.agents.state import VideoAgentState
from src.tools.image_gen import generate_image
from src.tools.video_gen import generate_video
from src.tools.tts import generate_tts
from src.tools.render import render_hyperframes
from src.tools.transcription import transcribe_audio
from src.tools.llm_tools import llm_chat, analyze_video_structure
from src.tasks.execution import tracked_node
from src.services.product_context import format_product_context

PROMPT = """Adapt the reference video structure for the supplied product.
Keep the same structure, pacing, and emotional tone.
Original script: {original_script}
Product context: {product_context}

Return ONLY JSON: {{"script": "...", "voiceover": "...", "image_prompts": ["..."]}}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .composition {{ position:relative; width:1152px; height:768px; overflow:hidden; }}
  .clip {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .subtitle {{ position:absolute; bottom:{subtitle_offset}%; width:100%; text-align:center; color:#fff; font-size:{subtitle_size}px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div class="composition" data-composition-id="viral-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio id="voiceover" src="{audio_url}" data-start="0" data-track-index="10" data-volume="1" preload="auto"></audio>
  {video_elements}
  {subtitle_elements}
</div>
</body></html>"""


def review_guidance(state: VideoAgentState, target_type: str) -> str:
    guidance = [item["content"] for item in state.get("review_feedback", []) if item.get("target_type") == target_type]
    return "\n\nReviewer improvement guidance:\n" + "\n".join(guidance) if guidance else ""


async def composition_options(state: VideoAgentState) -> dict:
    defaults = {"clip_duration": 5, "subtitle_offset": 10, "subtitle_size": 32}
    guidance = review_guidance(state, "composition")
    if not guidance:
        return defaults
    try:
        result = await llm_chat("scriptwriter", "Return only JSON with clip_duration (3-7), subtitle_offset (6-18), and subtitle_size (24-42).", "Adjust this video composition using the reviewer guidance:" + guidance, temperature=0.2, task_id=state.get("task_id"), model_stage="creative_planning")
        proposed = json.loads(result)
        return {"clip_duration": min(7, max(3, int(proposed.get("clip_duration", 5)))), "subtitle_offset": min(18, max(6, int(proposed.get("subtitle_offset", 10)))), "subtitle_size": min(42, max(24, int(proposed.get("subtitle_size", 32))))}
    except (OpenAIError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return defaults


def build_viral_graph(checkpointer=None, interrupt_before=None) -> StateGraph:
    if interrupt_before is None:
        interrupt_before = ["wait_viral_confirm", "wait_script_review", "wait_image_review"]
    graph = StateGraph(VideoAgentState)

    async def analyze_source(state: VideoAgentState) -> dict:
        if state.get("viral_analysis"):
            return {"viral_analysis": state["viral_analysis"]}
        transcript = await transcribe_audio(state["viral_url"], task_id=state.get("task_id"))
        analysis = await analyze_video_structure(transcript, task_id=state.get("task_id"))
        return {"viral_analysis": analysis}

    async def wait_viral_confirm(state: VideoAgentState) -> dict:
        return {}

    async def generate_rewritten_script(state: VideoAgentState) -> dict:
        if state.get("script_content") and state.get("image_prompts"):
            return {}
        info = state["product_info"]
        user_prompt = PROMPT.format(
            original_script=str(state.get("viral_analysis", {})),
            product_context=format_product_context(info) + review_guidance(state, "script"),
        )
        result = await llm_chat("scriptwriter", "You are a video script adapter.", user_prompt, task_id=state.get("task_id"), model_stage="scriptwriting")
        data = json.loads(result)
        return {
            "script_content": data["script"],
            "voiceover_text": data["voiceover"],
            "image_prompts": data["image_prompts"],
        }

    async def wait_script_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_images(state: VideoAgentState) -> dict:
        if state.get("generated_images"):
            return {"generated_images": state["generated_images"]}
        images = []
        for i, p in enumerate(state.get("image_prompts", [])):
            url = await generate_image(
                p + review_guidance(state, "image"),
                ref_image_url=state.get("main_image_data_uri") or None,
                task_id=state.get("task_id"),
            )
            images.append({"sort_order": i, "image_url": url, "status": "pending_review"})
        return {"generated_images": images}

    async def wait_image_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_clips_and_voiceover(state: VideoAgentState) -> dict:
        clips = list(state.get("video_clips") or [])
        if not clips:
            for img in state.get("generated_images", []):
                if img.get("status") == "approved":
                    clip = await generate_video(
                        prompt=f"Smooth cinematic movement showcasing {state['product_info']['category']['name']} product {state['product_info']['name']}" + review_guidance(state, "video_clip"),
                        image_urls=[img["image_url"]],
                        task_id=state.get("task_id"),
                    )
                    clips.append(clip)

        if state.get("tts_audio_url"):
            audio_url = state["tts_audio_url"]
            words = state["tts_words"]
        else:
            tts_result = await generate_tts(
                state.get("edited_script_content") or state["script_content"], task_id=state.get("task_id")
            )
            audio_url = tts_result["audio_url"]
            words = tts_result["words"]
            tts_duration_seconds = tts_result["tts_duration_seconds"]
        if state.get("tts_audio_url"):
            tts_duration_seconds = state.get("tts_duration_seconds", 0)
        return {
            "video_clips": clips,
            "tts_audio_url": audio_url,
            "tts_words": words,
            "tts_duration_seconds": tts_duration_seconds,
        }

    async def composite(state: VideoAgentState) -> dict:
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
                f'data-duration="{duration}" data-track-index="0" muted playsinline preload="auto"></video>\n'
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

    graph.add_node("analyze_source", tracked_node("analyze_source", analyze_source))
    graph.add_node("wait_viral_confirm", wait_viral_confirm)
    graph.add_node("generate_rewritten_script", tracked_node("generate_rewritten_script", generate_rewritten_script))
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_images", tracked_node("generate_images", generate_images))
    graph.add_node("wait_image_review", wait_image_review)
    graph.add_node("generate_clips_and_voiceover", tracked_node("generate_clips_and_voiceover", generate_clips_and_voiceover))
    graph.add_node("composite", tracked_node("composite", composite))

    graph.set_entry_point("analyze_source")
    graph.add_edge("analyze_source", "wait_viral_confirm")
    graph.add_edge("wait_viral_confirm", "generate_rewritten_script")
    graph.add_edge("generate_rewritten_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_images")
    graph.add_edge("generate_images", "wait_image_review")
    graph.add_edge("wait_image_review", "generate_clips_and_voiceover")
    graph.add_edge("generate_clips_and_voiceover", "composite")
    graph.add_edge("composite", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )


viral_graph = build_viral_graph()
