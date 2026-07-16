from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import get_current_user
from src.database import get_async_session
from src.models.catalog_initialization import CatalogInitialization
from src.services.sample_catalog import SAMPLE_VERSION

router = APIRouter(tags=["initialization"])


@router.get("/initialization-status")
async def initialization_status(db: AsyncSession = Depends(get_async_session), user=Depends(get_current_user)):
    row = (await db.execute(select(CatalogInitialization).where(
        CatalogInitialization.user_id == user.id,
        CatalogInitialization.sample_version == SAMPLE_VERSION,
    ))).scalar_one_or_none()
    if row is None:
        return {"status": "pending", "sample_version": SAMPLE_VERSION, "attempts": 0, "error_message": None, "completed_at": None}
    return row
