from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.media.storage import ObjectStorage
from src.config import settings
from src.models.media_asset import MediaAsset
from src.services.media_service import MediaService

FetchLegacy = Callable[[str], Awaitable[tuple[bytes, str, str]]]


async def migrate_legacy_url(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    owner_user_id: UUID,
    category: str,
    legacy_url: str,
    fetch: FetchLegacy,
    source_id: str,
    product_id: UUID | None = None,
    task_id: UUID | None = None,
) -> MediaAsset:
    """Migrate one legacy URL idempotently; unavailable rows fail closed."""
    key = f"legacy:{source_id}"
    existing = await session.scalar(
        select(MediaAsset).where(
            MediaAsset.owner_user_id == owner_user_id,
            MediaAsset.idempotency_key == key,
        )
    )
    if existing:
        return existing
    try:
        data, content_type, filename = await fetch(legacy_url)
    except Exception:
        asset = MediaAsset(
            owner_user_id=owner_user_id,
            product_id=product_id,
            task_id=task_id,
            category=category,
            bucket=settings.media_bucket,
            object_key=f"unavailable/{owner_user_id}/{source_id}",
            content_type="application/octet-stream",
            size_bytes=0,
            checksum="0" * 64,
            status="unavailable",
            idempotency_key=key,
        )
        session.add(asset)
        await session.flush()
        return asset
    return await MediaService(session, storage).create_asset(
        owner_user_id=owner_user_id,
        category=category,
        data=data,
        content_type=content_type,
        filename=filename,
        product_id=product_id,
        task_id=task_id,
        source_provider="legacy-migration",
        idempotency_key=key,
    )
