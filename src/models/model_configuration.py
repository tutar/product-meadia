"""Persistent, non-secret model-selection records.

Credentials are deliberately represented only by ciphertext.  No ORM attribute
contains plaintext, which prevents accidental API serialization.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class ProviderModelCatalog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "provider_model_catalog"

    provider = Column(String(80), nullable=False)
    model_id = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    capabilities = Column(JSONB, nullable=False, default=list)
    constraints = Column(JSONB, nullable=False, default=dict)
    capability_revision = Column(Integer, nullable=False, default=1)
    platform_default_available = Column(Boolean, nullable=False, default=False)
    is_available = Column(Boolean, nullable=False, default=True)

    __table_args__ = (UniqueConstraint("provider", "model_id", name="uq_provider_model_catalog_identity"),)


class ModelConfiguration(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "model_configurations"

    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    catalog_model_id = Column(UUID(as_uuid=True), ForeignKey("provider_model_catalog.id", ondelete="RESTRICT"), nullable=False)
    credential_ciphertext = Column(Text, nullable=True)
    uses_platform_default = Column(Boolean, nullable=False, default=False)
    verification_status = Column(String(20), nullable=False, default="unverified")
    verification_error = Column(String(500), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User")
    catalog_model = relationship("ProviderModelCatalog")


class StageModelDefault(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stage_model_defaults"

    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String(40), nullable=False)
    model_configuration_id = Column(UUID(as_uuid=True), ForeignKey("model_configurations.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (UniqueConstraint("owner_user_id", "stage", name="uq_stage_model_defaults_owner_stage"),)

    model_configuration = relationship("ModelConfiguration")


class StageModelSelection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stage_model_selections"

    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String(40), nullable=False)
    model_configuration_id = Column(UUID(as_uuid=True), ForeignKey("model_configurations.id", ondelete="RESTRICT"), nullable=False)
    selection_version = Column(Integer, nullable=False, default=1)
    resolution_snapshot = Column(JSONB, nullable=False, default=dict)
    availability_status = Column(String(30), nullable=False, default="available")
    started_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("task_id", "stage", name="uq_stage_model_selections_task_stage"),)

    model_configuration = relationship("ModelConfiguration")
