from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from src.models.base import Base, TimestampMixin, UUIDMixin


class OutboxEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "outbox_events"

    event_type = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
