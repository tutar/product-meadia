from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class MediaAsset(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "media_assets"

    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=True)
    category = Column(String(30), nullable=False)
    bucket = Column(String(255), nullable=False)
    object_key = Column(Text, nullable=False, unique=True)
    content_type = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    checksum = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="available")
    source_provider = Column(String(100), nullable=True)
    idempotency_key = Column(String(255), nullable=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    delete_after = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User")
