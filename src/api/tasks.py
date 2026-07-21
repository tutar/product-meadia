from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import case, delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID
from src.database import get_async_session
from src.models.user import User
from src.models.product import Product
from src.models.category import Category
from src.models.task import VideoTask
from src.models.script import Script
from src.models.creative_brief import CreativeBrief
from src.models.shot_plan import ShotPlan
from src.models.editing_blueprint import EditingBlueprint
from src.models.generated_image import GeneratedImage
from src.models.video_candidate import VideoCandidate
from src.models.review_feedback import ReviewFeedback
from src.models.viral_analysis import ViralAnalysis
from src.models.media_asset import MediaAsset
from src.models.generation_record import GenerationRecord
from src.models.model_configuration import StageModelSelection
from src.schemas.task import (
    TaskCreate, TaskResponse, ScriptResponse, ScriptUpdate, CreativeBriefResponse, CreativeBriefUpdate,
    ShotPlanResponse, ShotPlanUpdate, EditingBlueprintResponse,
    ImageResponse, ImageReview, CandidateReview, RegenerateRequest, VideoCandidateResponse, ViralAnalysisResponse,
    GenerationRecordResponse, GenerationRecordExportRequest,
    StageModelSelectionResponse, StageModelSelectionUpdate,
)
from src.auth.deps import get_current_user
from src.tasks.execution import feedback_stage, stage_for_node
from src.tasks.recovery import is_stale_task
from src.services.product_context import build_product_snapshot
from src.api.media import get_media_service
from src.services.media_service import MediaService
from src.services.stage_model_selections import ModelSelectionUnavailableError, freeze_stage_model_selections
from src.services.stage_model_selections import replace_stage_model_selection

router = APIRouter(prefix="/tasks", tags=["tasks"])
ACTIVE_TASK_STATUSES = ("pending", "planning", "creative_brief_review", "shot_plan_review", "scripting", "script_review", "imaging", "image_review", "character_review", "video_gen", "video_review", "compositing", "composition_review", "cancellation_requested")
TERMINAL_TASK_STATUSES = {"done", "failed", "cancelled"}


def blocks_new_task(task: VideoTask) -> bool:
    return task.status in ACTIVE_TASK_STATUSES and not is_stale_task(task.status, task.updated_at)


