from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_async_session
from src.auth.deps import get_current_user
from src.models.user import User
from src.models.category import Category, CategoryAttribute
from src.models.product import Product
from src.schemas.category import CategoryCreate, CategoryUpdate, CategoryOut
from src.services.category_service import get_owned_category, replace_template

router = APIRouter(prefix='/categories', tags=['categories'])

@router.post('', response_model=CategoryOut, status_code=201)
async def create(body: CategoryCreate, db: AsyncSession=Depends(get_async_session), user: User=Depends(get_current_user)):
    c=Category(user_id=user.id,name=body.name,description=body.description)
    c.attributes=[CategoryAttribute(**a.model_dump()) for a in body.attributes]; db.add(c)
    try: await db.commit(); await db.refresh(c)
    except IntegrityError: await db.rollback(); raise HTTPException(409,'name already exists')
    return c

@router.get('', response_model=list[CategoryOut])
async def list_categories(db: AsyncSession=Depends(get_async_session), user: User=Depends(get_current_user)):
    from sqlalchemy.orm import selectinload
    return (await db.execute(select(Category).where(Category.user_id==user.id).options(selectinload(Category.attributes)))).scalars().all()

@router.get('/{category_id}', response_model=CategoryOut)
async def get(category_id, db: AsyncSession=Depends(get_async_session), user: User=Depends(get_current_user)):
    c=await get_owned_category(db,user.id,category_id,load_attributes=True)
    if not c: raise HTTPException(404,'Category not found')
    return c

@router.put('/{category_id}', response_model=CategoryOut)
async def update(category_id, body: CategoryUpdate, db: AsyncSession=Depends(get_async_session), user: User=Depends(get_current_user)):
    c=await get_owned_category(db,user.id,category_id,load_attributes=True)
    if not c: raise HTTPException(404,'Category not found')
    if c.template_version != body.template_version: raise HTTPException(409, {'current_version': c.template_version})
    c.name,c.description=body.name,body.description
    await replace_template(db,c,body.template_version,[a.model_dump() for a in body.attributes])
    try: await db.commit(); await db.refresh(c)
    except IntegrityError: await db.rollback(); raise HTTPException(409,'name already exists')
    return c

@router.delete('/{category_id}', status_code=204)
async def delete(category_id, db: AsyncSession=Depends(get_async_session), user: User=Depends(get_current_user)):
    c=await get_owned_category(db,user.id,category_id)
    if not c: raise HTTPException(404,'Category not found')
    count=(await db.execute(select(func.count()).select_from(Product).where(getattr(Product,'category_id',None)==category_id))).scalar() if hasattr(Product,'category_id') else 0
    if count: raise HTTPException(409, {'product_count': count})
    await db.delete(c); await db.commit()
