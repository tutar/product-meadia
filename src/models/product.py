from sqlalchemy import String, Text, Column
from sqlalchemy.dialects.postgresql import JSONB
from src.models.base import Base, UUIDMixin, TimestampMixin

class Product(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"
    name = Column(String(255), nullable=False)
    top_note = Column(Text, nullable=True)
    middle_note = Column(Text, nullable=True)
    base_note = Column(Text, nullable=True)
    scenarios = Column(JSONB, default=list)
    main_image_url = Column(Text, nullable=True)
