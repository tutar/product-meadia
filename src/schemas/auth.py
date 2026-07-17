from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewPreferences(BaseModel):
    auto_approve_script: bool = False
    auto_approve_images: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRequest(BaseModel):
    grant_type: str
    email: str | None = None
    password: str | None = None
    google_code: str | None = None
    redirect_uri: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
