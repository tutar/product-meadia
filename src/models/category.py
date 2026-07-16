from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class Category(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    template_version = Column(Integer, nullable=False, default=1)

    user = relationship("User")
    attributes = relationship(
        "CategoryAttribute", back_populates="category", cascade="all, delete-orphan"
    )
    products = relationship("Product", back_populates="category")


class CategoryAttribute(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "category_attributes"
    __table_args__ = (UniqueConstraint("category_id", "key"),)

    category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    key = Column(String(100), nullable=False)
    label = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False)
    required = Column(Boolean, nullable=False, default=False)
    options = Column(JSONB, nullable=False, default=list)
    sort_order = Column(Integer, nullable=False, default=0)

    category = relationship("Category", back_populates="attributes")
