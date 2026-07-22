from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
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
from src.models.voiceover_candidate import VoiceoverCandidate
from src.models.review_feedback import ReviewFeedback
from src.models.viral_analysis import ViralAnalysis
from src.models.media_asset import MediaAsset
from src.models.generation_record import GenerationRecord
from src.models.composition_source import CompositionSourceSnapshot
from src.models.model_configuration import StageModelSelection
from src.schemas.task import (
    TaskCreate, TaskResponse, ScriptResponse, ScriptUpdate, CreativeBriefResponse, CreativeBriefUpdate,
    ShotPlanResponse, ShotPlanUpdate, EditingBlueprintResponse, EditingBlueprintUpdate, ReviewRewindRequest,
    ImageResponse, ImageReview, CandidateReview, RegenerateRequest, VoiceoverReview, VideoCandidateResponse, ViralAnalysisResponse,
    GenerationRecordResponse, GenerationRecordExportRequest, CompositionSourceResponse, VoiceoverCandidateResponse,
    StageModelSelectionResponse, StageModelSelectionUpdate,
)
from src.auth.deps import get_current_user
from src.tasks.execution import feedback_stage, stage_for_node
from src.tasks.recovery import is_stale_task
from src.services.product_context import build_product_snapshot
from src.api.media import get_media_service
from src.services.media_service import MediaService
from src.services.composition_sources import materialize_html, html_checksum
from src.tools.render import render_hyperframes
from src.services.stage_model_selections import ModelSelectionUnavailableError, freeze_stage_model_selections
from src.services.stage_model_selections import replace_stage_model_selection

router = APIRouter(prefix="/tasks", tags=["tasks"])
ACTIVE_TASK_STATUSES = ("pending", "planning", "creative_brief_review", "shot_plan_review", "scripting", "script_review", "imaging", "image_review", "character_review", "video_gen", "video_review", "voice_review", "editing_blueprint_review", "compositing", "composition_review", "cancellation_requested")
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
        voiceover_review_enabled=True,
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
    attempt: int | None = None,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await owned_task(db, user, task_id)
    query = select(GenerationRecord).where(GenerationRecord.task_id == task_id)
    if stage:
        query = query.where(GenerationRecord.stage == stage)
    if attempt is not None:
        query = query.where(GenerationRecord.attempt == attempt)
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


