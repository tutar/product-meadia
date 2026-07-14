from sqlalchemy import String, Integer, Text, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class GeneratedImage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "generated_images"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False)
    prompt = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending_review")

    task = relationship("VideoTask", back_populates="images")
