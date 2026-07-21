from datetime import datetime
from ipaddress import ip_address
from urllib.parse import urlparse
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
    catalog_model_id: UUID | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    adapter: str | None = Field(default=None, min_length=1, max_length=80)
    api_base: str | None = Field(default=None, max_length=1000)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    capabilities: list[str] | None = None
    constraints: dict | None = None
    credential: str | None = Field(default=None, min_length=1, max_length=20000)
    use_platform_default: bool = False

    @model_validator(mode="after")
    def has_exactly_one_credential_source(self):
        if not self.credential and not self.use_platform_default:
            raise ValueError("Provide a credential")
        if self.credential and self.use_platform_default:
            raise ValueError("Provide a credential or request the platform default, but not both")
        if self.catalog_model_id is None:
            missing = [name for name in ("display_name", "adapter", "model_id", "capabilities") if getattr(self, name) in (None, [])]
            if missing:
                raise ValueError("Private model configurations require " + ", ".join(missing))
        return self

    @model_validator(mode="after")
    def private_endpoint_is_reachable_and_safe(self):
        if self.api_base is None:
            return self
        parsed = urlparse(self.api_base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Private endpoint must be an absolute HTTP(S) URL")
        hostname = parsed.hostname.lower()
        private_hostname = hostname == "localhost" or hostname.endswith(".local") or hostname.endswith(".internal")
        try:
            private_hostname = private_hostname or ip_address(hostname).is_private or ip_address(hostname).is_loopback
        except ValueError:
            pass
        if parsed.scheme == "http" and not private_hostname:
            raise ValueError("Public private-model endpoints must use HTTPS")
        return self


class ModelConfigurationUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    adapter: str | None = Field(default=None, min_length=1, max_length=80)
    api_base: str | None = Field(default=None, max_length=1000)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    capabilities: list[str] | None = None
    constraints: dict | None = None
    credential: str | None = Field(default=None, min_length=1, max_length=20000)

    @model_validator(mode="after")
    def updated_endpoint_is_safe(self):
        if self.api_base is None:
            return self
        ModelConfigurationCreate(
            display_name="endpoint-validation", adapter="openai_compatible", api_base=self.api_base,
            model_id="endpoint-validation", capabilities=["scriptwriting"], credential="endpoint-validation",
        )
        return self


class ModelConfigurationResponse(BaseModel):
    id: UUID
    catalog_model_id: UUID | None
    adapter: str
    api_base: str | None
    provider: str
    model_id: str
    display_name: str
    capabilities: list[str]
    constraints: dict
    revision: int
    uses_platform_default: bool
    verification_status: str
    verification_error: str | None
    first_use_eligible: bool
    verified_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StageModelDefaultUpsert(BaseModel):
    model_configuration_id: UUID


class StageModelDefaultResponse(BaseModel):
    stage: str
    model_configuration_id: UUID
