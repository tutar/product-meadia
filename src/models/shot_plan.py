from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class ShotPlan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "shot_plans"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    shots = Column(JSONB, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="pending_review")
    task = relationship("VideoTask", back_populates="shot_plan")
