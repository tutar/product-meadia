from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.category import Category, CategoryAttribute

async def get_owned_category(db: AsyncSession, user_id, category_id, *, load_attributes=False):
    q = select(Category).where(Category.id == category_id, Category.user_id == user_id)
    if load_attributes:
        from sqlalchemy.orm import selectinload
        q = q.options(selectinload(Category.attributes))
    return (await db.execute(q)).scalar_one_or_none()

async def replace_template(db, category, expected_version, attributes):
    if category.template_version != expected_version:
        return None
    category.template_version += 1
    category.attributes.clear()
    for a in attributes:
        category.attributes.append(CategoryAttribute(**a))
    await db.flush()
    return category
