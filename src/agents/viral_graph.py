import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from src.agents.state import VideoAgentState
from src.config import settings
from src.tools.image_gen import generate_image
from src.tools.video_gen import generate_video
from src.tools.tts import generate_tts
from src.tools.render import render_hyperframes
from src.tools.transcription import transcribe_audio
from src.tools.llm_tools import llm_chat, analyze_video_structure

PROMPT = """Rewrite the following video script for a perfume product.
Replace the original product mentions with this product: {product_name}.
Keep the same structure, pacing, and emotional tone.
Original script: {original_script}
Product info: {product_info}

Return ONLY JSON: {{"script": "...", "voiceover": "...", "image_prompts": ["..."]}}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .clip {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .subtitle {{ position:absolute; bottom:10%; width:100%; text-align:center; color:#fff; font-size:32px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="viral-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio src="{audio_url}" data-start="0"></audio>
  {video_elements}
  {subtitle_elements}
</div>
</body></html>"""


def build_viral_graph() -> StateGraph:
    graph = StateGraph(VideoAgentState)

    async def analyze_source(state: VideoAgentState) -> dict:
        transcript = await transcribe_audio(state["viral_url"])
        analysis = await analyze_video_structure(transcript)
        return {"viral_analysis": analysis}

    async def wait_viral_confirm(state: VideoAgentState) -> dict:
        return {}

    async def generate_rewritten_script(state: VideoAgentState) -> dict:
        info = state["product_info"]
        user_prompt = PROMPT.format(
            product_name=info["name"],
            original_script=str(state.get("viral_analysis", {})),
            product_info=json.dumps(info),
        )
        result = await llm_chat("scriptwriter", "You are a video script adapter.", user_prompt)
        data = json.loads(result)
        return {
            "script_content": data["script"],
            "voiceover_text": data["voiceover"],
            "image_prompts": data["image_prompts"],
        }

    async def wait_script_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_images(state: VideoAgentState) -> dict:
        images = []
        for i, p in enumerate(state.get("image_prompts", [])):
            url = await generate_image(p)
            images.append({"sort_order": i, "image_url": url, "status": "pending_review"})
        return {"generated_images": images}

    async def wait_image_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_clips_and_voiceover(state: VideoAgentState) -> dict:
        clips = []
        for img in state.get("generated_images", []):
            if img.get("status") == "approved":
                clip = await generate_video(
                    prompt="Smooth cinematic movement, luxury product showcase",
                    image_urls=[img["image_url"]],
                )
                clips.append(clip)

        tts_result = await generate_tts(
            state.get("edited_script_content") or state["script_content"]
        )
        return {
            "video_clips": clips,
            "tts_audio_url": tts_result["audio_url"],
            "tts_words": tts_result["words"],
        }

    async def composite(state: VideoAgentState) -> dict:
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

    graph.add_node("analyze_source", analyze_source)
    graph.add_node("wait_viral_confirm", wait_viral_confirm)
    graph.add_node("generate_rewritten_script", generate_rewritten_script)
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_images", generate_images)
    graph.add_node("wait_image_review", wait_image_review)
    graph.add_node("generate_clips_and_voiceover", generate_clips_and_voiceover)
    graph.add_node("composite", composite)

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
        checkpointer=PostgresSaver(conn=settings.database_url),
        interrupt_before=["wait_viral_confirm", "wait_script_review", "wait_image_review"],
    )


viral_graph = build_viral_graph()
