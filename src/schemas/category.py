from typing import Literal
from pydantic import BaseModel, Field, model_validator
from uuid import UUID

Selection = Literal['single_select','multi_select']

class CategoryAttributeInput(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    type: str
    required: bool = False
    options: list[str] = Field(default_factory=list)
    sort_order: int = 0

    @model_validator(mode='after')
    def validate_options(self):
        selection = self.type in ('single_select','multi_select')
        if selection:
            if not self.options or any(not x.strip() for x in self.options) or len(set(self.options)) != len(self.options):
                raise ValueError('selection types require unique non-empty options')
        elif self.options:
            raise ValueError('non-selection types require empty options')
        return self

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    attributes: list[CategoryAttributeInput] = []

class CategoryUpdate(CategoryCreate):
    template_version: int

class CategoryAttributeOut(CategoryAttributeInput):
    id: UUID
    model_config = {'from_attributes': True}

class CategoryOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    template_version: int
    attributes: list[CategoryAttributeOut] = []
    model_config = {'from_attributes': True}
