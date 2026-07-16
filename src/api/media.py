from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import get_current_user
from src.database import get_async_session
from src.media.rustfs import create_rustfs_storage
from src.media.storage import ObjectNotFound
from src.schemas.media import MediaAccessResponse
from src.services.media_service import MediaService

router = APIRouter(prefix="/media", tags=["media"])


def get_media_service(db: AsyncSession = Depends(get_async_session)) -> MediaService:
    from src.config import settings

    return MediaService(db, create_rustfs_storage(settings))


@router.get("/{asset_id}/access", response_model=MediaAccessResponse)
async def access(
    asset_id: UUID,
    user=Depends(get_current_user),
    media: MediaService = Depends(get_media_service),
):
    try:
        url = await media.access_url(asset_id, user.id)
    except ObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="Media asset not found") from exc
    return MediaAccessResponse(
        asset_id=asset_id,
        url=url,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=media.access_ttl_seconds),
    )
