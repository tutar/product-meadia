from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async
from src.tasks.generation_records import record_generation
from src.database import AsyncSessionLocal
from src.services.model_invocation import ModelInvocationBoundary
from src.services.image_concurrency import image_generation_slot

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@retry_async(max_attempts=3)
@observe(name="generate_image")
async def generate_image(prompt: str, ref_image_url: str | None = None, *, task_id: str | None = None) -> str:
    async with image_generation_slot():
        return await _generate_image(prompt, ref_image_url=ref_image_url, task_id=task_id)


async def _generate_image(prompt: str, ref_image_url: str | None = None, *, task_id: str | None = None) -> str:
    extra_body = {}
    if ref_image_url:
        extra_body["image"] = [ref_image_url]

    if task_id:
        from uuid import UUID
        async with AsyncSessionLocal() as db:
            resolved = await ModelInvocationBoundary().generate_image(
                db, UUID(task_id), prompt, reference_image_url=ref_image_url,
            )
        snapshot = resolved.model_resolution_snapshot
        provider = snapshot.get("provider") or snapshot["adapter"]
        model = snapshot["model_id"]
        image_url = resolved.content
    else:
        response = await client.images.generate(
            model="agnes-image-2.1-flash", prompt=prompt, size="1024x1024",
            extra_body=extra_body if extra_body else None,
        )
        provider, model, image_url = "litellm", "agnes-image-2.1-flash", response.data[0].url
    await record_generation(provider, model, {"size": "1024x1024"}, {"prompt": prompt, "reference_media": "provided" if ref_image_url else None}, {"result": "image generated"}, {"model": model, "prompt": prompt, "size": "1024x1024", "reference_media": "provided" if ref_image_url else None})
    return image_url
