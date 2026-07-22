from sqlalchemy import String, Integer, Text, Column, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class VideoTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "video_tasks"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_snapshot = Column(JSONB, nullable=False)
    type = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    current_step = Column(Text, nullable=True)
    image_count = Column(Integer, nullable=False, default=4)
    error_message = Column(Text, nullable=True)
    result_video_url = Column(Text, nullable=True)
    result_video_asset_id = Column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    celery_task_id = Column(String(255), nullable=True)
    progress_log = Column(JSONB, nullable=False, default=list)
    # Existing tasks retain the legacy review flow.  New tasks opt into the
    # explicit voiceover/blueprint review workflow at creation time.
    voiceover_review_enabled = Column(Boolean, nullable=False, default=False)
    user = relationship("User")
    product = relationship("Product")
    script = relationship("Script", back_populates="task", uselist=False)
    creative_brief = relationship("CreativeBrief", back_populates="task", uselist=False)
    shot_plan = relationship("ShotPlan", back_populates="task", uselist=False)
    editing_blueprint = relationship("EditingBlueprint", back_populates="task", uselist=False)
    images = relationship("GeneratedImage", back_populates="task")
    video_candidates = relationship("VideoCandidate", back_populates="task")
    voiceover_candidates = relationship("VoiceoverCandidate", back_populates="task")
    generation_records = relationship("GenerationRecord", back_populates="task", passive_deletes=True)
    viral_analysis = relationship("ViralAnalysis", back_populates="task", uselist=False)
    result_video_asset = relationship("MediaAsset", foreign_keys=[result_video_asset_id])
