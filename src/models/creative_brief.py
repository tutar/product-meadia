from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class CreativeBrief(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "creative_briefs"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    content = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="pending_review")
    task = relationship("VideoTask", back_populates="creative_brief")
