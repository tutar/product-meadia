from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.catalog_initialization import CatalogInitialization
from src.models.category import Category, CategoryAttribute
from src.models.product import Product
from src.config import settings
from src.media.rustfs import create_rustfs_storage
from src.services.media_service import MediaService

SAMPLE_VERSION = 1
SAMPLE_CATEGORIES = (
    {"key": "sample-perfume", "name": "Perfume", "attributes": ({"key": "scent", "label": "Scent", "type": "text", "required": True, "options": (), "sort_order": 0},), "products": ({"name": "Sample Perfume", "attributes": {"scent": "Floral"}},)},
    {"key": "sample-electronics", "name": "Electronics", "attributes": ({"key": "color", "label": "Color", "type": "single_select", "required": True, "options": ("black", "white"), "sort_order": 0},), "products": ({"name": "Sample Headphones", "attributes": {"color": "black"}},)},
    {"key": "sample-food", "name": "Food", "attributes": ({"key": "weight", "label": "Weight", "type": "number", "required": True, "options": (), "sort_order": 0},), "products": ({"name": "Sample Snack", "attributes": {"weight": 100}},)},
)


class SampleCatalogInitializer:
    async def initialize(self, db, user_id, sample_version: int = SAMPLE_VERSION):
        result = await db.execute(select(CatalogInitialization).where(
            CatalogInitialization.user_id == user_id,
            CatalogInitialization.sample_version == sample_version,
        ).with_for_update())
        initialization = result.scalar_one_or_none()
        if initialization and initialization.status == "completed":
            return initialization
        media = MediaService(db, create_rustfs_storage(settings))
        if initialization is None:
            initialization = CatalogInitialization(user_id=user_id, sample_version=sample_version)
            db.add(initialization)
        initialization.status = "pending"
        initialization.attempts = (initialization.attempts or 0) + 1
        try:
            existing = (await db.execute(select(Category).where(Category.user_id == user_id).options(selectinload(Category.attributes)))).scalars().all()
            by_name = {category.name: category for category in existing}
            for sample in SAMPLE_CATEGORIES:
                category = by_name.get(sample["name"])
                if category is None:
                    category = Category(user_id=user_id, name=sample["name"])
                    category.attributes = [CategoryAttribute(**{**item, "options": list(item["options"])}) for item in sample["attributes"]]
                    db.add(category)
                    await db.flush()
                product_names = set((await db.execute(select(Product.name).where(Product.user_id == user_id, Product.category_id == category.id))).scalars().all())
                for item in sample["products"]:
                    if item["name"] not in product_names:
                        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect width="100%" height="100%" fill="#eee"/><text x="50%" y="50%" text-anchor="middle">{item["name"]}</text></svg>'.encode()
                        asset=await media.create_asset(owner_user_id=user_id,category="product_image",data=svg,content_type="image/svg+xml",filename=f'{sample["key"]}.svg',idempotency_key=f'sample:{sample_version}:{sample["key"]}')
                        db.add(Product(user_id=user_id, category_id=category.id, category_template_version=category.template_version, main_image_url="", main_image_asset_id=asset.id, main_image_source="asset", selling_points=[], scenarios=[], description=None, **item))
            initialization.status = "completed"
            initialization.completed_at = datetime.now(timezone.utc)
            initialization.error_message = None
            await db.flush()
            return initialization
        except Exception as exc:
            initialization.status = "failed"
            initialization.error_message = str(exc)
            await db.flush()
            raise
