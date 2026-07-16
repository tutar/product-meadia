import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from fastapi import HTTPException
from src.api.categories import get as get_category, delete as delete_category, update as update_category, create as create_category, list_categories
from src.schemas.category import CategoryCreate
from src.schemas.category import CategoryUpdate
from src.schemas.category import CategoryAttributeInput

def test_selection_options_validation():
    with pytest.raises(ValueError):
        CategoryAttributeInput(key='x', label='X', type='single_select', options=[])
    with pytest.raises(ValueError):
        CategoryAttributeInput(key='x', label='X', type='text', options=['a'])

def test_selection_options_unique():
    with pytest.raises(ValueError):
        CategoryAttributeInput(key='x', label='X', type='multi_select', options=['a','a'])


@pytest.mark.parametrize("type_", ["text", "number", "boolean"])
def test_scalar_attribute_types_reject_options(type_):
    item = CategoryAttributeInput(key="x", label="X", type=type_)
    assert item.type == type_ and item.options == []
    with pytest.raises(ValueError):
        CategoryAttributeInput(key="x", label="X", type=type_, options=["a"])


@pytest.mark.parametrize("type_", ["single_select", "multi_select"])
def test_selection_attribute_types_require_valid_options(type_):
    item = CategoryAttributeInput(key="x", label="X", type=type_, options=["a", "b"])
    assert item.type == type_
    with pytest.raises(ValueError):
        CategoryAttributeInput(key="x", label="X", type=type_, options=["a", ""])


def test_attribute_type_is_restricted():
    with pytest.raises(ValueError):
        CategoryAttributeInput(key="x", label="X", type="url")

class _Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value
    def scalar_one(self): return self.value

class _DBError:
    pgcode = "23505"
    constraint_name = "categories_user_id_name_key"

class _UnknownDBError:
    pgcode = "40001"

@pytest.mark.asyncio
async def test_get_cross_user_is_404():
    db = AsyncMock(); db.execute.return_value = _Result(None)
    with pytest.raises(HTTPException) as err:
        await get_category(uuid4(), db, SimpleNamespace(id=uuid4()))
    assert err.value.status_code == 404
    assert "user_id" in str(db.execute.call_args.args[0])

@pytest.mark.asyncio
async def test_update_version_conflict_returns_current_version():
    category = SimpleNamespace(id=uuid4(), user_id=uuid4(), template_version=3, name="Old", description=None)
    db = AsyncMock(); db.execute.return_value = _Result(category)
    with pytest.raises(HTTPException) as err:
        await update_category(category.id, CategoryUpdate(name="New", template_version=2, attributes=[]), db, SimpleNamespace(id=category.user_id))
    assert err.value.status_code == 409 and err.value.detail["current_version"] == 3

@pytest.mark.asyncio
async def test_delete_referenced_returns_structured_conflict():
    category = SimpleNamespace(id=uuid4(), user_id=uuid4())
    db = AsyncMock(); db.execute.side_effect = [_Result(category), _Result(2)]
    with pytest.raises(HTTPException) as err:
        await delete_category(category.id, db, SimpleNamespace(id=category.user_id))
    assert err.value.status_code == 409 and err.value.detail["product_count"] == 2

@pytest.mark.asyncio
async def test_create_category_success():
    db = AsyncMock(); db.commit.return_value = None
    db.add = Mock()
    loaded = SimpleNamespace(name="Books", attributes=[])
    db.execute.return_value = _Result(loaded)
    body = CategoryCreate(name="Books", attributes=[])
    result = await create_category(body, db, SimpleNamespace(id=uuid4()))
    assert result.name == "Books"; db.add.assert_called_once(); db.commit.assert_awaited_once()
    assert db.execute.await_count >= 1

@pytest.mark.asyncio
async def test_list_categories_success():
    categories = [SimpleNamespace(id=uuid4(), name="Books", description=None, template_version=1, attributes=[])]
    db = AsyncMock(); db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: categories))
    assert await list_categories(db, SimpleNamespace(id=uuid4())) == categories

@pytest.mark.asyncio
async def test_update_category_success():
    category = SimpleNamespace(id=uuid4(), user_id=uuid4(), template_version=1, name="Old", description=None, attributes=[])
    db = AsyncMock(); db.execute.return_value = _Result(category)
    body = CategoryUpdate(name="New", template_version=1, attributes=[])
    result = await update_category(category.id, body, db, SimpleNamespace(id=category.user_id))
    assert result.name == "New"; assert db.commit.await_count == 1

@pytest.mark.asyncio
async def test_delete_category_success():
    category = SimpleNamespace(id=uuid4(), user_id=uuid4())
    db = AsyncMock(); db.execute.side_effect = [_Result(category), _Result(0)]
    await delete_category(category.id, db, SimpleNamespace(id=category.user_id))
    db.delete.assert_awaited_once_with(category); db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_create_duplicate_name_returns_409():
    from sqlalchemy.exc import IntegrityError
    db = AsyncMock(); db.add = Mock(); db.commit.side_effect = IntegrityError("duplicate", {}, _DBError())
    with pytest.raises(HTTPException) as err:
        await create_category(CategoryCreate(name="Books"), db, SimpleNamespace(id=uuid4()))
    assert err.value.status_code == 409

@pytest.mark.asyncio
async def test_create_unknown_integrity_error_is_not_masked():
    from sqlalchemy.exc import IntegrityError
    db = AsyncMock(); db.add = Mock(); db.commit.side_effect = IntegrityError("serialization", {}, _UnknownDBError())
    with pytest.raises(IntegrityError):
        await create_category(CategoryCreate(name="Books"), db, SimpleNamespace(id=uuid4()))
