from sqlalchemy import Text, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class ViralAnalysis(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "viral_analyses"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    source_url = Column(Text, nullable=False)
    original_script = Column(Text, nullable=True)
    script_structure = Column(JSONB, nullable=True)
    shot_list = Column(JSONB, default=list)
    style_params = Column(JSONB, nullable=True)

    task = relationship("VideoTask", back_populates="viral_analysis")
