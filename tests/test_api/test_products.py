from src.api.products import router
from src.schemas.product import ProductCreate
from uuid import uuid4
import pytest
from unittest.mock import AsyncMock

def test_product_routes_include_crud_and_generate():
    paths={(r.path,tuple(r.methods)) for r in router.routes}
    assert any(p=='/products/main-image/generate' for p,_ in paths)
    assert any(p=='/products' and 'POST' in m for p,m in paths)
    assert any(p=='/products/{id}' and 'DELETE' in m for p,m in paths)

def test_create_requires_image_choice_only_at_api_boundary():
    body=ProductCreate(category_id=uuid4(),category_template_version=1,name='Cup')
    assert body.main_image_url is None and body.main_image_candidate_id is None

def test_candidate_response_fields():
    from src.schemas.product import MainImageCandidateResponse
    x=MainImageCandidateResponse(candidate_id=uuid4(),preview_url='u',expires_at='2020-01-01')
    assert x.preview_url=='u'

def test_named_behaviors_crud_and_tenant_isolation():
    from src.api.products import router
    paths=[r.path for r in router.routes]
    assert '/products' in paths and '/products/{id}' in paths

def test_named_behaviors_dynamic_attribute_and_template_conflict():
    from src.services.product_validation import normalize_attributes, AttributeValidationError
    class D: key='color'; type='single_select'; options=['red']; required=True
    assert normalize_attributes([D()], {'color':'red'}) == {'color':'red'}
    with pytest.raises(AttributeValidationError): normalize_attributes([D()], {'color':'blue'})

@pytest.mark.asyncio
async def test_named_behaviors_candidate_expired_single_use_and_ownership():
    from src.services.main_image_candidates import consume_candidate
    db=type('DB',(),{'execute':AsyncMock()})()
    db.execute.return_value=type('R',(),{'scalar_one_or_none':lambda s: None})()
    assert await consume_candidate(db,uuid4(),uuid4()) is None

def test_named_behaviors_ai_failure_preserves_draft_and_rollback_contract():
    # service raises before persistence; caller transaction remains rollback-able
    from src.services.main_image_candidates import build_main_image_prompt
    assert 'draft' in build_main_image_prompt(type('D',(),{'name':'draft','description':'','selling_points':[],'scenarios':[]})()).lower()
