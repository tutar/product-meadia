from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class EditingBlueprint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "editing_blueprints"

    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    entries = Column(JSONB, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="approved")

    task = relationship("VideoTask", back_populates="editing_blueprint")
