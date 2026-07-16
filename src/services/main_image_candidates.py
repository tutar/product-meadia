from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from src.models.main_image_candidate import MainImageCandidate
from src.tools.image_gen import generate_image

def build_main_image_prompt(draft):
    parts=[draft.name, draft.description or '', *draft.selling_points, *draft.scenarios]
    return 'Professional catalog product hero image. ' + '. '.join(x.strip() for x in parts if x and x.strip())

async def create_candidate(db,user_id,draft):
    url=await generate_image(build_main_image_prompt(draft))
    c=MainImageCandidate(user_id=user_id,image_url=url,expires_at=datetime.now(timezone.utc)+timedelta(hours=24))
    db.add(c); await db.flush(); return c

async def consume_candidate(db,user_id,candidate_id):
    now=datetime.now(timezone.utc)
    c=(await db.execute(select(MainImageCandidate).where(MainImageCandidate.id==candidate_id,MainImageCandidate.user_id==user_id,MainImageCandidate.used_at.is_(None),MainImageCandidate.expires_at>now).with_for_update())).scalar_one_or_none()
    if not c: return None
    c.used_at=now; await db.flush(); return c

async def cleanup_external_asset(url):
    return None
