import pytest
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
