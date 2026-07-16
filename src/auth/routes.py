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
from src.services.outbox import record_event

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def persist_registered_user(db: AsyncSession, user: User) -> User:
    db.add(user)
    await db.flush()
    await record_event(db, "user.registered", user.id, {"user_id": str(user.id)})
    await db.commit()
    await db.refresh(user)
    return user


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
    await persist_registered_user(db, user)
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
                "redirect_uri": body.redirect_uri or "postmessage",
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
            await persist_registered_user(db, user)
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
