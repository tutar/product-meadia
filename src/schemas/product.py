from uuid import UUID
from pydantic import BaseModel, Field
from typing import Literal

class ProductDraft(BaseModel):
    category_id: UUID
    category_template_version: int
    name: str = Field(min_length=1,max_length=255)
    description: str | None = None
    selling_points: list[str] = []
    scenarios: list[str] = []
    attributes: dict[str, object] = {}

class ProductCreate(ProductDraft):
    main_image_url: str | None = None
    main_image_source: Literal["upload"] | None = None
    main_image_candidate_id: UUID | None = None
    main_image_asset_id: UUID | None = None

class ProductUpdate(ProductCreate): pass

class ProductResponse(ProductDraft):
    id: UUID
    main_image_url: str
    main_image_source: str
    main_image_asset_id: UUID | None = None
    model_config={'from_attributes':True}

class PaginatedProducts(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int

class MainImageCandidateResponse(BaseModel):
    candidate_id: UUID
    preview_url: str
    expires_at: object
