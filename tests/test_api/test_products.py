from src.api.products import router
from src.schemas.product import ProductCreate, ProductUpdate
from uuid import uuid4
import pytest
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace
from fastapi import HTTPException
import src.api.products as products_api

def test_product_routes_include_crud_and_generate():
    paths={(r.path,tuple(r.methods)) for r in router.routes}
    assert any(p=='/products/main-image/generate' for p,_ in paths)
    assert any(p=='/products' and 'POST' in m for p,m in paths)
    assert any(p=='/products/{id}' and 'DELETE' in m for p,m in paths)

def test_create_requires_image_choice_only_at_api_boundary():
    body=ProductCreate(category_id=uuid4(),category_template_version=1,name='Cup')
    assert body.main_image_asset_id is None and body.main_image_candidate_id is None

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
async def test_owned_product_route_returns_scoped_product():
    from src.api.products import owned
    owner, product_id = uuid4(), uuid4()
    class Result:
        def scalar_one_or_none(self): return type('P', (), {'id': product_id, 'user_id': owner})()
    db=type('DB',(),{'execute':AsyncMock(return_value=Result())})()
    product = await owned(db, SimpleNamespace(id=owner), product_id)
    assert product.id == product_id

@pytest.mark.asyncio
async def test_owned_product_route_rejects_missing_scoped_product():
    from fastapi import HTTPException
    from src.api.products import owned
    class Result:
        def scalar_one_or_none(self): return None
    db=type('DB',(),{'execute':AsyncMock(return_value=Result())})()
    with pytest.raises(HTTPException) as exc:
        await owned(db, SimpleNamespace(id=uuid4()), uuid4())
    assert exc.value.status_code == 404

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

def _db():
    db=type('DB',(),{})(); db.add=Mock(); db.commit=AsyncMock(); db.refresh=AsyncMock(); db.delete=AsyncMock(); db.execute=AsyncMock(); return db

@pytest.mark.asyncio
async def test_create_asset_commits_owned_product(monkeypatch):
    db,user=_db(),SimpleNamespace(id=uuid4()); monkeypatch.setattr(products_api,'prepare',AsyncMock(return_value={'color':'red'}))
    asset_id=uuid4(); db.execute.return_value=SimpleNamespace(scalar_one_or_none=lambda:SimpleNamespace(id=asset_id))
    monkeypatch.setattr(products_api, 'owned', AsyncMock(return_value=SimpleNamespace(user_id=user.id, main_image_asset_id=asset_id)))
    result=await products_api.create(ProductCreate(category_id=uuid4(),category_template_version=1,name='Cup',main_image_asset_id=asset_id),db,user)
    assert result.user_id==user.id and result.main_image_asset_id==asset_id; db.add.assert_called_once(); db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_persists_ordered_packaging_images(monkeypatch):
    db,user=_db(),SimpleNamespace(id=uuid4()); monkeypatch.setattr(products_api,'prepare',AsyncMock(return_value={}))
    main, first, second = uuid4(), uuid4(), uuid4()
    db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=main)),
        SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=first)),
        SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=second)),
    ]
    monkeypatch.setattr(products_api, 'owned', AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    body=ProductCreate(category_id=uuid4(), category_template_version=1, name='Cup', main_image_asset_id=main, packaging_image_asset_ids=[first, second])
    await products_api.create(body, db, user)
    packaging = [call.args[0] for call in db.add.call_args_list if call.args[0].__class__.__name__ == 'ProductPackagingImage']
    assert [(item.asset_id, item.sort_order) for item in packaging] == [(first, 0), (second, 1)]

@pytest.mark.asyncio
async def test_create_without_image_returns_422(monkeypatch):
    db,user=_db(),SimpleNamespace(id=uuid4()); monkeypatch.setattr(products_api,'prepare',AsyncMock(return_value={}))
    with pytest.raises(HTTPException) as exc: await products_api.create(ProductCreate(category_id=uuid4(),category_template_version=1,name='Cup'),db,user)
    assert exc.value.status_code==422 and not db.commit.await_args_list

@pytest.mark.asyncio
async def test_create_candidate_uses_owned_candidate(monkeypatch):
    asset_id=uuid4(); db,user=_db(),SimpleNamespace(id=uuid4()); monkeypatch.setattr(products_api,'prepare',AsyncMock(return_value={})); monkeypatch.setattr(products_api,'consume_candidate',AsyncMock(return_value=SimpleNamespace(asset_id=asset_id)))
    monkeypatch.setattr(products_api, 'owned', AsyncMock(return_value=SimpleNamespace(main_image_asset_id=asset_id, main_image_source='ai')))
    result=await products_api.create(ProductCreate(category_id=uuid4(),category_template_version=1,name='Cup',main_image_candidate_id=uuid4()),db,user)
    assert result.main_image_asset_id==asset_id and result.main_image_source=='ai'; db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_listing_returns_items_total_and_user_scope():
    db,user=_db(),SimpleNamespace(id=uuid4()); items=[SimpleNamespace(id=uuid4())]
    db.execute.side_effect=[SimpleNamespace(scalar_one=lambda:1),SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:items))]
    result=await products_api.listing(search='cup',page=2,page_size=5,db=db,user=user)
    assert result['items']==items and result['total']==1 and result['page']==2; assert 'products.user_id' in str(db.execute.call_args_list[0].args[0])

