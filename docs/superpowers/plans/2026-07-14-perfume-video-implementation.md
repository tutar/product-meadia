# 香水短视频生成应用 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-stack perfume short-video AI generation app with three video types (promo, viral, personify) using DeepAgents + FastAPI + React.

**Architecture:** FastAPI backend with Celery async tasks, DeepAgents/LangGraph for multi-step agent orchestration with human-in-the-loop checkpoints, React SPA frontend. Reuses agent-infra services (LiteLLM, PostgreSQL, Redis, RustFS, FunASR, Langfuse).

**Tech Stack:** Python 3.11+, FastAPI, Celery, DeepAgents (LangChain + LangGraph), SQLAlchemy async, React + Vite + TypeScript, HyperFrames CLI, FFmpeg

## Global Constraints

- All LLM calls via LiteLLM at `http://localhost:4000/v1` with `sk-litellm-master`
- Agnes Image via LiteLLM `/v1/images/generations`, Agnes Video via `https://apihub.agnes-ai.com` directly
- VoxCPM2 TTS, LatentSync 1.6 lipsync — assumed available as HTTP services
- PostgreSQL database `perfume_video`, RustFS object storage at `http://localhost:8001`
- HyperFrames requires Node.js 22+ on the host
- Langfuse observability on all LLM calls via `@observe` decorator
- JWT auth (email/password + Google OAuth), all API endpoints (except auth) require Bearer token
- Celery broker is Redis at `redis://localhost:6379/0`
- Project root: `/home/tutar/work/video-infra/product-meadia`

---

### Task 1: Project scaffolding and configuration

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/config.py`

**Interfaces:**
- Produces: `src/config.Settings` — Pydantic BaseSettings, consumed by all modules

- [ ] **Step 1: Write requirements.txt**

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.1
celery[redis]==5.4.0
redis==5.2.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.20
httpx==0.28.1
authlib==1.4.0
pydantic-settings==2.7.1
langchain==0.3.14
langgraph==0.2.61
deepagents==0.1.0
langfuse==2.60.0
openai==1.58.1
websockets==14.1
```

- [ ] **Step 2: Write .env.example**

```bash
# App
APP_ENV=development
SECRET_KEY=change-me-64-chars-random
DATABASE_URL=postgresql+asyncpg://agent:agent123@localhost:5432/perfume_video
CELERY_BROKER_URL=redis://localhost:6379/0

# LiteLLM
LITELLM_BASE_URL=http://localhost:4000/v1
LITELLM_API_KEY=sk-litellm-master

# Agnes Video
AGNES_VIDEO_API_KEY=sk-your-agnes-ai-key
AGNES_VIDEO_BASE_URL=https://apihub.agnes-ai.com

# VoxCPM2
VOXCPM2_BASE_URL=http://localhost:8080

# LatentSync
LATENTSYNC_BASE_URL=http://localhost:8090

# RustFS
RUSTFS_BASE_URL=http://localhost:8001

# FunASR
FUNASR_BASE_URL=http://localhost:8021/v1

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-default
LANGFUSE_SECRET_KEY=sk-lf-default
LANGFUSE_HOST=http://localhost:3060
```

- [ ] **Step 3: Write src/config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://agent:agent123@localhost:5432/perfume_video"
    celery_broker_url: str = "redis://localhost:6379/0"

    litellm_base_url: str = "http://localhost:4000/v1"
    litellm_api_key: str = "sk-litellm-master"

    agnes_video_api_key: str = ""
    agnes_video_base_url: str = "https://apihub.agnes-ai.com"

    voxcpm2_base_url: str = "http://localhost:8080"
    latentsync_base_url: str = "http://localhost:8090"
    rustfs_base_url: str = "http://localhost:8001"
    funasr_base_url: str = "http://localhost:8021/v1"

    google_client_id: str = ""
    google_client_secret: str = ""

    langfuse_public_key: str = "pk-lf-default"
    langfuse_secret_key: str = "sk-lf-default"
    langfuse_host: str = "http://localhost:3060"

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: Run pip install**

```bash
cd /home/tutar/work/video-infra/product-meadia
pip install -r requirements.txt
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example src/__init__.py src/config.py
git commit -m "feat: project scaffolding with FastAPI + LangGraph + Celery stack"
```

---

### Task 2: Database engine and session

**Files:**
- Create: `src/database.py`

**Interfaces:**
- Produces: `src/database.get_async_session()` — async generator yielding SQLAlchemy AsyncSession
- Produces: `src/database.engine` — AsyncEngine

- [ ] **Step 1: Write src/database.py**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings

engine = create_async_engine(settings.database_url, echo=(settings.app_env == "development"))
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 2: Verify with a quick Python import check**

```bash
cd /home/tutar/work/video-infra/product-meadia
python -c "from src.config import settings; print(settings.database_url)"
```

- [ ] **Step 3: Commit**

```bash
git add src/database.py
git commit -m "feat: async SQLAlchemy engine and session factory"
```

---

### Task 3: SQLAlchemy models

**Files:**
- Create: `src/models/__init__.py`
- Create: `src/models/base.py`
- Create: `src/models/user.py`
- Create: `src/models/product.py`
- Create: `src/models/task.py`
- Create: `src/models/script.py`
- Create: `src/models/generated_image.py`
- Create: `src/models/viral_analysis.py`

**Interfaces:**
- Produces: `User`, `Product`, `VideoTask`, `Script`, `GeneratedImage`, `ViralAnalysis` ORM models

- [ ] **Step 1: Write src/models/base.py**

```python
from sqlalchemy.orm import DeclarativeBase
import uuid
from sqlalchemy import Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

class Base(DeclarativeBase):
    pass

class UUIDMixin:
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 2: Write src/models/user.py**

```python
from sqlalchemy import String, Boolean, Column
from src.models.base import Base, UUIDMixin, TimestampMixin

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=True)
    google_id = Column(String(255), unique=True, nullable=True)
    role = Column(String(20), nullable=False, default="customer")  # "customer" | "operator"
    is_active = Column(Boolean, default=True)
```

- [ ] **Step 3: Write src/models/product.py**

```python
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
```

- [ ] **Step 4: Write src/models/task.py**

```python
from sqlalchemy import String, Integer, Text, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class VideoTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "video_tasks"
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    current_step = Column(Text, nullable=True)
    image_count = Column(Integer, nullable=False, default=4)
    error_message = Column(Text, nullable=True)
    result_video_url = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)

    product = relationship("Product")
    script = relationship("Script", back_populates="task", uselist=False)
    images = relationship("GeneratedImage", back_populates="task")
    viral_analysis = relationship("ViralAnalysis", back_populates="task", uselist=False)
```

- [ ] **Step 5: Write src/models/script.py**

```python
from sqlalchemy import String, Text, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class Script(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scripts"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    edited_content = Column(Text, nullable=True)
    image_prompts = Column(JSONB, default=list)
    voiceover_text = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending_review")

    task = relationship("VideoTask", back_populates="script")
```

- [ ] **Step 6: Write src/models/generated_image.py**

```python
from sqlalchemy import String, Integer, Text, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class GeneratedImage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "generated_images"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=False)
    prompt = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending_review")

    task = relationship("VideoTask", back_populates="images")
```

- [ ] **Step 7: Write src/models/viral_analysis.py**

```python
from sqlalchemy import Text, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.models.base import Base, UUIDMixin, TimestampMixin

