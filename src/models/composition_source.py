from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class CompositionSourceSnapshot(Base, UUIDMixin, TimestampMixin):
    """Immutable replay input retained for one Final Composition Candidate."""

    __tablename__ = "composition_source_snapshots"

    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("video_candidates.id", ondelete="CASCADE"), nullable=True, unique=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True)
    generation_record_id = Column(UUID(as_uuid=True), ForeignKey("generation_records.id", ondelete="SET NULL"), nullable=True)
    source_kind = Column(String(20), nullable=False, default="captured")
    canonical_html_checksum = Column(String(64), nullable=False)
    input_asset_ids = Column(JSONB, nullable=False, default=list)
    render_spec = Column(JSONB, nullable=False, default=dict)
    provenance = Column(JSONB, nullable=False, default=dict)
    reconstruction_notes = Column(Text, nullable=True)

    task = relationship("VideoTask")
    candidate = relationship("VideoCandidate")
    asset = relationship("MediaAsset")
    generation_record = relationship("GenerationRecord")
