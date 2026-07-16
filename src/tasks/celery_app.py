from celery import Celery
from src.config import settings

celery_app = Celery(
    "perfume_video",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="perfume-video",
    imports=("src.tasks.video_tasks", "src.tasks.catalog_tasks"),
)
celery_app.conf.beat_schedule = {
    "cleanup-expired-main-images": {"task": "cleanup_expired_main_image_candidates", "schedule": 3600.0}
}
