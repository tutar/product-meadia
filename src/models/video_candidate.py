from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class VideoCandidate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "video_candidates"

    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(20), nullable=False)  # clip | composition
    sort_order = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="pending_review")
    is_current = Column(Boolean, nullable=False, default=True)
    generation_context = Column(JSONB, nullable=False, default=dict)
    recomposed_from_candidate_id = Column(UUID(as_uuid=True), ForeignKey("video_candidates.id", ondelete="SET NULL"), nullable=True)

    task = relationship("VideoTask", back_populates="video_candidates")
    asset = relationship("MediaAsset")
