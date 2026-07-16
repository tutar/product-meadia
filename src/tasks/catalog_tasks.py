import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from src.database import AsyncSessionLocal
from src.models.main_image_candidate import MainImageCandidate
from src.tasks.celery_app import celery_app
from src.models.outbox_event import OutboxEvent
from src.services.sample_catalog import SAMPLE_VERSION, SampleCatalogInitializer

async def _cleanup():
    async with AsyncSessionLocal() as db:
        result=await db.execute(delete(MainImageCandidate).where(MainImageCandidate.used_at.is_(None),MainImageCandidate.expires_at<=datetime.now(timezone.utc)).returning(MainImageCandidate.image_url))
        urls=list(result.scalars()); await db.commit(); return urls

@celery_app.task(name='cleanup_expired_main_image_candidates')
def cleanup_expired_main_image_candidates():
    return asyncio.run(_cleanup())


async def _dispatch_outbox():
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        events = (await db.execute(select(OutboxEvent).where(
            OutboxEvent.processed_at.is_(None), OutboxEvent.next_attempt_at <= now
        ).with_for_update(skip_locked=True).limit(20))).scalars().all()
        for event in events:
            event.attempts += 1
            event.last_attempt_at = now
            try:
                if event.event_type == "user.registered":
                    await SampleCatalogInitializer().initialize(db, event.payload["user_id"], SAMPLE_VERSION)
                event.processed_at = now
                event.error_message = None
            except Exception as exc:
                event.error_message = str(exc)
                event.next_attempt_at = now + timedelta(minutes=min(60, 2 ** event.attempts))
        await db.commit()
        return len(events)


@celery_app.task(name="dispatch_catalog_outbox")
def dispatch_catalog_outbox():
    return asyncio.run(_dispatch_outbox())
