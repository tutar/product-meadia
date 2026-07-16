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