class ViralAnalysis(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "viral_analyses"
    task_id = Column(UUID(as_uuid=True), ForeignKey("video_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    source_url = Column(Text, nullable=False)
    original_script = Column(Text, nullable=True)
    script_structure = Column(JSONB, nullable=True)
    shot_list = Column(JSONB, default=list)
    style_params = Column(JSONB, nullable=True)

    task = relationship("VideoTask", back_populates="viral_analysis")
```

- [ ] **Step 8: Write src/models/__init__.py**

```python
from src.models.base import Base
from src.models.user import User
from src.models.product import Product
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis

__all__ = ["Base", "User", "Product", "VideoTask", "Script", "GeneratedImage", "ViralAnalysis"]
```

- [ ] **Step 9: Commit**

```bash
git add src/models/
git commit -m "feat: SQLAlchemy models for products, tasks, scripts, images, viral analysis"
```

---

### Task 4: Create database and run schema

**Files:**
- Modify: `db/schema.sql` — add users table

**Note:** The agent-infra provides PostgreSQL. Create the database and add the users table.

- [ ] **Step 1: Add users table to db/schema.sql**

Append to `db/schema.sql`:

```sql
-- 用户表
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(320) NOT NULL UNIQUE,
    hashed_password VARCHAR(128),
    google_id       VARCHAR(255) UNIQUE,
    role            VARCHAR(20) NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'operator')),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_google_id ON users(google_id);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

- [ ] **Step 2: Create database in PostgreSQL**

```bash
docker compose -f /home/tutar/work/agent-infra/infra/docker-compose.yml exec postgres \
  psql -U agent -c "CREATE DATABASE perfume_video;"
```

- [ ] **Step 3: Run DDL**

```bash
docker compose -f /home/tutar/work/agent-infra/infra/docker-compose.yml exec -T postgres \
  psql -U agent -d perfume_video < /home/tutar/work/video-infra/product-meadia/db/schema.sql
```

- [ ] **Step 4: Verify tables**

```bash
docker compose -f /home/tutar/work/agent-infra/infra/docker-compose.yml exec postgres \
  psql -U agent -d perfume_video -c "\dt"
```

Expected output includes: `products`, `video_tasks`, `scripts`, `generated_images`, `viral_analyses`, `users`

- [ ] **Step 5: Commit**

```bash
git add db/schema.sql
git commit -m "feat: add users table and create perfume_video database"
```

---

### Task 5: Pydantic schemas

**Files:**
- Create: `src/schemas/__init__.py`
- Create: `src/schemas/auth.py`
- Create: `src/schemas/product.py`
- Create: `src/schemas/task.py`

**Interfaces:**
- Produces: `UserCreate`, `UserResponse`, `TokenResponse`, `ProductCreate`, `ProductResponse`, `TaskCreate`, `TaskResponse`, `ScriptResponse`, `ScriptUpdate`, `ImageResponse`, `ImageReview`, `ViralAnalysisResponse` Pydantic models

- [ ] **Step 1: Write src/schemas/auth.py**

```python
from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRequest(BaseModel):
    grant_type: str  # "password" | "google_oauth"
    email: str | None = None
    password: str | None = None
    google_code: str | None = None

class RefreshRequest(BaseModel):
    refresh_token: str
```

- [ ] **Step 2: Write src/schemas/product.py**

```python
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
```

- [ ] **Step 3: Write src/schemas/task.py**

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class TaskCreate(BaseModel):
    product_id: UUID
    type: str  # "promo" | "viral" | "personify"
    image_count: int = 4
    viral_url: str | None = None
    script_overrides: dict | None = None
    style_overrides: dict | None = None

class ScriptResponse(BaseModel):
    id: UUID
    task_id: UUID
    content: str
    edited_content: str | None
    image_prompts: list[str]
    voiceover_text: str | None
    status: str

    model_config = {"from_attributes": True}

class ScriptUpdate(BaseModel):
    approved: bool
    edited_content: str | None = None
    image_prompts: list[str] | None = None

class ImageResponse(BaseModel):
    id: UUID
    task_id: UUID
    prompt: str
    image_url: str | None
    sort_order: int
    status: str

    model_config = {"from_attributes": True}

class ImageReview(BaseModel):
    action: str  # "approve" | "reject"

class ViralAnalysisResponse(BaseModel):
    id: UUID
    task_id: UUID | None
    source_url: str
    original_script: str | None
    script_structure: dict | None
    shot_list: list[dict]
    style_params: dict | None

    model_config = {"from_attributes": True}

class TaskResponse(BaseModel):
    id: UUID
    product_id: UUID
    type: str
    status: str
    current_step: str | None
    image_count: int
    error_message: str | None
    result_video_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Write src/schemas/__init__.py**

```python
from src.schemas.auth import UserCreate, UserResponse, TokenResponse, TokenRequest, RefreshRequest
from src.schemas.product import ProductCreate, ProductResponse
from src.schemas.task import (
    TaskCreate, TaskResponse, ScriptResponse, ScriptUpdate,
    ImageResponse, ImageReview, ViralAnalysisResponse
)
```

- [ ] **Step 5: Commit**

```bash
git add src/schemas/
git commit -m "feat: Pydantic schemas for auth, products, and tasks"
```

---

### Task 6: JWT and auth utilities

**Files:**
- Create: `src/auth/__init__.py`
- Create: `src/auth/jwt.py`
- Create: `src/auth/deps.py`

**Interfaces:**
- Produces: `create_access_token(data: dict) -> str`, `create_refresh_token(data: dict) -> str`, `decode_token(token: str) -> dict`
- Produces: `get_current_user(token: str, db: AsyncSession) -> User`

- [ ] **Step 1: Write src/auth/jwt.py**

```python
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from src.config import settings

ALGORITHM = "HS256"

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
```

- [ ] **Step 2: Write src/auth/deps.py**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError
from src.database import get_async_session
from src.models.user import User
from src.auth.jwt import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_session),
) -> User:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user
```

- [ ] **Step 3: Commit**

```bash
git add src/auth/
git commit -m "feat: JWT token creation, decoding, and current-user dependency"
```

---

### Task 7: Auth routes (register, token, Google OAuth)

**Files:**
- Create: `src/auth/routes.py`

**Interfaces:**
- Produces: FastAPI APIRouter with routes:
  - `POST /api/v1/auth/register` — email + password registration
  - `POST /api/v1/auth/token` — token endpoint (password / google_oauth grant types)
  - `POST /api/v1/auth/refresh` — refresh access token

- [ ] **Step 1: Write src/auth/routes.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from httpx import AsyncClient
from src.database import get_async_session
from src.models.user import User
from src.schemas.auth import UserCreate, UserResponse, TokenResponse, TokenRequest, RefreshRequest
from src.auth.jwt import create_access_token, create_refresh_token, decode_token
from src.auth.deps import get_current_user
from src.config import settings
from jose import JWTError

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: AsyncSession = Depends(get_async_session)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=body.email,
        hashed_password=pwd_context.hash(body.password),
        role="customer",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/token", response_model=TokenResponse)
async def token(body: TokenRequest, db: AsyncSession = Depends(get_async_session)):
    if body.grant_type == "password":
        if not body.email or not body.password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email and password required")
        result = await db.execute(select(User).where(User.email == body.email))
        user = result.scalar_one_or_none()
        if not user or not user.hashed_password or not pwd_context.verify(body.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    elif body.grant_type == "google_oauth":
        if not body.google_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google_code required")
        async with AsyncClient() as client:
            token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                "code": body.google_code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": "postmessage",
                "grant_type": "authorization_code",
            })
            if token_resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google code")
            google_tokens = token_resp.json()
            userinfo_resp = await client.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={
                "Authorization": f"Bearer {google_tokens['access_token']}"
            })
            userinfo = userinfo_resp.json()
            email = userinfo["email"]
            google_id = userinfo["id"]

        result = await db.execute(select(User).where((User.email == email) | (User.google_id == google_id)))
        user = result.scalar_one_or_none()
        if not user:
            user = User(email=email, google_id=google_id, role="customer")
            db.add(user)
            await db.commit()
            await db.refresh(user)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant_type")

    sub = str(user.id)
    access = create_access_token({"sub": sub})
    refresh = create_refresh_token({"sub": sub})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        sub = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    access = create_access_token({"sub": sub})
    refresh_new = create_refresh_token({"sub": sub})
    return TokenResponse(access_token=access, refresh_token=refresh_new)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
```