@router.get("/{task_id}/video-candidates/{candidate_id}/composition-source", response_model=CompositionSourceResponse)
async def get_composition_source(
    task_id: UUID,
    candidate_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    await owned_task(db, user, task_id)
    snapshot = await db.scalar(select(CompositionSourceSnapshot).where(
        CompositionSourceSnapshot.task_id == task_id,
        CompositionSourceSnapshot.candidate_id == candidate_id,
    ))
    if not snapshot:
        raise HTTPException(status_code=404, detail="Composition source snapshot not found")
    return CompositionSourceResponse(
        id=snapshot.id,
        task_id=snapshot.task_id,
        candidate_id=snapshot.candidate_id,
        asset_id=snapshot.asset_id,
        source_kind=snapshot.source_kind,
        canonical_html_checksum=snapshot.canonical_html_checksum,
        input_asset_ids=[str(asset_id) for asset_id in snapshot.input_asset_ids],
        render_spec=snapshot.render_spec,
        provenance=snapshot.provenance,
        reconstruction_notes=snapshot.reconstruction_notes,
    )


async def _owned_composition_source(db: AsyncSession, user: User, task_id: UUID, candidate_id: UUID) -> CompositionSourceSnapshot:
    await owned_task(db, user, task_id)
    snapshot = await db.scalar(select(CompositionSourceSnapshot).where(
        CompositionSourceSnapshot.task_id == task_id,
        CompositionSourceSnapshot.candidate_id == candidate_id,
    ))
    if not snapshot or not snapshot.asset_id:
        raise HTTPException(status_code=404, detail="Composition source snapshot not found")
    return snapshot


@router.get("/{task_id}/video-candidates/{candidate_id}/composition-source/download")
async def download_composition_source(
    task_id: UUID,
    candidate_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
    media: MediaService = Depends(get_media_service),
):
    snapshot = await _owned_composition_source(db, user, task_id, candidate_id)
    asset = await media.get_owned_asset(snapshot.asset_id, user.id)
    html = await media.storage.download(asset.bucket, asset.object_key)
    return Response(
        content=html,
        media_type=asset.content_type or "text/html; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="composition-source.html"'},
    )


@router.get("/{task_id}/video-candidates/{candidate_id}/composition-source/preview", response_class=HTMLResponse)
async def preview_composition_source(
    task_id: UUID,
    candidate_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
    media: MediaService = Depends(get_media_service),
):
    snapshot = await _owned_composition_source(db, user, task_id, candidate_id)
    asset = await media.get_owned_asset(snapshot.asset_id, user.id)
    canonical_html = (await media.storage.download(asset.bucket, asset.object_key)).decode("utf-8")
    html = await materialize_html(canonical_html, media, user.id)
    return HTMLResponse(html, headers={
        "Content-Security-Policy": "default-src 'self' https: http: data:; script-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/{task_id}/video-candidates/{candidate_id}/composition-source/replay", response_model=VideoCandidateResponse)
async def replay_composition_source(
    task_id: UUID,
    candidate_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
    media: MediaService = Depends(get_media_service),
):
    """Render a source snapshot into a new candidate without mutating its source."""
    snapshot = await _owned_composition_source(db, user, task_id, candidate_id)
    task = await owned_task(db, user, task_id)
    asset = await media.get_owned_asset(snapshot.asset_id, user.id)
    canonical_html = (await media.storage.download(asset.bucket, asset.object_key)).decode("utf-8")
    path = await render_hyperframes(await materialize_html(canonical_html, media, user.id))
    candidates = (await db.scalars(select(VideoCandidate).where(
        VideoCandidate.task_id == task_id, VideoCandidate.kind == "composition"
    ))).all()
    next_version = max((item.version for item in candidates), default=0) + 1
    output_asset = await media.create_asset(
        owner_user_id=user.id,
        category="final_video",
        data=Path(path).read_bytes(),
        content_type="video/mp4",
        filename=f"{task_id}-final-replay.mp4",
        task_id=task.id,
        source_provider="hyperframes-replay",
        idempotency_key=f"task:{task_id}:final-video:replay:{next_version}",
    )
    for prior in candidates:
        if prior.is_current:
            prior.is_current = False
    replay = VideoCandidate(
        task_id=task.id,
        asset_id=output_asset.id,
        kind="composition",
        sort_order=0,
        version=next_version,
        status="pending_review",
        recomposed_from_candidate_id=candidate_id,
    )
    db.add(replay)
    await db.flush()
    db.add(CompositionSourceSnapshot(
        task_id=task.id,
        candidate_id=replay.id,
        asset_id=snapshot.asset_id,
        source_kind=snapshot.source_kind,
        canonical_html_checksum=snapshot.canonical_html_checksum,
        input_asset_ids=snapshot.input_asset_ids,
        render_spec=snapshot.render_spec,
        provenance={**snapshot.provenance, "recomposed_from_candidate_id": str(candidate_id)},
        reconstruction_notes=snapshot.reconstruction_notes,
    ))
    task.result_video_asset_id = output_asset.id
    task.result_video_url = None
    task.status = "composition_review"
    await db.commit()
    return VideoCandidateResponse.model_validate(replay)


@router.post("/{task_id}/video-candidates/{candidate_id}/composition-source/reconstruct", response_model=CompositionSourceResponse)
async def reconstruct_composition_source(
    task_id: UUID, candidate_id: UUID, db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user), media: MediaService = Depends(get_media_service),
):
    """Create an explicitly inferred source for a legacy candidate with no capture."""
    task = await owned_task(db, user, task_id)
    if await db.scalar(select(CompositionSourceSnapshot).where(CompositionSourceSnapshot.candidate_id == candidate_id)):
        raise HTTPException(status_code=409, detail="Composition source snapshot already exists")
    blueprint = await db.scalar(select(EditingBlueprint).where(EditingBlueprint.task_id == task_id))
    clips = (await db.scalars(select(VideoCandidate).where(VideoCandidate.task_id == task_id, VideoCandidate.kind == "clip", VideoCandidate.is_current.is_(True), VideoCandidate.asset_id.is_not(None)).order_by(VideoCandidate.sort_order))).all()
    audio = await db.scalar(select(MediaAsset).where(MediaAsset.task_id == task_id, MediaAsset.category == "tts_audio", MediaAsset.status == "available").order_by(MediaAsset.created_at.desc()))
    if not blueprint or not clips or not audio:
        raise HTTPException(status_code=422, detail="Insufficient retained inputs to reconstruct composition source")
    entries = blueprint.entries
    if len(entries) != len(clips):
        raise HTTPException(status_code=422, detail="Editing Blueprint no longer matches retained clip candidates")
    duration = sum(float(entry.get("duration_seconds", 0)) for entry in entries)
    videos = "".join(f'<video id="clip-{index}" src="asset://{clip.asset_id}" data-start="{entry["start_seconds"]}" data-duration="{entry["duration_seconds"]}" data-track-index="0" muted playsinline></video>' for index, (clip, entry) in enumerate(zip(clips, entries)))
    canonical_html = f'<div data-composition-id="reconstructed-{candidate_id}" data-duration="{duration}" data-width="1152" data-height="768"><audio id="voiceover" src="asset://{audio.id}" data-start="0" data-track-index="10"></audio>{videos}</div>'
    asset = await media.create_asset(owner_user_id=user.id, category="composition_source", data=canonical_html.encode(), content_type="text/html; charset=utf-8", filename=f"{task_id}-reconstructed-source.html", task_id=task.id, source_provider="composition-reconstruction", idempotency_key=f"candidate:{candidate_id}:reconstructed-source")
    snapshot = CompositionSourceSnapshot(task_id=task.id, candidate_id=candidate_id, asset_id=asset.id, source_kind="reconstructed", canonical_html_checksum=html_checksum(canonical_html), input_asset_ids=[*[str(clip.asset_id) for clip in clips], str(audio.id)], render_spec={"width": 1152, "height": 768}, provenance={"source_candidate_id": str(candidate_id), "editing_blueprint_id": str(blueprint.id), "input_selection": "current_candidates"}, reconstruction_notes="Reconstructed after the original HTML was unavailable; uses current retained clip candidates and latest retained voiceover.")
    db.add(snapshot)
    await db.commit()
    return CompositionSourceResponse(id=snapshot.id, task_id=snapshot.task_id, candidate_id=snapshot.candidate_id, asset_id=snapshot.asset_id, source_kind=snapshot.source_kind, canonical_html_checksum=snapshot.canonical_html_checksum, input_asset_ids=snapshot.input_asset_ids, render_spec=snapshot.render_spec, provenance=snapshot.provenance, reconstruction_notes=snapshot.reconstruction_notes)


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
    source_candidate_ids = set((await db.scalars(select(CompositionSourceSnapshot.candidate_id).where(
        CompositionSourceSnapshot.task_id == task_id,
        CompositionSourceSnapshot.candidate_id.is_not(None),
    ))).all())
    return [{"id": candidate.id, "task_id": candidate.task_id, "asset_id": candidate.asset_id, "access_url": await media.access_url(candidate.asset_id, user.id) if candidate.asset_id else None, "kind": candidate.kind, "sort_order": candidate.sort_order, "version": candidate.version, "status": candidate.status, "is_current": candidate.is_current, "has_composition_source": candidate.id in source_candidate_ids, "generation_context": candidate.generation_context or {}} for candidate in candidates]


@router.get("/{task_id}/voiceover-candidates", response_model=list[VoiceoverCandidateResponse])
async def list_voiceover_candidates(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user), media: MediaService = Depends(get_media_service)):
    await owned_task(db, user, task_id)
    candidates = (await db.scalars(select(VoiceoverCandidate).where(
        VoiceoverCandidate.task_id == task_id,
    ).order_by(VoiceoverCandidate.version))).all()
    return [{"id": candidate.id, "task_id": candidate.task_id, "asset_id": candidate.asset_id, "access_url": await media.access_url(candidate.asset_id, user.id) if candidate.asset_id else None, "narration_text": candidate.narration_text, "duration_seconds": candidate.duration_seconds, "version": candidate.version, "status": candidate.status, "is_current": candidate.is_current, "generation_context": candidate.generation_context or {}} for candidate in candidates]