async def owned_task(db, user, task_id):
    task = (await db.execute(select(VideoTask).where(
        VideoTask.id == task_id, VideoTask.user_id == user.id
    ))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


SENSITIVE_GENERATION_PAYLOAD_KEYS = ("authorization", "api_key", "token", "secret", "password", "url", "data_uri")


def sanitized_provider_payload(payload):
    """Keep provider request shape without retaining credentials or transient media access."""
    if isinstance(payload, list):
        return [sanitized_provider_payload(value) for value in payload]
    if not isinstance(payload, dict):
        return payload
    return {
        key: sanitized_provider_payload(value)
        for key, value in payload.items()
        if not any(sensitive in key.lower() for sensitive in SENSITIVE_GENERATION_PAYLOAD_KEYS)
    }


async def mark_latest_training_candidate(db: AsyncSession, task_id: UUID, stage: str, outcome: str) -> None:
    """Preserve review signal without promoting rejected generations to training data."""
    record = await db.scalar(select(GenerationRecord).where(
        GenerationRecord.task_id == task_id,
        GenerationRecord.stage == stage,
    ).order_by(GenerationRecord.attempt.desc(), GenerationRecord.created_at.desc()).limit(1))
    if record:
        record.training_candidate = outcome


@router.post("/{task_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_task(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    task = await owned_task(db, user, task_id)
    if task.status in TERMINAL_TASK_STATUSES:
        raise HTTPException(status_code=409, detail="Terminal tasks cannot be cancelled")
    if task.status != "cancellation_requested":
        task.status = "cancellation_requested"
        task.progress_log = list(task.progress_log or []) + [{
            "stage": "other", "step": "cancellation_requested", "time": datetime.utcnow().isoformat() + "Z",
            "status": "ok", "summary": "Cancellation requested; no downstream steps will start",
        }]
        await db.commit()
    from src.tasks.video_tasks import run_video_task
    run_video_task.delay(str(task_id))
    return {"status": "cancellation_requested"}


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    task = await owned_task(db, user, task_id)
    if task.status not in TERMINAL_TASK_STATUSES:
        raise HTTPException(status_code=409, detail="Only terminal tasks can be deleted")
    assets = (await db.scalars(select(MediaAsset).where(MediaAsset.task_id == task.id))).all()
    delete_after = datetime.now(timezone.utc) + timedelta(days=7)
    for asset in assets:
        shared_with_product = await db.scalar(select(Product.id).where(Product.main_image_asset_id == asset.id).limit(1))
        asset.task_id = None
        if not shared_with_product:
            asset.status = "pending_delete"
            asset.delete_after = delete_after
    # Use database cascades for required task-owned rows (script, images and
    # candidates). ORM deletion otherwise attempts to null their non-null
    # task_id foreign keys before PostgreSQL can apply ON DELETE CASCADE.
    await db.execute(delete(VideoTask).where(VideoTask.id == task.id))
    await db.commit()


def validated_feedback(feedback: str | None) -> str:
    value = (feedback or "").strip()
    if not 5 <= len(value) <= 1000:
        raise HTTPException(status_code=422, detail="Feedback must contain 5 to 1000 characters")
    return value


def record_feedback(db: AsyncSession, task: VideoTask, target_type: str, target_id: UUID | None, feedback: str) -> None:
    db.add(ReviewFeedback(task_id=task.id, target_type=target_type, target_id=target_id, content=feedback))
    task.progress_log = list(task.progress_log or []) + [{
        "stage": feedback_stage(target_type),
        "step": "review_feedback",
        "time": datetime.utcnow().isoformat() + "Z",
        "status": "ok",
        "summary": "Improvement guidance recorded for regeneration",
    }]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    product_result = await db.execute(
        select(Product)
        .where(Product.id == body.product_id, Product.user_id == user.id)
        .options(
            selectinload(Product.category).selectinload(Category.attributes),
            selectinload(Product.packaging_images),
        )
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if body.type == "viral" and not body.viral_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="viral_url required for viral type")

    existing = (await db.execute(
        select(VideoTask).where(
            VideoTask.user_id == user.id,
            VideoTask.product_id == body.product_id,
            VideoTask.type == body.type,
            VideoTask.status.in_(ACTIVE_TASK_STATUSES),
        ).order_by(VideoTask.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing and blocks_new_task(existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "An active task already exists", "task_id": str(existing.id)},
        )

    task = VideoTask(
        user_id=user.id,
        product_id=body.product_id,
        product_snapshot=build_product_snapshot(product, product.category),
        type=body.type,
        image_count=body.image_count,
        status="pending",
    )
    db.add(task)
    await db.flush()
    try:
        await freeze_stage_model_selections(
            db, task, user.id, overrides=body.stage_model_configuration_ids,
        )
    except ModelSelectionUnavailableError as error:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    await db.commit()
    await db.refresh(task)

    from src.tasks.video_tasks import run_video_task
    celery_result = run_video_task.delay(str(task.id))
    task.celery_task_id = celery_result.id
    task.status = "planning"
    await db.commit()
    await db.refresh(task)

    return task


@router.get("")
async def list_tasks(
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    query = select(VideoTask).where(VideoTask.user_id == user.id).options(selectinload(VideoTask.script), selectinload(VideoTask.images))
    if category_id:
        query = query.join(Product, VideoTask.product_id == Product.id).where(Product.category_id == category_id)
    if product_id:
        query = query.where(VideoTask.product_id == product_id)
    if type:
        query = query.where(VideoTask.type == type)
    if status:
        query = query.where(VideoTask.status == status)

    queue_priority = case(
        (VideoTask.status.in_(("creative_brief_review", "script_review", "shot_plan_review", "image_review", "character_review", "video_review", "composition_review")), 0),
        (VideoTask.status.in_(("pending", "planning", "scripting", "imaging", "video_gen", "compositing")), 1),
        else_=2,
    )
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(queue_priority, VideoTask.updated_at.desc()).offset(offset).limit(page_size))
    items = result.scalars().all()
    total_result = await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    return {"items": items, "total": total_result.scalar()}


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(VideoTask).where(VideoTask.id == task_id, VideoTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/stage-model-selections", response_model=list[StageModelSelectionResponse])
async def list_stage_model_selections(
    task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user),
):
    await owned_task(db, user, task_id)
    return (await db.scalars(select(StageModelSelection).where(
        StageModelSelection.task_id == task_id,
    ).order_by(StageModelSelection.created_at))).all()


@router.put("/{task_id}/stage-model-selections/{stage}", response_model=StageModelSelectionResponse)
async def update_stage_model_selection(
    task_id: UUID, stage: str, body: StageModelSelectionUpdate,
    db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user),
):
    task = await owned_task(db, user, task_id)
    selection = await replace_stage_model_selection(db, task, user.id, stage, body.model_configuration_id)
    await db.commit()
    return selection


@router.get("/{task_id}/generation-records", response_model=list[GenerationRecordResponse])
async def list_generation_records(
    task_id: UUID,
    stage: str | None = None,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await owned_task(db, user, task_id)
    query = select(GenerationRecord).where(GenerationRecord.task_id == task_id)
    if stage:
        query = query.where(GenerationRecord.stage == stage)
    records = (await db.scalars(query.order_by(GenerationRecord.attempt.desc(), GenerationRecord.created_at.desc(), GenerationRecord.id.desc()))).all()
    for record in records:
        record.provider_payload = sanitized_provider_payload(record.provider_payload)
        record.media_asset_ids = [str(asset_id) for asset_id in record.media_asset_ids]
    return records


@router.post("/{task_id}/generation-records/export", response_model=list[GenerationRecordResponse])
async def export_generation_records(
    task_id: UUID,
    body: GenerationRecordExportRequest,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """Return only owner-selected positive Training Candidates for dataset tooling."""
    await owned_task(db, user, task_id)
    records = (await db.scalars(select(GenerationRecord).where(
        GenerationRecord.task_id == task_id,
        GenerationRecord.id.in_(body.record_ids),
        GenerationRecord.training_candidate == "approved",
    ).order_by(GenerationRecord.created_at))).all()
    for record in records:
        record.provider_payload = sanitized_provider_payload(record.provider_payload)
        record.media_asset_ids = [str(asset_id) for asset_id in record.media_asset_ids]
    return records


@router.get("/{task_id}/script", response_model=ScriptResponse)
async def get_script(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await owned_task(db, user, task_id)
    result = await db.execute(select(Script).where(Script.task_id == task_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@router.get("/{task_id}/creative-brief", response_model=CreativeBriefResponse)
async def get_creative_brief(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    await owned_task(db, user, task_id)
    brief = await db.scalar(select(CreativeBrief).where(CreativeBrief.task_id == task_id))
    if not brief:
        raise HTTPException(status_code=404, detail="Creative Brief not found")
    return brief


@router.put("/{task_id}/creative-brief", response_model=CreativeBriefResponse)
async def update_creative_brief(
    task_id: UUID,
    body: CreativeBriefUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    task = await owned_task(db, user, task_id)
    brief = await db.scalar(select(CreativeBrief).where(CreativeBrief.task_id == task_id))
    if not brief:
        raise HTTPException(status_code=404, detail="Creative Brief not found")
    if body.content is not None:
        brief.content = body.content
    if body.approved:
        brief.status = "approved"
        task.status = "scripting"
        await mark_latest_training_candidate(db, task_id, "planning", "approved")
    else:
        record_feedback(db, task, "creative_brief", brief.id, validated_feedback(body.feedback))
        brief.content = {}
        brief.status = "rejected"
        task.status = "planning"
        await mark_latest_training_candidate(db, task_id, "planning", "negative")
    await db.commit()
    from src.tasks.video_tasks import run_video_task
    run_video_task.delay(str(task_id))
    return brief


@router.get("/{task_id}/shot-plan", response_model=ShotPlanResponse)
async def get_shot_plan(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    await owned_task(db, user, task_id)
    plan = await db.scalar(select(ShotPlan).where(ShotPlan.task_id == task_id))
    if not plan:
        raise HTTPException(status_code=404, detail="Shot Plan not found")
    return plan


@router.put("/{task_id}/shot-plan", response_model=ShotPlanResponse)
async def update_shot_plan(
    task_id: UUID,
    body: ShotPlanUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    task = await owned_task(db, user, task_id)
    plan = await db.scalar(select(ShotPlan).where(ShotPlan.task_id == task_id))
    if not plan:
        raise HTTPException(status_code=404, detail="Shot Plan not found")
    if body.shots is not None:
        plan.shots = body.shots
    if body.approved:
        plan.status = "approved"
        task.status = "imaging"
        await mark_latest_training_candidate(db, task_id, "planning", "approved")
    else:
        record_feedback(db, task, "shot_plan", plan.id, validated_feedback(body.feedback))
        plan.shots = []
        plan.status = "rejected"
        task.status = "planning"
        await mark_latest_training_candidate(db, task_id, "planning", "negative")
    await db.commit()
    from src.tasks.video_tasks import run_video_task
    run_video_task.delay(str(task_id))
    return plan


@router.put("/{task_id}/script", response_model=ScriptResponse)
async def update_script(
    task_id: UUID,
    body: ScriptUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await owned_task(db, user, task_id)
    result = await db.execute(select(Script).where(Script.task_id == task_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    if body.edited_content is not None:
        script.edited_content = body.edited_content
    if body.image_prompts is not None:
        script.image_prompts = body.image_prompts
    task_result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
    task = task_result.scalar_one()
    if body.approved:
        script.status = "approved"
        task.status = "planning"
        await mark_latest_training_candidate(db, task_id, "scripting", "approved")
        await db.commit()
        await db.refresh(script)
        # Resume the graph
        from src.tasks.video_tasks import run_video_task
        run_video_task.delay(str(task_id))
    else:
        record_feedback(db, task, "script", script.id, validated_feedback(body.feedback))
        script.status = "rejected"
        task.status = "scripting"
        await mark_latest_training_candidate(db, task_id, "scripting", "negative")
        await db.commit()
        await db.refresh(script)
        from src.tasks.video_tasks import run_video_task
        run_video_task.delay(str(task_id))
    return script


@router.get("/{task_id}/images", response_model=list[ImageResponse])
async def list_images(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
    media: MediaService = Depends(get_media_service),
):
    task = await owned_task(db, user, task_id)
    result = await db.execute(
        select(GeneratedImage).where(GeneratedImage.task_id == task_id).order_by(GeneratedImage.sort_order)
    )
    images=result.scalars().all()
    return [
        {
            "id": image.id, "task_id": image.task_id, "prompt": image.prompt,
            "image_url": None, "asset_id": image.asset_id,
            "access_url": await media.access_url(image.asset_id,user.id) if image.asset_id else None,
            "sort_order": image.sort_order, "status": image.status,
            "generation_context": image.generation_context or {},
        }
        for image in images
    ]


@router.put("/{task_id}/images/{image_id}")
async def review_image(
    task_id: UUID,
    image_id: UUID,
    body: ImageReview,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await owned_task(db, user, task_id)
    result = await db.execute(
        select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.task_id == task_id)
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="Unsupported image review action")
    img.status = "approved" if body.action == "approve" else "rejected"
    await mark_latest_training_candidate(db, task_id, "imaging", "approved" if body.action == "approve" else "negative")
    if body.action == "reject":
        record_feedback(db, task, "image", img.id, validated_feedback(body.feedback))
    await db.commit()

    if body.action == "approve":
        task_result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
        task = task_result.scalar_one()
        all_approved = await db.execute(
            select(func.count(GeneratedImage.id)).where(
                GeneratedImage.task_id == task_id,
                GeneratedImage.status != "approved",
            )
        )
        if all_approved.scalar() == 0:
            task.status = "video_gen"
            await db.commit()
            # Resume the graph
            from src.tasks.video_tasks import run_video_task
            run_video_task.delay(str(task_id))
    return {"status": "ok"}


@router.post("/{task_id}/images/{image_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_image(
    task_id: UUID,
    image_id: UUID,
    body: RegenerateRequest,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    task = await owned_task(db, user, task_id)
    result = await db.execute(
        select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.task_id == task_id)
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    record_feedback(db, task, "image", img.id, validated_feedback(body.feedback))
    img.status = "rejected"
    await mark_latest_training_candidate(db, task_id, "imaging", "negative")
    img.image_url = None
    task.status = "imaging"
    await db.commit()
    from src.tasks.video_tasks import run_video_task
    run_video_task.delay(str(task_id))
    return {"status": "queued"}


@router.put("/{task_id}/characters/{image_id}")
async def review_character(
    task_id: UUID,
    image_id: UUID,
    body: ImageReview,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    task = await owned_task(db, user, task_id)
    character = await db.scalar(select(GeneratedImage).where(
        GeneratedImage.id == image_id,
        GeneratedImage.task_id == task_id,
        GeneratedImage.prompt == "character",
    ))
    if not character:
        raise HTTPException(status_code=404, detail="Character image not found")
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="Unsupported character review action")
    if body.action == "approve":
        character.status = "approved"
        task.status = "scripting"
        await mark_latest_training_candidate(db, task_id, "character", "approved")
    else:
        character.status = "rejected"
        record_feedback(db, task, "character", character.id, validated_feedback(body.feedback))
        task.status = "scripting"
        await mark_latest_training_candidate(db, task_id, "character", "negative")
    await db.commit()
    from src.tasks.video_tasks import run_video_task
    run_video_task.delay(str(task_id))
    return {"status": "queued"}


@router.get("/{task_id}/video-candidates", response_model=list[VideoCandidateResponse])
async def list_video_candidates(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user), media: MediaService = Depends(get_media_service)):
    await owned_task(db, user, task_id)
    candidates = (await db.scalars(select(VideoCandidate).where(VideoCandidate.task_id == task_id).order_by(VideoCandidate.kind, VideoCandidate.sort_order, VideoCandidate.version))).all()
    return [{"id": candidate.id, "task_id": candidate.task_id, "asset_id": candidate.asset_id, "access_url": await media.access_url(candidate.asset_id, user.id) if candidate.asset_id else None, "kind": candidate.kind, "sort_order": candidate.sort_order, "version": candidate.version, "status": candidate.status, "is_current": candidate.is_current, "generation_context": candidate.generation_context or {}} for candidate in candidates]


@router.get("/{task_id}/editing-blueprint", response_model=EditingBlueprintResponse)
async def get_editing_blueprint(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    await owned_task(db, user, task_id)
    blueprint = await db.scalar(select(EditingBlueprint).where(EditingBlueprint.task_id == task_id))
    if not blueprint:
        raise HTTPException(status_code=404, detail="Editing Blueprint not found")
    return blueprint


@router.put("/{task_id}/video-candidates/{candidate_id}")
async def review_video_candidate(task_id: UUID, candidate_id: UUID, body: CandidateReview, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    task = await owned_task(db, user, task_id)
    candidate = await db.scalar(select(VideoCandidate).where(VideoCandidate.id == candidate_id, VideoCandidate.task_id == task_id, VideoCandidate.is_current.is_(True)))
    if not candidate:
        raise HTTPException(status_code=404, detail="Current video candidate not found")
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="Unsupported video review action")
    candidate.status = "approved" if body.action == "approve" else "rejected"
    await mark_latest_training_candidate(db, task_id, "compositing" if candidate.kind == "composition" else "video_gen", "approved" if body.action == "approve" else "negative")
    if body.action == "reject":
        record_feedback(db, task, "composition" if candidate.kind == "composition" else "video_clip", candidate.id, validated_feedback(body.feedback))
    if candidate.kind == "composition" and body.action == "approve":
        task.status = "done"
        task.result_video_asset_id = candidate.asset_id
    elif candidate.kind == "clip" and body.action == "approve":
        remaining = await db.scalar(select(func.count(VideoCandidate.id)).where(VideoCandidate.task_id == task_id, VideoCandidate.kind == "clip", VideoCandidate.is_current.is_(True), VideoCandidate.status != "approved"))
        if remaining == 0:
            task.status = "compositing"
    await db.commit()
    if task.status == "compositing":
        from src.tasks.video_tasks import run_video_task
        run_video_task.delay(str(task_id))
    return {"status": "ok"}


@router.post("/{task_id}/video-candidates/{candidate_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_video_candidate(task_id: UUID, candidate_id: UUID, body: RegenerateRequest, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    task = await owned_task(db, user, task_id)
    candidate = await db.scalar(select(VideoCandidate).where(VideoCandidate.id == candidate_id, VideoCandidate.task_id == task_id, VideoCandidate.is_current.is_(True)))
    if not candidate:
        raise HTTPException(status_code=404, detail="Current video candidate not found")
    # Recomposition and clip regeneration are both a rejected review decision.
    # Recording the feedback before dispatching keeps the retry fully auditable.
    record_feedback(db, task, "composition" if candidate.kind == "composition" else "video_clip", candidate.id, validated_feedback(body.feedback))
    candidate.status = "rejected"
    candidate.is_current = False
    await mark_latest_training_candidate(db, task_id, "compositing" if candidate.kind == "composition" else "video_gen", "negative")
    task.status = "compositing" if candidate.kind == "composition" else "video_gen"
    await db.commit()
    from src.tasks.video_tasks import run_video_task
    run_video_task.delay(str(task_id))
    return {"status": "queued"}


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """Manually resume/start a task — dispatches the graph in background."""
    task = await owned_task(db, user, task_id)
    if task.status == "done":
        raise HTTPException(status_code=400, detail="Task already done")
    if task.status not in ("pending", "failed") and not is_stale_task(
        task.status, task.updated_at
    ):
        return {"status": "already_running", "task_status": task.status}
    # Allow retry from failed — resume from last completed step
    if task.status == "failed":
        task.error_message = None
        failed_step = (task.progress_log or [{}])[-1].get("step")
        retry_status = stage_for_node(failed_step)
        # Check what's already done
        script_result = await db.execute(select(Script).where(Script.task_id == task_id))
        script = script_result.scalar_one_or_none()
        img_result = await db.execute(select(GeneratedImage).where(GeneratedImage.task_id == task_id))
        images = img_result.scalars().all()

        if retry_status:
            task.status = retry_status
        elif images and any(img.status == "approved" for img in images):
            task.status = "image_review"  # Re-review what we have
        elif images and all(img.status in ("pending_review", "rejected") for img in images):
            task.status = "image_review"  # Re-review existing images
        elif script and script.status == "approved":
            task.status = "imaging"  # Script done, go to images
        elif script:
            task.status = "script_review"  # Re-review script
        else:
            task.status = "scripting"  # Start fresh
        await db.commit()
    else:
        task.status = "scripting"
        await db.commit()

    # Always enqueue resumable work in Celery so an API restart cannot lose it.
    from src.tasks.video_tasks import run_video_task
    celery_result = run_video_task.delay(str(task_id))
    task.celery_task_id = celery_result.id
    await db.commit()

    return {
        "status": "resumed",
        "task_status": task.status,
        "celery_task_id": celery_result.id,
    }


@router.get("/{task_id}/video")
async def download_video(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
    media: MediaService = Depends(get_media_service),
):
    result = await db.execute(select(VideoTask).where(VideoTask.id == task_id, VideoTask.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task or task.status not in ("done", "composition_review"):
        raise HTTPException(status_code=404, detail="Video not ready")
    if not task.result_video_asset_id:
        raise HTTPException(status_code=404, detail="Video not ready")
    return RedirectResponse(url=await media.access_url(task.result_video_asset_id,user.id))


@router.post("/viral/analyze", response_model=ViralAnalysisResponse, status_code=status.HTTP_200_OK)
async def analyze_viral_video_endpoint(
    product_id: UUID,
    video_url: str,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Lazy import: tools may not exist until Tasks 10-13 are implemented
    from src.tools.transcription import transcribe_audio
    from src.tools.llm_tools import analyze_video_structure

    transcription = await transcribe_audio(video_url)
    structure = await analyze_video_structure(transcription)
    return ViralAnalysisResponse(
        id=UUID("00000000-0000-0000-0000-000000000000"),
        task_id=None,
        source_url=video_url,
        original_script=transcription,
        script_structure=structure.get("script_structure"),
        shot_list=structure.get("shot_list", []),
        style_params=structure.get("style_params"),
    )