- [ ] **Step 2: Commit**

```bash
git add src/auth/routes.py
git commit -m "feat: auth routes — register, token (password/google_oauth), refresh"
```

---

### Task 8: FastAPI app entry point and product CRUD

**Files:**
- Create: `src/main.py`
- Create: `src/api/__init__.py`
- Create: `src/api/products.py`

**Interfaces:**
- Produces: FastAPI app at `src.main:app`
- Produces: `POST /api/v1/products`, `GET /api/v1/products`, `GET /api/v1/products/{id}`

- [ ] **Step 1: Write src/api/products.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from src.database import get_async_session
from src.models.user import User
from src.models.product import Product
from src.schemas.product import ProductCreate, ProductResponse
from src.auth.deps import get_current_user

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    product = Product(
        name=body.name,
        top_note=body.top_note,
        middle_note=body.middle_note,
        base_note=body.base_note,
        scenarios=body.scenarios,
        main_image_url=body.main_image_url,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    result = await db.execute(select(Product).offset(offset).limit(page_size).order_by(Product.created_at.desc()))
    items = result.scalars().all()
    total_result = await db.execute(select(func.count(Product.id)))
    total = total_result.scalar()
    return {"items": items, "total": total}


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product
```

- [ ] **Step 2: Write src/main.py**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.auth.routes import router as auth_router
from src.api.products import router as products_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Perfume Video API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
```

- [ ] **Step 3: Test the app starts**

```bash
cd /home/tutar/work/video-infra/product-meadia
python -c "from src.main import app; print('App loaded OK, routes:', [r.path for r in app.routes])"
```

- [ ] **Step 4: Commit**

```bash
git add src/main.py src/api/
git commit -m "feat: FastAPI app entry point and product CRUD API"
```

---

### Task 9: Task API with WebSocket progress

**Files:**
- Create: `src/api/tasks.py`
- Create: `src/ws/__init__.py`
- Create: `src/ws/progress.py`

**Interfaces:**
- Produces: `POST /api/v1/tasks`, `GET /api/v1/tasks`, `GET /api/v1/tasks/{id}`, `PUT /api/v1/tasks/{id}/script`, `GET /api/v1/tasks/{id}/images`, `PUT /api/v1/tasks/{id}/images/{img_id}`, `POST /api/v1/tasks/{id}/images/{img_id}/regenerate`, `GET /api/v1/tasks/{id}/video`, `POST /api/v1/tasks/viral/analyze`
- Produces: `WS /ws/tasks/{task_id}` — pushes JSON progress events

- [ ] **Step 1: Write src/ws/progress.py**

```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict

class ProgressManager:
    def __init__(self):
        self._connections: Dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(task_id, []).append(ws)

    def disconnect(self, task_id: str, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        if ws in conns:
            conns.remove(ws)

    async def send_progress(self, task_id: str, data: dict):
        for ws in self._connections.get(task_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass

progress_manager = ProgressManager()
```

- [ ] **Step 2: Write src/api/tasks.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status, Query, WebSocket, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID
from src.database import get_async_session
from src.models.user import User
from src.models.product import Product
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis
from src.schemas.task import (
    TaskCreate, TaskResponse, ScriptResponse, ScriptUpdate,
    ImageResponse, ImageReview, ViralAnalysisResponse,
)
from src.auth.deps import get_current_user
from src.ws.progress import progress_manager

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    product_result = await db.execute(select(Product).where(Product.id == body.product_id))
    if not product_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if body.type == "viral" and not body.viral_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="viral_url required for viral type")

    task = VideoTask(
        product_id=body.product_id,
        type=body.type,
        image_count=body.image_count,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    # Celery dispatch will be wired in Task 17
    return task


@router.get("")
async def list_tasks(
    product_id: UUID | None = None,
    type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    query = select(VideoTask).options(selectinload(VideoTask.script), selectinload(VideoTask.images))
    if product_id:
        query = query.where(VideoTask.product_id == product_id)
    if type:
        query = query.where(VideoTask.type == type)
    if status:
        query = query.where(VideoTask.status == status)

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size).order_by(VideoTask.created_at.desc()))
    items = result.scalars().all()
    total_result = await db.execute(select(func.count(VideoTask.id)))
    return {"items": items, "total": total_result.scalar()}


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/script", response_model=ScriptResponse)
async def get_script(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    result = await db.execute(select(Script).where(Script.task_id == task_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@router.put("/{task_id}/script", response_model=ScriptResponse)
async def update_script(
    task_id: UUID, body: ScriptUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Script).where(Script.task_id == task_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    if body.edited_content is not None:
        script.edited_content = body.edited_content
    if body.image_prompts is not None:
        script.image_prompts = body.image_prompts
    if body.approved:
        script.status = "approved"
        task_result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
        task = task_result.scalar_one()
        task.status = "imaging"
        # Agent resume will be wired in Task 17
    await db.commit()
    await db.refresh(script)
    return script


@router.get("/{task_id}/images", response_model=list[ImageResponse])
async def list_images(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    result = await db.execute(select(GeneratedImage).where(GeneratedImage.task_id == task_id).order_by(GeneratedImage.sort_order))
    return result.scalars().all()


@router.put("/{task_id}/images/{image_id}")
async def review_image(
    task_id: UUID, image_id: UUID, body: ImageReview,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.task_id == task_id))
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    img.status = "approved" if body.action == "approve" else "rejected"
    await db.commit()

    if body.action == "approve":
        # Check if ALL images for this task are approved
        task_result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
        task = task_result.scalar_one()
        all_approved = await db.execute(
            select(func.count(GeneratedImage.id)).where(
                GeneratedImage.task_id == task_id,
                GeneratedImage.status != "approved",
            )
        )
        if all_approved.scalar() == 0:
            task.status = "video_gen"
            await db.commit()
    return {"status": "ok"}


@router.post("/{task_id}/images/{image_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_image(
    task_id: UUID, image_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.task_id == task_id))
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    img.status = "pending_review"
    img.image_url = None
    await db.commit()
    return {"status": "queued"}


@router.get("/{task_id}/video")
async def download_video(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task or task.status != "done":
        raise HTTPException(status_code=404, detail="Video not ready")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=task.result_video_url)


@router.post("/viral/analyze", response_model=ViralAnalysisResponse, status_code=status.HTTP_200_OK)
async def analyze_viral_video(
    product_id: UUID,
    video_url: str,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    from src.tools.transcription import transcribe_audio
    from src.tools.llm_tools import analyze_video_structure
    transcription = await transcribe_audio(video_url)
    structure = await analyze_video_structure(transcription)
    return ViralAnalysisResponse(
        id=UUID("00000000-0000-0000-0000-000000000000"),
        task_id=None,
        source_url=video_url,
        original_script=transcription,
        script_structure=structure.get("script_structure"),
        shot_list=structure.get("shot_list", []),
        style_params=structure.get("style_params"),
    )


@router.websocket("/ws/tasks/{task_id}")
async def task_progress_ws(websocket: WebSocket, task_id: str):
    await progress_manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        progress_manager.disconnect(task_id, websocket)
```

- [ ] **Step 3: Wire task routes and WebSocket into main.py**

Update `src/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from src.auth.routes import router as auth_router
from src.api.products import router as products_router
from src.api.tasks import router as tasks_router
from src.ws.progress import progress_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Perfume Video API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")

@app.websocket("/ws/tasks/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str):
    await progress_manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        progress_manager.disconnect(task_id, websocket)
```

- [ ] **Step 4: Commit**

```bash
git add src/api/tasks.py src/ws/ src/main.py
git commit -m "feat: task API endpoints and WebSocket progress"
```

---

### Task 10: Shared tool — Image generation via Agnes/LiteLLM

**Files:**
- Create: `src/tools/__init__.py`
- Create: `src/tools/image_gen.py`

**Interfaces:**
- Produces: `async generate_image(prompt: str, ref_image_url: str | None = None) -> str` — returns image URL

- [ ] **Step 1: Write src/tools/image_gen.py**

```python
import time
from openai import AsyncOpenAI
from src.config import settings
from langfuse.decorators import observe

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)

@observe(name="generate_image")
async def generate_image(prompt: str, ref_image_url: str | None = None) -> str:
    extra_body = {}
    if ref_image_url:
        extra_body["image"] = [ref_image_url]

    for attempt in range(3):
        try:
            response = await client.images.generate(
                model="agnes-image-2.1-flash",
                prompt=prompt,
                size="1024x1024",
                extra_body=extra_body if extra_body else None,
            )
            return response.data[0].url
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("generate_image failed after 3 retries")
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/
git commit -m "feat: shared tool — Agnes Image generation via LiteLLM with retry"
```

---

### Task 11: Shared tool — Video generation via Agnes API

**Files:**
- Create: `src/tools/video_gen.py`

**Interfaces:**
- Produces: `async generate_video(prompt: str, image_urls: list[str] | None = None) -> str` — returns video URL

- [ ] **Step 1: Write src/tools/video_gen.py**

```python
import time
import httpx
from src.config import settings
from langfuse.decorators import observe

HEADERS = {"Authorization": f"Bearer {settings.agnes_video_api_key}"}

@observe(name="generate_video")
async def generate_video(prompt: str, image_urls: list[str] | None = None) -> str:
    payload = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": 1152,
        "height": 768,
        "num_frames": 121,
        "frame_rate": 24,
    }
    if image_urls:
        payload["extra_body"] = {"image": image_urls, "mode": "keyframes"}

    async with httpx.AsyncClient(timeout=360) as client:
        resp = await client.post(f"{settings.agnes_video_base_url}/v1/videos", headers=HEADERS, json=payload)
        resp.raise_for_status()
        video_id = resp.json()["video_id"]

        while True:
            await time.sleep(10)
            result = await client.get(f"{settings.agnes_video_base_url}/agnesapi", params={"video_id": video_id}, headers=HEADERS)
            result.raise_for_status()
            data = result.json()
            if data["status"] == "completed":
                return data["url"]
            if data["status"] == "failed":
                raise RuntimeError(f"Video generation failed: {data.get('error')}")
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/video_gen.py
git commit -m "feat: shared tool — Agnes Video generation with polling"
```

---

### Task 12: Shared tool — TTS (VoxCPM2)

**Files:**
- Create: `src/tools/tts.py`

**Interfaces:**
- Produces: `async generate_tts(text: str) -> dict` — returns `{"audio_url": str, "words": [{"word": str, "start": float, "end": float}]}`

- [ ] **Step 1: Write src/tools/tts.py**

```python
import httpx
from src.config import settings
from langfuse.decorators import observe

@observe(name="generate_tts")
async def generate_tts(text: str) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.voxcpm2_base_url}/v1/tts",
            json={"text": text, "return_timestamps": True},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "audio_url": data["audio_url"],
            "words": data.get("words", []),
        }
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/tts.py
git commit -m "feat: shared tool — VoxCPM2 TTS with word timestamps"
```

---

### Task 13: Shared tools — LipSync, HyperFrames render, audio transcription, LLM analysis

**Files:**
- Create: `src/tools/lipsync.py`
- Create: `src/tools/render.py`
- Create: `src/tools/transcription.py`
- Create: `src/tools/llm_tools.py`

**Interfaces:**
- Produces: `async run_lipsync(image_url: str, audio_url: str) -> str` — returns video URL
- Produces: `async render_hyperframes(html_content: str, asset_dir: str) -> str` — returns MP4 path
- Produces: `async transcribe_audio(video_url: str) -> str` — returns transcript text
- Produces: `async analyze_video_structure(transcript: str) -> dict`

- [ ] **Step 1: Write src/tools/lipsync.py**

```python
import httpx
from src.config import settings
from langfuse.decorators import observe

@observe(name="lipsync")
async def run_lipsync(image_url: str, audio_url: str) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{settings.latentsync_base_url}/v1/lipsync",
            json={"image_url": image_url, "audio_url": audio_url},
        )
        resp.raise_for_status()
        return resp.json()["video_url"]
