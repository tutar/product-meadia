from openai import AsyncOpenAI
from src.config import settings
from langfuse import observe
from src.tools.retry import retry_async
from src.tasks.generation_records import record_generation

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@retry_async(max_attempts=3)
@observe(name="generate_image")
async def generate_image(prompt: str, ref_image_url: str | None = None) -> str:
    extra_body = {}
    if ref_image_url:
        extra_body["image"] = [ref_image_url]

    response = await client.images.generate(
        model="agnes-image-2.1-flash",
        prompt=prompt,
        size="1024x1024",
        extra_body=extra_body if extra_body else None,
    )
    await record_generation("litellm", "agnes-image-2.1-flash", {"size": "1024x1024"}, {"prompt": prompt, "reference_media": "provided" if ref_image_url else None}, {"result": "image generated"}, {"model": "agnes-image-2.1-flash", "prompt": prompt, "size": "1024x1024", "reference_media": "provided" if ref_image_url else None})
    return response.data[0].url
