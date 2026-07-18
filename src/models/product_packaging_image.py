from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class ProductPackagingImage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "product_packaging_images"
    __table_args__ = (UniqueConstraint("product_id", "sort_order"),)

    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False)
    source = Column(String(20), nullable=False)
    prompt = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False)

    product = relationship("Product", back_populates="packaging_images")
    asset = relationship("MediaAsset")
