import json
from openai import AsyncOpenAI
from src.config import settings
from langfuse.decorators import observe
from src.tools.retry import retry_async

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@retry_async(max_attempts=3)
@observe(name="llm_chat")
async def llm_chat(model: str, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content


@observe(name="analyze_video_structure")
async def analyze_video_structure(transcript: str) -> dict:
    system = """You are a video analysis expert. Analyze the given video transcript and extract:
1. Script structure: hook, pain_point, solution, product_showcase, cta — one paragraph each
2. Shot list: array of {index, description, duration_seconds, shot_type}
3. Style params: {transition, bgm_style, subtitle_position, subtitle_style}

Return ONLY valid JSON, no markdown wrapping."""
    text = await llm_chat("researcher", system, transcript, temperature=0.2)
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)
