from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class ProductCreate(BaseModel):
    name: str
    top_note: str | None = None
    middle_note: str | None = None
    base_note: str | None = None
    scenarios: list[str] = []
    main_image_url: str | None = None


class ProductResponse(ProductCreate):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
