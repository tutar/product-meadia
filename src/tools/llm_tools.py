import json
import hashlib
from uuid import UUID
from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async
from src.tasks.generation_records import record_generation
from src.database import AsyncSessionLocal
from src.services.model_invocation import ModelInvocationBoundary

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@retry_async(max_attempts=3)
@observe(name="llm_chat")
async def llm_chat(
    model: str, system_prompt: str, user_message: str, temperature: float = 0.7,
    *, task_id: str | None = None, model_stage: str | None = None,
) -> str:
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
    resolved = None
    if task_id and model_stage:
        async with AsyncSessionLocal() as db:
            resolved = await ModelInvocationBoundary().complete(
                db, UUID(task_id), model_stage, messages, temperature=temperature,
            )
        content = resolved.content
        provider = resolved.model_resolution_snapshot["provider"]
        actual_model = resolved.model_resolution_snapshot["model_id"]
    else:
        resp = await client.chat.completions.create(model=model, messages=messages, temperature=temperature)
        content = resp.choices[0].message.content or ""
        provider, actual_model = "litellm", model
    await record_generation(provider, actual_model, {"temperature": temperature, "prompt_template_hash": hashlib.sha256(system_prompt.encode()).hexdigest()}, {"system": system_prompt, "user": user_message}, {"content": content}, {"model": actual_model, "messages": messages, "temperature": temperature})
    return content


@observe(name="analyze_video_structure")
async def analyze_video_structure(transcript: str, *, task_id: str | None = None) -> dict:
    system = """You are a video analysis expert. Analyze the given video transcript and extract:
1. Script structure: hook, pain_point, solution, product_showcase, cta — one paragraph each
2. Shot list: array of {index, description, duration_seconds, shot_type}
3. Style params: {transition, bgm_style, subtitle_position, subtitle_style}

Return ONLY valid JSON, no markdown wrapping."""
    text = await llm_chat("researcher", system, transcript, temperature=0.2, task_id=task_id, model_stage="viral_analysis" if task_id else None)
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)