@router.get("/{task_id}/editing-blueprint", response_model=EditingBlueprintResponse)
async def get_editing_blueprint(task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    await owned_task(db, user, task_id)
    blueprint = await db.scalar(select(EditingBlueprint).where(EditingBlueprint.task_id == task_id))
    if not blueprint:
        raise HTTPException(status_code=404, detail="Editing Blueprint not found")
    return blueprint


def _blueprint_duration(entries: list[dict]) -> float:
    return sum(float(entry.get("duration_seconds", 0)) for entry in entries)


async def _render_saved_blueprint(
    db: AsyncSession, media: MediaService, task: VideoTask, blueprint: EditingBlueprint,
) -> VideoCandidate:
    """Render the user-saved deterministic blueprint with retained inputs only."""
    clips = (await db.scalars(select(VideoCandidate).where(
        VideoCandidate.task_id == task.id, VideoCandidate.kind == "clip",
        VideoCandidate.is_current.is_(True), VideoCandidate.asset_id.is_not(None),
    ).order_by(VideoCandidate.sort_order))).all()
    voice = await db.scalar(select(VoiceoverCandidate).where(
        VoiceoverCandidate.task_id == task.id, VoiceoverCandidate.is_current.is_(True),
        VoiceoverCandidate.status == "approved", VoiceoverCandidate.asset_id.is_not(None),
    ))
    entries = blueprint.entries or []
    if not clips or not voice or len(entries) != len(clips):
        raise HTTPException(status_code=422, detail="Editing Blueprint does not match approved retained inputs")
    for index, entry in enumerate(entries):
        if int(entry.get("clip_index", index)) != index or float(entry.get("duration_seconds", 0)) <= 0:
            raise HTTPException(status_code=422, detail="Editing Blueprint contains invalid clip timing")
    duration = _blueprint_duration(entries)
    videos = "".join(
        f'<video id="clip-{index}" class="clip" src="asset://{clip.asset_id}" data-start="{entry.get("start_seconds", 0)}" data-duration="{entry["duration_seconds"]}" data-track-index="0" muted playsinline preload="auto"></video>'
        for index, (clip, entry) in enumerate(zip(clips, entries))
    )
    canonical_html = (
        f'<div data-composition-id="task-{task.id}" data-start="0" data-duration="{duration}" data-width="1152" data-height="768">'
        f'<audio id="voiceover" src="asset://{voice.asset_id}" data-start="0" data-track-index="10"></audio>{videos}</div>'
    )
    source_asset = await media.create_asset(
        owner_user_id=task.user_id, category="composition_source", data=canonical_html.encode(),
        content_type="text/html; charset=utf-8", filename=f"{task.id}-composition-source.html",
        task_id=task.id, source_provider="editing-blueprint",
        idempotency_key=f"task:{task.id}:editing-blueprint:{blueprint.updated_at.isoformat()}",
    )
    path = await render_hyperframes(await materialize_html(canonical_html, media, task.user_id))
    prior = (await db.scalars(select(VideoCandidate).where(
        VideoCandidate.task_id == task.id, VideoCandidate.kind == "composition",
    ))).all()
    next_version = max((candidate.version for candidate in prior), default=0) + 1
    final_asset = await media.create_asset(
        owner_user_id=task.user_id, category="final_video", data=Path(path).read_bytes(),
        content_type="video/mp4", filename=f"{task.id}-final-blueprint.mp4", task_id=task.id,
        source_provider="hyperframes", idempotency_key=f"task:{task.id}:final-video:blueprint:{next_version}",
    )
    for candidate in prior:
        if candidate.is_current:
            candidate.is_current = False
    candidate = VideoCandidate(task_id=task.id, asset_id=final_asset.id, kind="composition", sort_order=0,
                               version=next_version, status="pending_review")
    db.add(candidate)
    await db.flush()
    db.add(CompositionSourceSnapshot(
        task_id=task.id, candidate_id=candidate.id, asset_id=source_asset.id, source_kind="captured",
        canonical_html_checksum=html_checksum(canonical_html),
        input_asset_ids=[str(clip.asset_id) for clip in clips] + [str(voice.asset_id)],
        render_spec={"fps": 30, "width": 1152, "height": 768, "format": "mp4"},
        provenance={"editing_blueprint": True},
    ))
    task.result_video_asset_id = final_asset.id
    task.result_video_url = None
    task.status = "composition_review"
    return candidate


@router.put("/{task_id}/editing-blueprint/recompose")
async def save_and_recompose_editing_blueprint(
    task_id: UUID, body: EditingBlueprintUpdate, db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user), media: MediaService = Depends(get_media_service),
):
    task = await owned_task(db, user, task_id)
    if not task.voiceover_review_enabled or task.status != "composition_review":
        raise HTTPException(status_code=409, detail="Editing Blueprint recomposition is only available during new-flow composition review")
    blueprint = await db.scalar(select(EditingBlueprint).where(EditingBlueprint.task_id == task_id))
    if not blueprint:
        raise HTTPException(status_code=404, detail="Editing Blueprint not found")
    if body.entries == blueprint.entries:
        raise HTTPException(status_code=422, detail="Save a changed Editing Blueprint before re-rendering")
    duration_changed = _blueprint_duration(body.entries) != _blueprint_duration(blueprint.entries)
    blueprint.entries = body.entries
    if duration_changed:
        blueprint.status = "pending_review"
        task.status = "editing_blueprint_review"
        await db.commit()
        return {"status": "editing_blueprint_review"}
    candidate = await _render_saved_blueprint(db, media, task, blueprint)
    await db.commit()
    return candidate


