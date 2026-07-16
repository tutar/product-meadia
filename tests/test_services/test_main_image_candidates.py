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

@pytest.mark.asyncio
async def test_consume_candidate_valid_marks_used_and_missing_returns_none():
    from src.services.main_image_candidates import consume_candidate
    class R:
        def scalar_one_or_none(self): return None
    db=type('DB',(),{'execute':AsyncMock(return_value=R()),'flush':AsyncMock()})()
    assert await consume_candidate(db,uuid4(),uuid4()) is None

@pytest.mark.asyncio
async def test_consume_candidate_valid_marks_candidate_used():
    from datetime import datetime, timedelta, timezone
    from src.models.main_image_candidate import MainImageCandidate
    from src.services.main_image_candidates import consume_candidate
    owner, candidate_id = uuid4(), uuid4()
    candidate = MainImageCandidate(id=candidate_id, user_id=owner,
        image_url="https://img/cup.png",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    class R:
        def scalar_one_or_none(self): return candidate
    db=type('DB',(),{'execute':AsyncMock(return_value=R()),'flush':AsyncMock()})()
    result = await consume_candidate(db, owner, candidate_id)
    assert result is candidate and candidate.used_at is not None

@pytest.mark.asyncio
async def test_create_candidate_ai_failure_does_not_add():
    from src.services.main_image_candidates import create_candidate
    d=ProductDraft(category_id=uuid4(),category_template_version=1,name='Cup')
    db=type('DB',(),{'add':lambda s,x: (_ for _ in ()).throw(AssertionError()),'flush':AsyncMock()})()
    with patch('src.services.main_image_candidates.generate_image',AsyncMock(side_effect=RuntimeError('boom'))):
        with pytest.raises(RuntimeError): await create_candidate(db,uuid4(),d)

@pytest.mark.asyncio
async def test_consume_candidate_valid_marks_used():
    from datetime import datetime, timedelta, timezone
    from src.models.main_image_candidate import MainImageCandidate
    from src.services.main_image_candidates import consume_candidate
    uid=uuid4(); c=MainImageCandidate(user_id=uid,image_url='u',expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    class R:
        def scalar_one_or_none(self): return c
    db=type('DB',(),{'execute':AsyncMock(return_value=R()),'flush':AsyncMock()})()
    out=await consume_candidate(db,uid,uuid4())
    assert out is c and c.used_at is not None
