from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.media.storage import ObjectStorage
from src.models.media_asset import MediaAsset


def due_for_cleanup(status: str, delete_after, now: datetime) -> bool:
    return (
        status in {"superseded", "pending_delete"}
        and delete_after is not None
        and delete_after <= now
    )


async def cleanup_due_assets(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    now = now or datetime.now(timezone.utc)
    assets = (
        await session.scalars(
            select(MediaAsset)
            .where(
                MediaAsset.status.in_(("superseded", "pending_delete")),
                MediaAsset.delete_after <= now,
            )
            .limit(limit)
        )
    ).all()
    cleaned = 0
    for asset in assets:
        await storage.delete(asset.bucket, asset.object_key)
        asset.status = "deleted"
        cleaned += 1
    await session.commit()
    return cleaned
