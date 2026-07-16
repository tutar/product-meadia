from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, UUIDMixin, TimestampMixin


class Product(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True)
    category = relationship("Category", back_populates="products")

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    selling_points = Column(JSONB, nullable=False, default=list)
    scenarios = Column(JSONB, nullable=False, default=list)
    main_image_url = Column(Text, nullable=False)
    main_image_source = Column(String(20), nullable=False)
    main_image_asset_id = Column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    attributes = Column(JSONB, nullable=False, default=dict)
    category_template_version = Column(Integer, nullable=False)

    user = relationship("User")
    category = relationship("Category", back_populates="products")
    main_image_asset = relationship("MediaAsset", foreign_keys=[main_image_asset_id])
