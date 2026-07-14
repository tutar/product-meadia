from sqlalchemy import String, Boolean, Column
from src.models.base import Base, UUIDMixin, TimestampMixin

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=True)
    google_id = Column(String(255), unique=True, nullable=True)
    role = Column(String(20), nullable=False, default="customer")  # "customer" | "operator"
    is_active = Column(Boolean, default=True)
