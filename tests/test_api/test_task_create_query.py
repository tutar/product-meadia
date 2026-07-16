from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.category import Category
from src.models.product import Product
from src.models.task import VideoTask


def test_task_product_query_can_eager_load_category_attributes():
    query = select(Product).options(
        selectinload(Product.category).selectinload(Category.attributes)
    )

    assert "products" in str(query)


def test_task_response_fields_are_mapped_on_model():
    assert hasattr(VideoTask, "progress_log")