```

- [ ] **Step 2: Write src/tools/render.py**

```python
import subprocess
import tempfile
import os
from langfuse.decorators import observe

@observe(name="render_hyperframes")
async def render_hyperframes(html_content: str, asset_dir: str) -> str:
    workdir = tempfile.mkdtemp(prefix="hyperframes_")
    html_path = os.path.join(workdir, "index.html")
    output_path = os.path.join(workdir, "output.mp4")

    with open(html_path, "w") as f:
        f.write(html_content)

    result = subprocess.run(
        ["npx", "hyperframes", "render", html_path, "--output", output_path],
        capture_output=True, text=True, timeout=300, cwd=workdir,
    )
    if result.returncode != 0:
        raise RuntimeError(f"HyperFrames render failed: {result.stderr}")
    return output_path
```

- [ ] **Step 3: Write src/tools/transcription.py**

```python
import httpx
from src.config import settings
from langfuse.decorators import observe

@observe(name="transcribe_audio")
async def transcribe_audio(video_url: str) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{settings.funasr_base_url}/audio/transcriptions",
            data={"file": video_url, "model": "sensevoice"},
        )
        resp.raise_for_status()
        return resp.json()["text"]
```

- [ ] **Step 4: Write src/tools/llm_tools.py**

```python
from openai import AsyncOpenAI
from src.config import settings
from langfuse.decorators import observe

client = AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)

@observe(name="llm_chat")
async def llm_chat(model: str, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content


@observe(name="analyze_video_structure")
async def analyze_video_structure(transcript: str) -> dict:
    import json
    system = """You are a video analysis expert. Analyze the given video transcript and extract:
1. Script structure: hook, pain_point, solution, product_showcase, cta — one paragraph each
2. Shot list: array of {index, description, duration_seconds, shot_type}
3. Style params: {transition, bgm_style, subtitle_position, subtitle_style}

Return ONLY valid JSON, no markdown wrapping."""
    text = await llm_chat("researcher", system, transcript, temperature=0.2)
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)
```

- [ ] **Step 5: Commit**

```bash
git add src/tools/lipsync.py src/tools/render.py src/tools/transcription.py src/tools/llm_tools.py
git commit -m "feat: shared tools — lipsync, HyperFrames render, transcription, LLM analysis"
```

---

### Task 14: LangGraph shared state and agent state models

**Files:**
- Create: `src/agents/__init__.py`
- Create: `src/agents/state.py`

**Interfaces:**
- Produces: `VideoAgentState` TypedDict, consumed by all agent graphs

- [ ] **Step 1: Write src/agents/state.py**

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class VideoAgentState(TypedDict):
    task_id: str
    product_id: str
    product_info: dict  # {name, top_note, middle_note, base_note, scenarios, main_image_url}
    task_type: str
    image_count: int

    # Script generation
    script_content: str
    edited_script_content: str
    image_prompts: list[str]
    voiceover_text: str

    # Image generation
    generated_images: list[dict]  # [{sort_order, image_url, status}]

    # Video generation
    video_clips: list[str]  # video URLs from Agnes

    # TTS
    tts_audio_url: str
    tts_words: list[dict]  # [{word, start, end}]

    # LipSync (personify only)
    lipsync_video_url: str
    character_image_url: str

    # Viral analysis
    viral_url: str
    viral_analysis: dict  # {script_structure, shot_list, style_params}

    # HyperFrames
    hyperframes_html: str
    final_video_path: str

    # Human-in-the-loop
    review_approved: bool
    messages: Annotated[list[BaseMessage], add_messages]
```

