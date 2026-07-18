from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from src.models.main_image_candidate import MainImageCandidate
from src.tools.image_gen import generate_image

def build_main_image_prompt(draft):
    parts=[draft.name, draft.description or '', *draft.selling_points]
    product_details = '. '.join(x.strip() for x in parts if x and x.strip())
    return (
        'Professional isolated e-commerce product packshot. '
        'Show one single product as the clear primary subject, centered and large, '
        'front-facing, fully visible, with realistic material and clean studio lighting. '
        'Use a clean, minimal background with no props, no scenery, no flowers, no plants, '
        'no people, no hands, no extra objects, no patterns, no text, and no watermark. '
        f'Product details: {product_details}'
    )

def build_packaging_image_prompt(draft, view_prompt: str | None = None):
    details = '. '.join(x.strip() for x in [draft.name, draft.description or '', *draft.selling_points] if x and x.strip())
    return (
        'Professional isolated e-commerce packaging packshot. Show the product and its real-looking retail packaging, '
        'centered, fully visible, on a clean white or neutral studio background. No people, hands, scenery, props, '
        'watermarks, or unrelated objects. Keep the product appearance consistent with the supplied reference image. '
        f'Packaging view: {view_prompt or "front view"}. Product details: {details}'
    )

async def create_candidate(db,user_id,draft,media,fetch):
    url=await generate_image(build_main_image_prompt(draft))
    asset=await media.create_from_remote(
        owner_user_id=user_id, category="product_image", source_url=url,
        filename=f"candidate-{user_id}.png", fetch=fetch,
        source_provider="image-provider",
        idempotency_key=f"candidate:{user_id}:{url}",
    )
    c=MainImageCandidate(user_id=user_id,image_url="",asset_id=asset.id,expires_at=datetime.now(timezone.utc)+timedelta(hours=24))
    db.add(c); await db.flush(); return c

async def consume_candidate(db,user_id,candidate_id):
    now=datetime.now(timezone.utc)
    c=(await db.execute(select(MainImageCandidate).where(MainImageCandidate.id==candidate_id,MainImageCandidate.user_id==user_id,MainImageCandidate.used_at.is_(None),MainImageCandidate.expires_at>now).with_for_update())).scalar_one_or_none()
    if not c: return None
    c.used_at=now; await db.flush(); return c

async def cleanup_external_asset(url):
    return None
