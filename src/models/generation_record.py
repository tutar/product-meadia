from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class GenerationRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "generation_records"

    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(40), nullable=False, index=True)
    substep = Column(String(80), nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    provider = Column(String(80), nullable=False)
    model = Column(String(160), nullable=False)
    parameters = Column(JSONB, nullable=False, default=dict)
    normalized_input = Column(JSONB, nullable=False, default=dict)
    normalized_output = Column(JSONB, nullable=False, default=dict)
    provider_payload = Column(JSONB, nullable=False, default=dict)
    media_asset_ids = Column(JSONB, nullable=False, default=list)
    provenance = Column(JSONB, nullable=False, default=dict)
    training_candidate = Column(String(20), nullable=False, default="pending_review")

    task = relationship("VideoTask", back_populates="generation_records")
