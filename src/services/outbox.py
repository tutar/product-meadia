from datetime import datetime, timezone
from uuid import UUID

from src.models.outbox_event import OutboxEvent


async def record_event(db, event_type: str, aggregate_id: UUID, payload: dict) -> OutboxEvent:
    event_payload = dict(payload)
    event_payload.setdefault("aggregate_id", str(aggregate_id))
    event = OutboxEvent(
        event_type=event_type,
        payload=event_payload,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(event)
    return event
