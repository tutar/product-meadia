import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from src.agents.state import VideoAgentState
from src.config import settings
from src.tools.image_gen import generate_image
from src.tools.tts import generate_tts
from src.tools.lipsync import run_lipsync
from src.tools.render import render_hyperframes
from src.tools.llm_tools import llm_chat

CHARACTER_PROMPT = """Design a personified character for this perfume:
Product: {product_name}
Top notes: {top_note}
Middle notes: {middle_note}
Base notes: {base_note}
Scenarios: {scenarios}

Describe the character as an image generation prompt: age, gender, clothing style,
expression, setting. The character should visually embody the perfume's personality.
Output ONLY the image prompt, no commentary."""

SCRIPT_PROMPT = """You are this perfume speaking in first person. Introduce yourself:
"I am {product_name}. My top notes are {top_note}, middle notes {middle_note},
base notes {base_note}. I'm perfect for {scenarios}..."

Write a 30-second first-person monologue.
Return ONLY JSON: {{"script": "...", "voiceover": "..."}}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .main {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .overlay {{ position:absolute; top:5%; left:5%; color:#fff; font-size:28px; text-shadow:0 2px 8px rgba(0,0,0,0.7); }}
  .subtitle {{ position:absolute; bottom:12%; width:100%; text-align:center; color:#fff; font-size:30px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="personify-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio src="{audio_url}" data-start="0"></audio>
  <video class="main" src="{lipsync_url}" data-start="0" data-duration="{total_duration}" muted playsinline></video>
  <div class="overlay" data-start="0" data-duration="{total_duration}">{product_name}</div>
  {subtitle_elements}
</div>
</body></html>"""


def build_personify_graph() -> StateGraph:
    graph = StateGraph(VideoAgentState)

    async def generate_character(state: VideoAgentState) -> dict:
        info = state["product_info"]
        prompt = CHARACTER_PROMPT.format(
            product_name=info["name"],
            top_note=info.get("top_note", ""),
            middle_note=info.get("middle_note", ""),
            base_note=info.get("base_note", ""),
            scenarios=", ".join(info.get("scenarios", [])),
        )
        result = await llm_chat("scriptwriter", "You are a character designer.", prompt)
        image_url = await generate_image(result)
        return {"character_image_url": image_url}

    async def wait_character_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_script(state: VideoAgentState) -> dict:
        info = state["product_info"]
        prompt = SCRIPT_PROMPT.format(
            product_name=info["name"],
            top_note=info.get("top_note", ""),
            middle_note=info.get("middle_note", ""),
            base_note=info.get("base_note", ""),
            scenarios=", ".join(info.get("scenarios", [])),
        )
        result = await llm_chat("scriptwriter", "You are a perfume speaking in first person.", prompt)
        data = json.loads(result)
        return {"script_content": data["script"], "voiceover_text": data["voiceover"]}

    async def wait_script_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_tts_and_lipsync(state: VideoAgentState) -> dict:
        tts_result = await generate_tts(
            state.get("edited_script_content") or state["script_content"]
        )
        lipsync_url = await run_lipsync(
            state["character_image_url"], tts_result["audio_url"]
        )
        return {
            "tts_audio_url": tts_result["audio_url"],
            "tts_words": tts_result["words"],
            "lipsync_video_url": lipsync_url,
        }

    async def composite(state: VideoAgentState) -> dict:
        total_duration = (
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
        html = HTML_TEMPLATE.format(
            total_duration=total_duration,
            audio_url=state["tts_audio_url"],
            lipsync_url=state["lipsync_video_url"],
            product_name=state["product_info"]["name"],
            subtitle_elements=subtitle_elements,
        )
        path = await render_hyperframes(html, "/tmp")
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node("generate_character", generate_character)
    graph.add_node("wait_character_review", wait_character_review)
    graph.add_node("generate_script", generate_script)
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_tts_and_lipsync", generate_tts_and_lipsync)
    graph.add_node("composite", composite)

    graph.set_entry_point("generate_character")
    graph.add_edge("generate_character", "wait_character_review")
    graph.add_edge("wait_character_review", "generate_script")
    graph.add_edge("generate_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_tts_and_lipsync")
    graph.add_edge("generate_tts_and_lipsync", "composite")
    graph.add_edge("composite", END)

    return graph.compile(
        checkpointer=PostgresSaver(conn=settings.database_url),
        interrupt_before=["wait_character_review", "wait_script_review"],
    )


personify_graph = build_personify_graph()