@router.post("/{task_id}/editing-blueprint/approve", response_model=VideoCandidateResponse)
async def approve_duration_changed_editing_blueprint(
    task_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user),
    media: MediaService = Depends(get_media_service),
):
    task = await owned_task(db, user, task_id)
    blueprint = await db.scalar(select(EditingBlueprint).where(EditingBlueprint.task_id == task_id))
    if task.status != "editing_blueprint_review" or not blueprint or blueprint.status != "pending_review":
        raise HTTPException(status_code=409, detail="No duration-changing Editing Blueprint awaits approval")
    blueprint.status = "approved"
    candidate = await _render_saved_blueprint(db, media, task, blueprint)
    await db.commit()
    return candidate


@router.post("/{task_id}/composition-review/rewind", status_code=status.HTTP_202_ACCEPTED)
async def rewind_composition_review(
    task_id: UUID, body: ReviewRewindRequest, db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """Return explicitly to voice or selected Clip Segment review without invoking a model."""
    task = await owned_task(db, user, task_id)
    if not task.voiceover_review_enabled or task.status != "composition_review":
        raise HTTPException(status_code=409, detail="Composition review rewind is unavailable for this task")
    composition = await db.scalar(select(VideoCandidate).where(
        VideoCandidate.task_id == task_id, VideoCandidate.kind == "composition", VideoCandidate.is_current.is_(True),
    ))
    if composition:
        composition.status = "rejected"
        composition.is_current = False
    if body.target == "voiceover":
        voice = await db.scalar(select(VoiceoverCandidate).where(
            VoiceoverCandidate.task_id == task_id, VoiceoverCandidate.is_current.is_(True),
        ))
        if not voice:
            raise HTTPException(status_code=409, detail="No current Voiceover Candidate")
        voice.status = "pending_review"
        task.status = "voice_review"
    elif body.target == "clips":
        if not body.clip_candidate_ids:
            raise HTTPException(status_code=422, detail="Select at least one Clip Segment")
        clips = (await db.scalars(select(VideoCandidate).where(
            VideoCandidate.task_id == task_id, VideoCandidate.id.in_(body.clip_candidate_ids),
            VideoCandidate.kind == "clip", VideoCandidate.is_current.is_(True),
        ))).all()
        if len(clips) != len(set(body.clip_candidate_ids)):
            raise HTTPException(status_code=422, detail="Selected Clip Segments are not current task candidates")
        for clip in clips:
            clip.status = "pending_review"
        task.status = "video_review"
    else:
        raise HTTPException(status_code=422, detail="Unsupported review rewind target")
    await db.commit()
    return {"status": "queued"}


@router.put("/{task_id}/voiceover-candidates/{candidate_id}", status_code=status.HTTP_202_ACCEPTED)
async def review_voiceover_candidate(
    task_id: UUID, candidate_id: UUID, body: VoiceoverReview,
    db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user),
):
    """Approve a Voiceover Candidate or create a replacement through TTS only."""
    task = await owned_task(db, user, task_id)
    candidate = await db.scalar(select(VoiceoverCandidate).where(
        VoiceoverCandidate.id == candidate_id, VoiceoverCandidate.task_id == task_id,
        VoiceoverCandidate.is_current.is_(True),
    ))
    if not candidate:
        raise HTTPException(status_code=404, detail="Current voiceover candidate not found")
    if body.action == "approve":
        candidate.status = "approved"
        task.status = "video_gen" if task.type == "personify" else "compositing"
        await db.commit()
        from src.tasks.video_tasks import run_video_task
        run_video_task.delay(str(task_id))
        return {"status": "queued"}
    if body.action != "regenerate":
        raise HTTPException(status_code=422, detail="Unsupported voiceover review action")
    changed_text = (body.narration_text or "").strip()
    if changed_text == candidate.narration_text:
        changed_text = ""
    if not changed_text and body.model_configuration_id is None:
        raise HTTPException(status_code=422, detail="Voiceover replacement requires changed narration text or a voice model configuration")
    selection = await db.scalar(select(StageModelSelection).where(
        StageModelSelection.task_id == task.id, StageModelSelection.stage == "voice_generation",
    ))
    if selection is None:
        raise HTTPException(status_code=409, detail="Voiceover regeneration has no model selection")
    await replace_stage_model_selection(
        db, task, user.id, "voice_generation", body.model_configuration_id or selection.model_configuration_id,
        explicit_regeneration=True,
    )
    if changed_text:
        script = await db.scalar(select(Script).where(Script.task_id == task_id))
        if script:
            script.voiceover_text = changed_text
    candidate.status = "rejected"
    candidate.is_current = False
    record_feedback(db, task, "voiceover", candidate.id, body.feedback or "User requested a replacement voiceover.")
    task.status = "video_gen"
    await db.commit()
    from src.tasks.video_tasks import run_video_task
    run_video_task.delay(str(task_id))
    return {"status": "queued"}


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
    if candidate.kind == "clip":
        # A User-requested regeneration deliberately begins a new selection
        # version.  Omitting a replacement keeps the same configuration
        # reference, but resolves its latest verified revision at stage start.
        selection = await db.scalar(select(StageModelSelection).where(
            StageModelSelection.task_id == task.id, StageModelSelection.stage == "clip_video",
        ))
        if selection is None:
            raise HTTPException(status_code=409, detail="Clip regeneration has no model selection")
        await replace_stage_model_selection(
            db, task, user.id, "clip_video", body.model_configuration_id or selection.model_configuration_id,
            explicit_regeneration=True,
        )
    elif body.model_configuration_id is not None:
        raise HTTPException(status_code=422, detail="Composition regeneration cannot replace a model selection")
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
