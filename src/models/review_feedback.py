from sqlalchemy import Boolean, Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class ReviewFeedback(Base, UUIDMixin, TimestampMixin):
    """A user instruction attached to one rejected review artifact."""

    __tablename__ = "review_feedback"

    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False)
    target_type = Column(Text, nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=True)
    content = Column(Text, nullable=False)
    consumed = Column(Boolean, nullable=False, default=False)

    task = relationship("VideoTask")
