import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from src.schemas.product import ProductDraft
from src.services.main_image_candidates import build_main_image_prompt, create_candidate

def test_prompt_is_generic_and_uses_draft():
    d=ProductDraft(category_id=uuid4(),category_template_version=1,name='Cup',description='Ceramic',selling_points=['Durable'])
    p=build_main_image_prompt(d)
    assert 'Cup' in p and 'Ceramic' in p and 'perfume' not in p.lower()

@pytest.mark.asyncio
async def test_candidate_expires_in_24_hours():
    db=AsyncMock(); db.add=lambda x: None
    d=ProductDraft(category_id=uuid4(),category_template_version=1,name='Cup')
    with patch('src.services.main_image_candidates.generate_image',AsyncMock(return_value='https://img/cup.png')):
        c=await create_candidate(db,uuid4(),d)
    assert c.image_url.endswith('cup.png')
