from sqlalchemy import String, Text, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class Script(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scripts"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    edited_content = Column(Text, nullable=True)
    image_prompts = Column(JSONB, default=list)
    voiceover_text = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending_review")

    task = relationship("VideoTask", back_populates="script")
