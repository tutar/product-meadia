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
    result = await db.execute(
        select(Product).offset(offset).limit(page_size).order_by(Product.created_at.desc())
    )
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
