import time
from openai import AsyncOpenAI
from src.config import settings
from langfuse.decorators import observe

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@observe(name="generate_image")
async def generate_image(prompt: str, ref_image_url: str | None = None) -> str:
    extra_body = {}
    if ref_image_url:
        extra_body["image"] = [ref_image_url]

    for attempt in range(3):
        try:
            response = await client.images.generate(
                model="agnes-image-2.1-flash",
                prompt=prompt,
                size="1024x1024",
                extra_body=extra_body if extra_body else None,
            )
            return response.data[0].url
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("generate_image failed after 3 retries")
