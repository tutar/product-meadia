from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class VoiceoverCandidate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "voiceover_candidates"

    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True)
    narration_text = Column(Text, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="pending_review")
    is_current = Column(Boolean, nullable=False, default=True)
    generation_context = Column(JSONB, nullable=False, default=dict)

    task = relationship("VideoTask", back_populates="voiceover_candidates")
    asset = relationship("MediaAsset")