- [ ] **Step 2: Commit**

```bash
git add src/agents/
git commit -m "feat: LangGraph shared VideoAgentState definition"
```

---

### Task 15: Promo agent graph (product promotional video)

**Files:**
- Create: `src/agents/promo_graph.py`

**Interfaces:**
- Consumes: `VideoAgentState`, shared tools
- Produces: compiled LangGraph `promo_graph`

- [ ] **Step 1: Write src/agents/promo_graph.py**

```python
import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.agents.state import VideoAgentState
from src.tools.image_gen import generate_image
from src.tools.video_gen import generate_video
from src.tools.tts import generate_tts
from src.tools.render import render_hyperframes
from src.tools.llm_tools import llm_chat

SCRIPT_SYSTEM = """You are a perfume video scriptwriter. Given a perfume product, write:
1. A video script (narration text) with structure: opening → middle notes → base notes → scenarios → CTA
2. Voiceover text (same as script, cleaned for TTS)
3. {image_count} image generation prompts. Each prompt describes a cinematic perfume-ad visual scene.
   Match the script's narrative flow. Style: luxury, cinematic lighting, product-focused.

Return ONLY JSON: {"script": "...", "voiceover": "...", "image_prompts": ["prompt1", ...]}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .clip {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .subtitle {{ position:absolute; bottom:10%; width:100%; text-align:center; color:#fff; font-size:32px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="promo-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio src="{audio_url}" data-start="0"></audio>
  {video_elements}
  {subtitle_elements}
</div>
</body></html>"""


def build_promo_graph() -> StateGraph:
    graph = StateGraph(VideoAgentState)

    async def generate_script(state: VideoAgentState) -> dict:
        info = state["product_info"]
        prompt = f"Product: {info['name']}\nTop notes: {info.get('top_note','')}\nMiddle notes: {info.get('middle_note','')}\nBase notes: {info.get('base_note','')}\nScenarios: {info.get('scenarios',[])}"
        system = SCRIPT_SYSTEM.format(image_count=state["image_count"])
        result = await llm_chat("scriptwriter", system, prompt, temperature=0.7)
        data = json.loads(result)
        return {
            "script_content": data["script"],
            "voiceover_text": data["voiceover"],
            "image_prompts": data["image_prompts"][: state["image_count"]],
        }

    async def wait_script_review(state: VideoAgentState) -> dict:
        # Human-in-the-loop: graph interrupts here, user approves via PUT /tasks/{id}/script
        return {}

    async def generate_images(state: VideoAgentState) -> dict:
        images = []
        prompts = state.get("edited_script_content") and state.get("image_prompts") or state["image_prompts"]
        for i, p in enumerate(prompts):
            url = await generate_image(p)
            images.append({"sort_order": i, "image_url": url, "status": "pending_review"})
        return {"generated_images": images}

    async def wait_image_review(state: VideoAgentState) -> dict:
        # Human-in-the-loop: graph interrupts, user reviews each image
        return {}

    async def generate_video_clips(state: VideoAgentState) -> dict:
        approved_urls = [img["image_url"] for img in state["generated_images"] if img["status"] == "approved"]
        clips = []
        for url in approved_urls:
            clip_url = await generate_video(
                prompt="Cinematic camera movement, smooth panning, luxury perfume advertisement style",
                image_urls=[url],
            )
            clips.append(clip_url)
        return {"video_clips": clips}

    async def generate_voiceover(state: VideoAgentState) -> dict:
        script = state.get("edited_script_content") or state["script_content"]
        result = await generate_tts(script)
        return {"tts_audio_url": result["audio_url"], "tts_words": result["words"]}

    async def composite_video(state: VideoAgentState) -> dict:
        total_duration = len(state["video_clips"]) * 5
        video_elements = ""
        for i, url in enumerate(state["video_clips"]):
            video_elements += f'<video class="clip" src="{url}" data-start="{i * 5}" data-duration="5" muted playsinline></video>\n'

        subtitle_elements = ""
        for w in state.get("tts_words", []):
            subtitle_elements += f'<div class="subtitle" data-start="{w["start"]}" data-duration="{w["end"] - w["start"]}">{w["word"]}</div>\n'

        html = HTML_TEMPLATE.format(
            total_duration=total_duration,
            audio_url=state["tts_audio_url"],
            video_elements=video_elements,
            subtitle_elements=subtitle_elements,
        )
        path = await render_hyperframes(html, "/tmp")
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node("generate_script", generate_script)
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_images", generate_images)
    graph.add_node("wait_image_review", wait_image_review)
    graph.add_node("generate_video_clips", generate_video_clips)
    graph.add_node("generate_voiceover", generate_voiceover)
    graph.add_node("composite_video", composite_video)

    graph.set_entry_point("generate_script")
    graph.add_edge("generate_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_images")
    graph.add_edge("generate_images", "wait_image_review")
    graph.add_edge("wait_image_review", "generate_video_clips")
    graph.add_edge("generate_video_clips", "generate_voiceover")
    graph.add_edge("generate_voiceover", "composite_video")
    graph.add_edge("composite_video", END)

    return graph.compile(checkpointer=MemorySaver(), interrupt_before=["wait_script_review", "wait_image_review"])


promo_graph = build_promo_graph()
```

- [ ] **Step 2: Commit**

```bash
git add src/agents/promo_graph.py
git commit -m "feat: promo agent graph — script→images→video→tts→HyperFrames composite"
```

---

### Task 16: Viral and Personify agent graphs

**Files:**
- Create: `src/agents/viral_graph.py`
- Create: `src/agents/personify_graph.py`

**Interfaces:**
- Produces: compiled `viral_graph`, `personify_graph`

- [ ] **Step 1: Write src/agents/viral_graph.py**

