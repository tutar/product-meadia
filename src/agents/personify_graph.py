import json
from langgraph.graph import StateGraph, END
from src.agents.state import VideoAgentState
from src.tools.image_gen import generate_image
from src.tools.tts import generate_tts
from src.tools.lipsync import run_lipsync
from src.tools.render import render_hyperframes
from src.tools.llm_tools import llm_chat
from src.tasks.execution import tracked_node
from src.services.product_context import format_product_context

CHARACTER_PROMPT = """Design a personified character for this product:
{product_context}

Describe the character as an image generation prompt: age, gender, clothing style,
expression, setting. Derive appearance from category, selling points, attributes, and use scenes.
Output ONLY the image prompt, no commentary."""

SCRIPT_PROMPT = """You are this product speaking in first person.
{product_context}

Write a 30-second category-appropriate first-person monologue grounded in the context.
Return ONLY JSON: {{"script": "...", "voiceover": "..."}}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .main {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .overlay {{ position:absolute; top:5%; left:5%; color:#fff; font-size:28px; text-shadow:0 2px 8px rgba(0,0,0,0.7); }}
  .subtitle {{ position:absolute; bottom:{subtitle_offset}%; width:100%; text-align:center; color:#fff; font-size:{subtitle_size}px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="personify-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio src="{audio_url}" data-start="0"></audio>
  <video class="main" src="{lipsync_url}" data-start="0" data-duration="{total_duration}" muted playsinline></video>
  <div class="overlay" data-start="0" data-duration="{total_duration}">{product_name}</div>
  {subtitle_elements}
</div>
</body></html>"""


def review_guidance(state: VideoAgentState, target_type: str) -> str:
    guidance = [item["content"] for item in state.get("review_feedback", []) if item.get("target_type") == target_type]
    return "\n\nReviewer improvement guidance:\n" + "\n".join(guidance) if guidance else ""


async def composition_options(state: VideoAgentState) -> dict:
    defaults = {"subtitle_offset": 12, "subtitle_size": 30}
    guidance = review_guidance(state, "composition")
    if not guidance:
        return defaults
    result = await llm_chat("composition_designer", "Return only JSON with subtitle_offset (6-18) and subtitle_size (24-42).", "Adjust this video composition using the reviewer guidance:" + guidance, temperature=0.2)
    try:
        proposed = json.loads(result)
        return {"subtitle_offset": min(18, max(6, int(proposed.get("subtitle_offset", 12)))), "subtitle_size": min(42, max(24, int(proposed.get("subtitle_size", 30))))}
    except (TypeError, ValueError, json.JSONDecodeError):
        return defaults


def build_personify_graph(checkpointer=None, interrupt_before=None) -> StateGraph:
    if interrupt_before is None:
        interrupt_before = ["wait_character_review", "wait_script_review"]
    graph = StateGraph(VideoAgentState)

    async def generate_character(state: VideoAgentState) -> dict:
        if state.get("character_image_url"):
            return {"character_image_url": state["character_image_url"]}
        info = state["product_info"]
        prompt = CHARACTER_PROMPT.format(product_context=format_product_context(info)) + review_guidance(state, "character")
        result = await llm_chat("scriptwriter", "You are a character designer.", prompt)
        image_url = await generate_image(
            result, ref_image_url=state.get("main_image_data_uri") or None
        )
        return {"character_image_url": image_url}

    async def wait_character_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_script(state: VideoAgentState) -> dict:
        if state.get("script_content"):
            return {}
        info = state["product_info"]
        prompt = SCRIPT_PROMPT.format(product_context=format_product_context(info)) + review_guidance(state, "script")
        result = await llm_chat("scriptwriter", "You are a product speaking in first person.", prompt)
        data = json.loads(result)
        return {"script_content": data["script"], "voiceover_text": data["voiceover"]}

    async def wait_script_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_tts_and_lipsync(state: VideoAgentState) -> dict:
        if state.get("tts_audio_url"):
            audio_url = state["tts_audio_url"]
            words = state["tts_words"]
        else:
            tts_result = await generate_tts(
                state.get("edited_script_content") or state["script_content"]
            )
            audio_url = tts_result["audio_url"]
            words = tts_result["words"]
            tts_duration_seconds = tts_result["tts_duration_seconds"]
        if state.get("tts_audio_url"):
            tts_duration_seconds = state.get("tts_duration_seconds", 0)
        lipsync_url = state.get("lipsync_video_url") or await run_lipsync(
            state["character_image_url"], audio_url
        )
        return {
            "tts_audio_url": audio_url,
            "tts_words": words,
            "tts_duration_seconds": tts_duration_seconds,
            "lipsync_video_url": lipsync_url,
        }

    async def composite(state: VideoAgentState) -> dict:
        total_duration = float(state.get("tts_duration_seconds") or 0) or (
            sum(w["end"] for w in state.get("tts_words", []))
            if state.get("tts_words")
            else 30
        )
        subtitle_elements = ""
        for w in state.get("tts_words", []):
            subtitle_elements += (
                f'<div class="subtitle" data-start="{w["start"]}" '
                f'data-duration="{w["end"] - w["start"]}">{w["word"]}</div>\n'
            )
        options = await composition_options(state)
        html = HTML_TEMPLATE.format(
            total_duration=total_duration,
            audio_url=state["tts_audio_url"],
            lipsync_url=state["lipsync_video_url"],
            product_name=state["product_info"]["name"],
            subtitle_elements=subtitle_elements,
            subtitle_offset=options["subtitle_offset"],
            subtitle_size=options["subtitle_size"],
        )
        path = await render_hyperframes(html)
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node("generate_character", tracked_node("generate_character", generate_character))
    graph.add_node("wait_character_review", wait_character_review)
    graph.add_node("generate_script", tracked_node("generate_script", generate_script))
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_tts_and_lipsync", tracked_node("generate_tts_and_lipsync", generate_tts_and_lipsync))
    graph.add_node("composite", tracked_node("composite", composite))

    graph.set_entry_point("generate_character")
    graph.add_edge("generate_character", "wait_character_review")
    graph.add_edge("wait_character_review", "generate_script")
    graph.add_edge("generate_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_tts_and_lipsync")
    graph.add_edge("generate_tts_and_lipsync", "composite")
    graph.add_edge("composite", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )


personify_graph = build_personify_graph()