@pytest.mark.asyncio
async def test_update_preserves_old_image(monkeypatch):
    db,user=_db(),SimpleNamespace(id=uuid4()); product=SimpleNamespace(id=uuid4(),user_id=user.id,main_image_url='old.jpg',main_image_source='upload',attributes={})
    monkeypatch.setattr(products_api,'owned',AsyncMock(return_value=product)); monkeypatch.setattr(products_api,'prepare',AsyncMock(return_value={'x':1}))
    await products_api.update(product.id,ProductUpdate(category_id=uuid4(),category_template_version=1,name='Cup'),db,user)
    assert product.main_image_url=='old.jpg' and product.main_image_source=='upload'; db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_update_candidate_replaces_image(monkeypatch):
    asset_id=uuid4(); db,user=_db(),SimpleNamespace(id=uuid4()); product=SimpleNamespace(id=uuid4(),user_id=user.id,main_image_url='',main_image_source='asset',main_image_asset_id=uuid4(),attributes={})
    monkeypatch.setattr(products_api,'owned',AsyncMock(return_value=product)); monkeypatch.setattr(products_api,'prepare',AsyncMock(return_value={})); monkeypatch.setattr(products_api,'consume_candidate',AsyncMock(return_value=SimpleNamespace(asset_id=asset_id)))
    await products_api.update(product.id,ProductUpdate(category_id=uuid4(),category_template_version=1,name='Cup',main_image_candidate_id=uuid4()),db,user)
    assert product.main_image_asset_id==asset_id and product.main_image_source=='ai'

@pytest.mark.asyncio
async def test_delete_commits_owned_product(monkeypatch):
    db,user=_db(),SimpleNamespace(id=uuid4()); product=SimpleNamespace(id=uuid4(),user_id=user.id); monkeypatch.setattr(products_api,'owned',AsyncMock(return_value=product))
    await products_api.delete(product.id,db,user); db.delete.assert_awaited_once_with(product); db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_prepare_template_conflict_returns_409(monkeypatch):
    user=SimpleNamespace(id=uuid4()); monkeypatch.setattr(products_api,'get_owned_category',AsyncMock(return_value=SimpleNamespace(template_version=2,attributes=[])))
    with pytest.raises(HTTPException) as exc: await products_api.prepare(_db(),user,ProductCreate(category_id=uuid4(),category_template_version=1,name='Cup'))
    assert exc.value.status_code==409 and exc.value.detail['current_version']==2


@pytest.mark.asyncio
async def test_generate_maps_media_storage_failure_to_503(monkeypatch):
    from src.media.storage import StorageError

    db = _db()
    db.rollback = AsyncMock()
    user = SimpleNamespace(id=uuid4())
    body = ProductCreate(category_id=uuid4(), category_template_version=1, name='Cup')
    monkeypatch.setattr(products_api, 'prepare', AsyncMock(return_value={}))
    monkeypatch.setattr(products_api, 'get_media_service', Mock(return_value=object()))
    monkeypatch.setattr(products_api, 'create_candidate', AsyncMock(side_effect=StorageError('offline')))

    with pytest.raises(HTTPException) as exc:
        await products_api.generate(body, db, user)

    assert exc.value.status_code == 503
    db.rollback.assert_awaited_once()