```python
import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.agents.state import VideoAgentState
from src.tools.image_gen import generate_image
from src.tools.video_gen import generate_video
from src.tools.tts import generate_tts
from src.tools.render import render_hyperframes
from src.tools.transcription import transcribe_audio
from src.tools.llm_tools import llm_chat, analyze_video_structure

PROMPT = """Rewrite the following video script for a perfume product.
Replace the original product mentions with this product: {product_name}.
Keep the same structure, pacing, and emotional tone.
Original script: {original_script}
Product info: {product_info}

Return ONLY JSON: {{"script": "...", "voiceover": "...", "image_prompts": ["..."]}}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .clip {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .subtitle {{ position:absolute; bottom:10%; width:100%; text-align:center; color:#fff; font-size:32px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="viral-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio src="{audio_url}" data-start="0"></audio>
  {video_elements}
  {subtitle_elements}
</div>
</body></html>"""


def build_viral_graph() -> StateGraph:
    graph = StateGraph(VideoAgentState)

    async def analyze_source(state: VideoAgentState) -> dict:
        transcript = await transcribe_audio(state["viral_url"])
        analysis = await analyze_video_structure(transcript)
        return {"viral_analysis": analysis}

    async def wait_viral_confirm(state: VideoAgentState) -> dict:
        return {}

    async def generate_rewritten_script(state: VideoAgentState) -> dict:
        info = state["product_info"]
        user_prompt = PROMPT.format(
            product_name=info["name"],
            original_script=state["viral_analysis"].get("original_script", ""),
            product_info=json.dumps(info),
        )
        result = await llm_chat("scriptwriter", "You are a video script adapter.", user_prompt)
        data = json.loads(result)
        return {"script_content": data["script"], "voiceover_text": data["voiceover"], "image_prompts": data["image_prompts"]}

    async def wait_script_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_images(state: VideoAgentState) -> dict:
        images = []
        for i, p in enumerate(state["image_prompts"]):
            url = await generate_image(p)
            images.append({"sort_order": i, "image_url": url, "status": "pending_review"})
        return {"generated_images": images}

    async def wait_image_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_clips_and_voiceover(state: VideoAgentState) -> dict:
        clips = []
        for img in state["generated_images"]:
            if img["status"] == "approved":
                clips.append(await generate_video(prompt="Smooth cinematic movement, luxury product showcase", image_urls=[img["image_url"]]))
        tts_result = await generate_tts(state.get("edited_script_content") or state["script_content"])
        return {"video_clips": clips, "tts_audio_url": tts_result["audio_url"], "tts_words": tts_result["words"]}

    async def composite(state: VideoAgentState) -> dict:
        total_duration = len(state["video_clips"]) * 5
        video_elements = ""
        for i, url in enumerate(state["video_clips"]):
            video_elements += f'<video class="clip" src="{url}" data-start="{i * 5}" data-duration="5" muted playsinline></video>\n'
        subtitle_elements = ""
        for w in state.get("tts_words", []):
            subtitle_elements += f'<div class="subtitle" data-start="{w["start"]}" data-duration="{w["end"] - w["start"]}">{w["word"]}</div>\n'
        html = HTML_TEMPLATE.format(total_duration=total_duration, audio_url=state["tts_audio_url"], video_elements=video_elements, subtitle_elements=subtitle_elements)
        path = await render_hyperframes(html, "/tmp")
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node("analyze_source", analyze_source)
    graph.add_node("wait_viral_confirm", wait_viral_confirm)
    graph.add_node("generate_rewritten_script", generate_rewritten_script)
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_images", generate_images)
    graph.add_node("wait_image_review", wait_image_review)
    graph.add_node("generate_clips_and_voiceover", generate_clips_and_voiceover)
    graph.add_node("composite", composite)

    graph.set_entry_point("analyze_source")
    graph.add_edge("analyze_source", "wait_viral_confirm")
    graph.add_edge("wait_viral_confirm", "generate_rewritten_script")
    graph.add_edge("generate_rewritten_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_images")
    graph.add_edge("generate_images", "wait_image_review")
    graph.add_edge("wait_image_review", "generate_clips_and_voiceover")
    graph.add_edge("generate_clips_and_voiceover", "composite")
    graph.add_edge("composite", END)

    return graph.compile(checkpointer=MemorySaver(), interrupt_before=["wait_viral_confirm", "wait_script_review", "wait_image_review"])


viral_graph = build_viral_graph()
```

- [ ] **Step 2: Write src/agents/personify_graph.py**

```python
import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.agents.state import VideoAgentState
from src.tools.image_gen import generate_image
from src.tools.tts import generate_tts
from src.tools.lipsync import run_lipsync
from src.tools.render import render_hyperframes
from src.tools.llm_tools import llm_chat

CHARACTER_PROMPT = """Design a personified character for this perfume:
Product: {product_name}
Top notes: {top_note}
Middle notes: {middle_note}
Base notes: {base_note}
Scenarios: {scenarios}

Describe the character as an image generation prompt: age, gender, clothing style, expression, setting.
The character should visually embody the perfume's personality. Output ONLY the image prompt, no commentary."""

SCRIPT_PROMPT = """You are this perfume speaking in first person. Introduce yourself:
"I am {product_name}. My top notes are {top_note}, middle notes {middle_note}, base notes {base_note}.
I'm perfect for {scenarios}..."

Write a 30-second first-person monologue. Return ONLY JSON: {{"script": "...", "voiceover": "..."}}"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; background:#000; font-family:sans-serif; }}
  .main {{ position:absolute; width:100%; height:100%; object-fit:cover; }}
  .overlay {{ position:absolute; top:5%; left:5%; color:#fff; font-size:28px; text-shadow:0 2px 8px rgba(0,0,0,0.7); }}
  .subtitle {{ position:absolute; bottom:12%; width:100%; text-align:center; color:#fff; font-size:30px; text-shadow:0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
<div data-composition-id="personify-video" data-start="0" data-duration="{total_duration}" data-width="1152" data-height="768">
  <audio src="{audio_url}" data-start="0"></audio>
  <video class="main" src="{lipsync_url}" data-start="0" data-duration="{total_duration}" muted playsinline></video>
  <div class="overlay" data-start="0" data-duration="{total_duration}">{product_name}</div>
  {subtitle_elements}
</div>
</body></html>"""


def build_personify_graph() -> StateGraph:
    graph = StateGraph(VideoAgentState)

    async def generate_character(state: VideoAgentState) -> dict:
        info = state["product_info"]
        prompt = CHARACTER_PROMPT.format(
            product_name=info["name"], top_note=info.get("top_note", ""),
            middle_note=info.get("middle_note", ""), base_note=info.get("base_note", ""),
            scenarios=", ".join(info.get("scenarios", [])),
        )
        result = await llm_chat("scriptwriter", "You are a character designer.", prompt)
        image_url = await generate_image(result)
        return {"character_image_url": image_url}

    async def wait_character_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_script(state: VideoAgentState) -> dict:
        info = state["product_info"]
        prompt = SCRIPT_PROMPT.format(
            product_name=info["name"], top_note=info.get("top_note", ""),
            middle_note=info.get("middle_note", ""), base_note=info.get("base_note", ""),
            scenarios=", ".join(info.get("scenarios", [])),
        )
        result = await llm_chat("scriptwriter", "You are a perfume speaking in first person.", prompt)
        data = json.loads(result)
        return {"script_content": data["script"], "voiceover_text": data["voiceover"]}

    async def wait_script_review(state: VideoAgentState) -> dict:
        return {}

    async def generate_tts_and_lipsync(state: VideoAgentState) -> dict:
        tts_result = await generate_tts(state.get("edited_script_content") or state["script_content"])
        lipsync_url = await run_lipsync(state["character_image_url"], tts_result["audio_url"])
        return {"tts_audio_url": tts_result["audio_url"], "tts_words": tts_result["words"], "lipsync_video_url": lipsync_url}

    async def composite(state: VideoAgentState) -> dict:
        total_duration = sum(w["end"] for w in state["tts_words"]) if state["tts_words"] else 30
        subtitle_elements = ""
        for w in state.get("tts_words", []):
            subtitle_elements += f'<div class="subtitle" data-start="{w["start"]}" data-duration="{w["end"] - w["start"]}">{w["word"]}</div>\n'
        html = HTML_TEMPLATE.format(
            total_duration=total_duration,
            audio_url=state["tts_audio_url"],
            lipsync_url=state["lipsync_video_url"],
            product_name=state["product_info"]["name"],
            subtitle_elements=subtitle_elements,
        )
        path = await render_hyperframes(html, "/tmp")
        return {"hyperframes_html": html, "final_video_path": path}

    graph.add_node("generate_character", generate_character)
    graph.add_node("wait_character_review", wait_character_review)
    graph.add_node("generate_script", generate_script)
    graph.add_node("wait_script_review", wait_script_review)
    graph.add_node("generate_tts_and_lipsync", generate_tts_and_lipsync)
    graph.add_node("composite", composite)

    graph.set_entry_point("generate_character")
    graph.add_edge("generate_character", "wait_character_review")
    graph.add_edge("wait_character_review", "generate_script")
    graph.add_edge("generate_script", "wait_script_review")
    graph.add_edge("wait_script_review", "generate_tts_and_lipsync")
    graph.add_edge("generate_tts_and_lipsync", "composite")
    graph.add_edge("composite", END)

    return graph.compile(checkpointer=MemorySaver(), interrupt_before=["wait_character_review", "wait_script_review"])


personify_graph = build_personify_graph()
```

- [ ] **Step 3: Commit**

```bash
git add src/agents/viral_graph.py src/agents/personify_graph.py
git commit -m "feat: viral and personify agent graphs with human-in-the-loop checkpoints"
```

---

### Task 17: Celery worker and task dispatch wiring

