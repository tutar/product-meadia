from __future__ import annotations

import hashlib
import posixpath
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.media.storage import ObjectNotFound, ObjectStorage
from src.models.media_asset import MediaAsset


def build_object_key(owner_user_id: uuid.UUID, category: str, filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return f"users/{owner_user_id}/{category}/{uuid.uuid4()}{suffix}"


class MediaService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        *,
        bucket: str | None = None,
        access_ttl_seconds: int | None = None,
    ):
        self.session = session
        self.storage = storage
        self.bucket = bucket or settings.media_bucket
        self.access_ttl_seconds = access_ttl_seconds or settings.media_access_ttl_seconds

    @staticmethod
    def checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    async def create_from_remote(
        self,
        *,
        owner_user_id: uuid.UUID,
        category: str,
        source_url: str,
        filename: str,
        fetch,
        content_type: str = "application/octet-stream",
        product_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        source_provider: str | None = None,
        idempotency_key: str | None = None,
    ) -> MediaAsset:
        """Persist a provider result without ever storing its URL as durable state."""
        data, detected_type = await fetch(source_url)
        return await self.create_asset(
            owner_user_id=owner_user_id,
            category=category,
            data=data,
            content_type=detected_type or content_type,
            filename=filename,
            product_id=product_id,
            task_id=task_id,
            source_provider=source_provider,
            idempotency_key=idempotency_key,
        )

    async def create_asset(
        self,
        *,
        owner_user_id: uuid.UUID,
        category: str,
        data: bytes,
        content_type: str,
        filename: str,
        product_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        source_provider: str | None = None,
        idempotency_key: str | None = None,
    ) -> MediaAsset:
        if idempotency_key:
            existing = await self.session.scalar(
                select(MediaAsset).where(
                    MediaAsset.owner_user_id == owner_user_id,
                    MediaAsset.idempotency_key == idempotency_key,
                    MediaAsset.status != "deleted",
                )
            )
            if existing:
                return existing

        object_key = build_object_key(owner_user_id, category, filename)
        checksum = self.checksum(data)
        await self.storage.upload(self.bucket, object_key, data, content_type)
        asset = MediaAsset(
            owner_user_id=owner_user_id,
            product_id=product_id,
            task_id=task_id,
            category=category,
            bucket=self.bucket,
            object_key=object_key,
            content_type=content_type,
            size_bytes=len(data),
            checksum=checksum,
            source_provider=source_provider,
            idempotency_key=idempotency_key,
            status="available",
        )
        try:
            self.session.add(asset)
            await self.session.flush()
        except Exception:
            await self.storage.delete(self.bucket, object_key)
            raise
        return asset

    async def get_owned_asset(
        self, asset_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> MediaAsset:
        asset = await self.session.scalar(
            select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.owner_user_id == owner_user_id,
                MediaAsset.status == "available",
            )
        )
        if not asset:
            raise ObjectNotFound(str(asset_id))
        return asset

    async def access_url(
        self, asset_id: uuid.UUID | str, owner_user_id: uuid.UUID
    ) -> str:
        if isinstance(asset_id, str):
            asset_id = uuid.UUID(asset_id)
        asset = await self.get_owned_asset(asset_id, owner_user_id)
        return await self.storage.presign_get(
            asset.bucket, asset.object_key, self.access_ttl_seconds
        )

    async def mark_superseded(
        self, asset: MediaAsset, *, retention_days: int = 7
    ) -> None:
        asset.superseded_at = datetime.now(timezone.utc)
        asset.delete_after = asset.superseded_at + timedelta(days=retention_days)
        await self.session.flush()

    async def delete_asset(self, asset: MediaAsset) -> None:
        await self.storage.delete(asset.bucket, asset.object_key)
        asset.status = "deleted"
        await self.session.flush()
