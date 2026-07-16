import asyncio
from datetime import datetime, timezone
from sqlalchemy import delete
from src.database import AsyncSessionLocal
from src.models.main_image_candidate import MainImageCandidate
from src.tasks.celery_app import celery_app

async def _cleanup():
    async with AsyncSessionLocal() as db:
        result=await db.execute(delete(MainImageCandidate).where(MainImageCandidate.used_at.is_(None),MainImageCandidate.expires_at<=datetime.now(timezone.utc)).returning(MainImageCandidate.image_url))
        urls=list(result.scalars()); await db.commit(); return urls

@celery_app.task(name='cleanup_expired_main_image_candidates')
def cleanup_expired_main_image_candidates():
    return asyncio.run(_cleanup())