**Files:**
- Create: `src/tasks/__init__.py`
- Create: `src/tasks/celery_app.py`
- Create: `src/tasks/video_tasks.py`

**Interfaces:**
- Produces: Celery app, `run_video_task` celery task that loads product info, creates agent state, and executes the correct graph

- [ ] **Step 1: Write src/tasks/celery_app.py**

```python
from celery import Celery
from src.config import settings

celery_app = Celery("perfume_video", broker=settings.celery_broker_url, backend=settings.celery_broker_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
```

- [ ] **Step 2: Write src/tasks/video_tasks.py**

```python
import asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from src.tasks.celery_app import celery_app
from src.models.product import Product
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis
from src.agents.state import VideoAgentState
from src.ws.progress import progress_manager

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

GRAPHS = {}


def _get_graph(task_type: str):
    if task_type not in GRAPHS:
        if task_type == "promo":
            from src.agents.promo_graph import promo_graph
            GRAPHS["promo"] = promo_graph
        elif task_type == "viral":
            from src.agents.viral_graph import viral_graph
            GRAPHS["viral"] = viral_graph
        elif task_type == "personify":
            from src.agents.personify_graph import personify_graph
            GRAPHS["personify"] = personify_graph
    return GRAPHS[task_type]


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_video_task(self, task_id: str):
    return asyncio.get_event_loop().run_until_complete(_async_run(task_id, self.request.id))


async def _async_run(task_id: str, celery_task_id: str):
    async with SessionLocal() as db:
        result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
        task = result.scalar_one()
        product_result = await db.execute(select(Product).where(Product.id == task.product_id))
        product = product_result.scalar_one()

        initial_state: VideoAgentState = {
            "task_id": str(task.id),
            "product_id": str(product.id),
            "product_info": {
                "name": product.name, "top_note": product.top_note,
                "middle_note": product.middle_note, "base_note": product.base_note,
                "scenarios": product.scenarios, "main_image_url": product.main_image_url,
            },
            "task_type": task.type,
            "image_count": task.image_count,
            "viral_url": "",
            "script_content": "", "edited_script_content": "", "image_prompts": [],
            "voiceover_text": "", "generated_images": [], "video_clips": [],
            "tts_audio_url": "", "tts_words": [], "lipsync_video_url": "",
            "character_image_url": "", "viral_analysis": {},
            "hyperframes_html": "", "final_video_path": "",
            "review_approved": False, "messages": [],
        }
        if task.type == "viral":
            v_result = await db.execute(select(ViralAnalysis).where(ViralAnalysis.task_id == task.id))
            va = v_result.scalar_one_or_none()
            if va:
                initial_state["viral_url"] = va.source_url

        task.status = "scripting"
        task.celery_task_id = celery_task_id
        await db.commit()

    graph = _get_graph(task.type)
    config = {"configurable": {"thread_id": task_id}}
    final_state = None

    async for event in graph.astream(initial_state, config):
        await progress_manager.send_progress(task_id, {"event": str(event)})
        for node_name, node_output in event.items():
            if node_name.startswith("wait_"):
                async with SessionLocal() as db:
                    t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                    t.status = node_name
                    await db.commit()
            final_state = node_output

    if final_state and final_state.get("final_video_path"):
        async with SessionLocal() as db:
            t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
            t.status = "done"
            t.result_video_url = final_state["final_video_path"]
            await db.commit()
        await progress_manager.send_progress(task_id, {"status": "done", "video_url": final_state["final_video_path"]})
```

- [ ] **Step 3: Update src/api/tasks.py to dispatch Celery task on creation**

In `src/api/tasks.py`, add to the `create_task` function after `await db.commit()` and before `return task`:

```python
    from src.tasks.video_tasks import run_video_task
    celery_result = run_video_task.delay(str(task.id))
    task.celery_task_id = celery_result.id
    await db.commit()
    await db.refresh(task)
```

- [ ] **Step 4: Commit**

```bash
git add src/tasks/ src/api/tasks.py
git commit -m "feat: Celery worker with task dispatch wiring to agent graphs"
```

---

### Task 18: Write conftest and first test

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_tools/test_image_gen.py`

- [ ] **Step 1: Write tests/conftest.py**

```python
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from src.models.base import Base

TEST_DB = settings.database_url.replace("perfume_video", "perfume_video_test")

@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

- [ ] **Step 2: Write tests/test_tools/test_image_gen.py**

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.tools.image_gen import generate_image

@pytest.mark.asyncio
async def test_generate_image_returns_url():
    mock_response = AsyncMock()
    mock_response.data = [AsyncMock(url="https://rustfs:8001/images/test.png")]

    with patch("src.tools.image_gen.client.images.generate", return_value=mock_response) as mock_gen:
        url = await generate_image("A perfume bottle on a marble table")
        assert url == "https://rustfs:8001/images/test.png"
        mock_gen.assert_called_once_with(
            model="agnes-image-2.1-flash",
            prompt="A perfume bottle on a marble table",
            size="1024x1024",
            extra_body=None,
        )

@pytest.mark.asyncio
async def test_generate_image_with_ref_image():
    mock_response = AsyncMock()
    mock_response.data = [AsyncMock(url="https://rustfs:8001/images/test2.png")]

    with patch("src.tools.image_gen.client.images.generate", return_value=mock_response) as mock_gen:
        url = await generate_image("Variant of the scene", ref_image_url="https://example.com/ref.png")
        assert url == "https://rustfs:8001/images/test2.png"
        assert mock_gen.call_args[1]["extra_body"] == {"image": ["https://example.com/ref.png"]}

@pytest.mark.asyncio
async def test_generate_image_retries_then_raises():
    with patch("src.tools.image_gen.client.images.generate", side_effect=Exception("API down")) as mock_gen:
        with pytest.raises(Exception):
            await generate_image("test")
        assert mock_gen.call_count == 3
```

- [ ] **Step 3: Run tests**

```bash
cd /home/tutar/work/video-infra/product-meadia
python -m pytest tests/test_tools/test_image_gen.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: image generation tool unit tests with mock"
```

---

### Task 19: Docker Compose for the application

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write docker-compose.yml**

```yaml
version: "3.8"

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - redis
    volumes:
      - ./src:/app/src
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    depends_on:
      - redis
    volumes:
      - ./src:/app/src
      - /tmp/hyperframes:/tmp/hyperframes
    command: celery -A src.tasks.celery_app worker --loglevel=info --concurrency=1

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

Note: PostgreSQL, LiteLLM, Redis are provided by agent-infra. This compose only adds the app's own services. If agent-infra Redis is preferred, remove the `redis` service and point `CELERY_BROKER_URL` to the agent-infra Redis.

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: docker-compose for API and Celery worker"
```

---

### Task 20: Frontend scaffold (React + Vite)

**Files:**
- Create: `frontend/` — full Vite + React + TypeScript scaffold

- [ ] **Step 1: Create React + Vite project**

```bash
cd /home/tutar/work/video-infra/product-meadia
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install react-router-dom axios
```

- [ ] **Step 2: Write frontend/src/api/client.ts**

```typescript
import axios from "axios";

const API_BASE = "http://localhost:8000/api/v1";

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        const { data } = await axios.post(`${API_BASE}/auth/refresh`, {
          refresh_token: refresh,
        });
        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("refresh_token", data.refresh_token);
        error.config.headers.Authorization = `Bearer ${data.access_token}`;
        return axios(error.config);
      }
    }
    return Promise.reject(error);
  }
);

