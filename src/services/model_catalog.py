"""The platform-maintained catalog; users can enable entries but cannot alter capabilities."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.model_configuration import ProviderModelCatalog


CATALOG_ENTRIES = (
    ("openai", "gpt-4.1-mini", "GPT-4.1 mini", ["creative_planning", "scriptwriting"], {}, True),
    ("openai", "gpt-image-1", "GPT Image 1", ["keyframe_image"], {"max_keyframes": 1}, False),
    ("google", "veo-3.0-generate-preview", "Veo 3", ["clip_video"], {"max_duration_seconds": 8, "max_keyframes": 2}, False),
    ("openai", "gpt-4o-mini-tts", "GPT-4o mini TTS", ["voice_generation"], {}, True),
    ("openai", "gpt-4o-transcribe", "GPT-4o Transcribe", ["viral_analysis"], {}, True),
)


async def ensure_provider_model_catalog(db: AsyncSession) -> None:
    existing = {(row.provider, row.model_id) for row in (await db.scalars(select(ProviderModelCatalog))).all()}
    for provider, model_id, display_name, capabilities, constraints, default_available in CATALOG_ENTRIES:
        if (provider, model_id) not in existing:
            db.add(ProviderModelCatalog(
                provider=provider, model_id=model_id, display_name=display_name,
                capabilities=capabilities, constraints=constraints,
                platform_default_available=default_available,
            ))
    await db.flush()
