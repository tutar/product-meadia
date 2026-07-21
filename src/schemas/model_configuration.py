from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ProviderModelCatalogResponse(BaseModel):
    id: UUID
    provider: str
    model_id: str
    display_name: str
    capabilities: list[str]
    constraints: dict
    capability_revision: int
    platform_default_available: bool
    is_available: bool

    model_config = {"from_attributes": True}


class ModelConfigurationCreate(BaseModel):
    catalog_model_id: UUID
    credential: str | None = Field(default=None, min_length=1, max_length=20000)
    use_platform_default: bool = False

    @model_validator(mode="after")
    def has_exactly_one_credential_source(self):
        if bool(self.credential) == self.use_platform_default:
            raise ValueError("Provide a credential or request the platform default, but not both")
        return self


class ModelConfigurationUpdate(BaseModel):
    credential: str | None = Field(default=None, min_length=1, max_length=20000)
    use_platform_default: bool | None = None


class ModelConfigurationResponse(BaseModel):
    id: UUID
    catalog_model_id: UUID
    provider: str
    model_id: str
    display_name: str
    capabilities: list[str]
    constraints: dict
    uses_platform_default: bool
    verification_status: str
    verification_error: str | None
    verified_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StageModelDefaultUpsert(BaseModel):
    model_configuration_id: UUID


class StageModelDefaultResponse(BaseModel):
    stage: str
    model_configuration_id: UUID
