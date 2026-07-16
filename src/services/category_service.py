from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.category import Category, CategoryAttribute

async def get_owned_category(db: AsyncSession, user_id, category_id, *, load_attributes=False):
    q = select(Category).where(Category.id == category_id, Category.user_id == user_id)
    if load_attributes:
        from sqlalchemy.orm import selectinload
        q = q.options(selectinload(Category.attributes))
    return (await db.execute(q)).scalar_one_or_none()

async def replace_template(db, category, expected_version, attributes):
    locked = (await db.execute(select(Category).where(
        Category.id == category.id, Category.template_version == expected_version
    ).with_for_update())).scalar_one_or_none()
    if locked is None:
        raise ValueError("template_version_conflict")
    category = locked
    category.template_version += 1
    await db.execute(delete(CategoryAttribute).where(CategoryAttribute.category_id == category.id))
    for a in attributes:
        category.attributes.append(CategoryAttribute(**a))
    await db.flush()
    return category
