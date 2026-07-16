from src.api.products import router
from src.schemas.product import ProductCreate
from uuid import uuid4
import pytest

def test_product_routes_include_crud_and_generate():
    paths={(r.path,tuple(r.methods)) for r in router.routes}
    assert any(p=='/products/main-image/generate' for p,_ in paths)
    assert any(p=='/products' and 'POST' in m for p,m in paths)
    assert any(p=='/products/{id}' and 'DELETE' in m for p,m in paths)

def test_create_requires_image_choice_only_at_api_boundary():
    body=ProductCreate(category_id=uuid4(),category_template_version=1,name='Cup')
    assert body.main_image_url is None and body.main_image_candidate_id is None