export default api;
```

- [ ] **Step 3: Write frontend/src/App.tsx**

```typescript
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import CreateTaskPage from "./pages/CreateTaskPage";
import TaskDetailPage from "./pages/TaskDetailPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/tasks/new" element={<CreateTaskPage />} />
        <Route path="/tasks/:id" element={<TaskDetailPage />} />
        <Route path="*" element={<Navigate to="/dashboard" />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: React + Vite frontend scaffold with routing and API client"
```

---

### Task 21: Frontend auth pages

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/RegisterPage.tsx`
- Create: `frontend/src/context/AuthContext.tsx`

- [ ] **Step 1: Write frontend/src/context/AuthContext.tsx**

```typescript
import { createContext, useContext, useState, ReactNode } from "react";
import api from "../api/client";

interface User {
  id: string;
  email: string;
  role: string;
}

interface AuthCtx {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const login = async (email: string, password: string) => {
    const { data } = await api.post("/auth/token", {
      grant_type: "password",
      email,
      password,
    });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    const me = await api.get("/auth/me");
    setUser(me.data);
  };
  const register = async (email: string, password: string) => {
    await api.post("/auth/register", { email, password });
  };
  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
  };
  return (
    <AuthContext.Provider value={{ user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

- [ ] **Step 2: Write frontend/src/pages/LoginPage.tsx**

```typescript
import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await login(email, password);
    navigate("/dashboard");
  };

  return (
    <div style={{ maxWidth: 400, margin: "100px auto" }}>
      <h1>Login</h1>
      <form onSubmit={handleSubmit}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit">Login</button>
      </form>
      <p>
        <a href="/register">Register</a>
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Write frontend/src/pages/RegisterPage.tsx**

```typescript
import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await register(email, password);
    navigate("/login");
  };

  return (
    <div style={{ maxWidth: 400, margin: "100px auto" }}>
      <h1>Register</h1>
      <form onSubmit={handleSubmit}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit">Register</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/RegisterPage.tsx frontend/src/context/AuthContext.tsx
git commit -m "feat: frontend auth pages with login/register"
```

---

### Task 22: Frontend task pages (dashboard, create, detail)

**Files:**
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/pages/CreateTaskPage.tsx`
- Create: `frontend/src/pages/TaskDetailPage.tsx`

- [ ] **Step 1: Write frontend/src/pages/DashboardPage.tsx**

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";

export default function DashboardPage() {
  const [tasks, setTasks] = useState<any[]>([]);
  useEffect(() => {
    api.get("/tasks").then((r) => setTasks(r.data.items));
  }, []);

  return (
    <div style={{ maxWidth: 800, margin: "40px auto" }}>
      <h1>Dashboard</h1>
      <Link to="/tasks/new"><button>Create New Video</button></Link>
      <table>
        <thead>
          <tr><th>Type</th><th>Status</th><th>Created</th><th>Action</th></tr>
        </thead>
        <tbody>
          {tasks.map((t: any) => (
            <tr key={t.id}>
              <td>{t.type}</td>
              <td>{t.status}</td>
              <td>{new Date(t.created_at).toLocaleString()}</td>
              <td><Link to={`/tasks/${t.id}`}>View</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Write frontend/src/pages/CreateTaskPage.tsx**

```typescript
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";

export default function CreateTaskPage() {
  const [products, setProducts] = useState<any[]>([]);
  const [productId, setProductId] = useState("");
  const [type, setType] = useState("promo");
  const [imageCount, setImageCount] = useState(4);
  const [viralUrl, setViralUrl] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/products").then((r) => setProducts(r.data.items));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const { data } = await api.post("/tasks", {
      product_id: productId,
      type,
      image_count: imageCount,
      viral_url: type === "viral" ? viralUrl : undefined,
    });
    navigate(`/tasks/${data.id}`);
  };

  return (
    <div style={{ maxWidth: 600, margin: "40px auto" }}>
      <h1>Create Video Task</h1>
      <form onSubmit={handleSubmit}>
        <select value={productId} onChange={(e) => setProductId(e.target.value)} required>
          <option value="">Select product</option>
          {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="promo">Promotional Video</option>
          <option value="viral">Viral Remix</option>
          <option value="personify">Personification Video</option>
        </select>
        {type === "promo" && (
          <input type="number" value={imageCount} min={1} max={16} onChange={(e) => setImageCount(+e.target.value)} />
        )}
        {type === "viral" && (
          <input type="url" placeholder="Viral video URL" value={viralUrl} onChange={(e) => setViralUrl(e.target.value)} required />
        )}
        <button type="submit">Create Task</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Write frontend/src/pages/TaskDetailPage.tsx**

```typescript
import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import api from "../api/client";

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<any>(null);
  const [script, setScript] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    api.get(`/tasks/${id}`).then((r) => setTask(r.data));
    api.get(`/tasks/${id}/script`).then((r) => setScript(r.data)).catch(() => {});
    api.get(`/tasks/${id}/images`).then((r) => setImages(r.data)).catch(() => {});

    const ws = new WebSocket(`ws://localhost:8000/ws/tasks/${id}`);
    ws.onmessage = (e) => {
      const progress = JSON.parse(e.data);
      if (progress.status === "done") {
        setTask((prev: any) => ({ ...prev, status: "done", result_video_url: progress.video_url }));
      }
    };
    wsRef.current = ws;
    return () => ws.close();
  }, [id]);

  const approveScript = async () => {
    await api.put(`/tasks/${id}/script`, { approved: true });
    setTask((prev: any) => ({ ...prev, status: "imaging" }));
  };

  const reviewImage = async (imageId: string, action: "approve" | "reject") => {
    await api.put(`/tasks/${id}/images/${imageId}`, { action });
    const { data } = await api.get(`/tasks/${id}/images`);
    setImages(data);
  };

  if (!task) return <div>Loading...</div>;

  return (
    <div style={{ maxWidth: 800, margin: "40px auto" }}>
      <h1>Task: {task.type}</h1>
      <p>Status: {task.status}</p>
      {task.result_video_url && (
        <video src={task.result_video_url} controls style={{ width: "100%" }} />
      )}

      {script && script.status === "pending_review" && (
        <div>
          <h2>Script Review</h2>
          <pre>{script.content}</pre>
          <textarea defaultValue={script.content} style={{ width: "100%", height: 200 }} />
          <button onClick={approveScript}>Approve Script</button>
        </div>
      )}

      {images.length > 0 && (
        <div>
          <h2>Image Review ({images.filter((i: any) => i.status === "approved").length}/{images.length} approved)</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
            {images.map((img: any) => (
              <div key={img.id}>
                <img src={img.image_url} style={{ width: "100%" }} />
                <p>Status: {img.status}</p>
                <button onClick={() => reviewImage(img.id, "approve")} disabled={img.status === "approved"}>Approve</button>
                <button onClick={() => reviewImage(img.id, "reject")}>Reject</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/CreateTaskPage.tsx frontend/src/pages/TaskDetailPage.tsx
git commit -m "feat: frontend task pages — dashboard, create, detail with review UI"
```

---

## Self-Review

**1. Spec coverage:**
- Product CRUD → Task 8
- Task CRUD + WebSocket → Task 9
- Auth (JWT + Google OAuth) → Tasks 6, 7
- Promo video flow (script→images→review→video→tts→composite) → Task 15
- Viral video flow (analyze→confirm→rewrite→images→review→composite) → Task 16
- Personify video flow (character→review→script→review→tts+lipsync→composite) → Task 16
- Shared tools (image, video, tts, lipsync, render, transcribe, analyze) → Tasks 10–13
- Celery task dispatch → Task 17
- Observability (Langfuse @observe) → on every tool call
- Frontend (React + Vite) → Tasks 20–22
- Docker Compose → Task 19
- Database schema → Tasks 3, 4
- Tests → Task 18

**2. Placeholder scan:** None. All steps have concrete code.

**3. Type consistency:**
- `VideoAgentState` field names consistent across Tasks 14, 15, 16, 17
- Pydantic schema field names match SQLAlchemy model field names (Task 3 vs Task 5)
- API paths match OpenAPI spec
- Celery task signature `run_video_task(self, task_id: str)` matches dispatch call `run_video_task.delay(str(task.id))`
