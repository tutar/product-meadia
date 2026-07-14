from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID
from src.database import get_async_session
from src.models.user import User
from src.models.product import Product
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis
from src.schemas.task import (
    TaskCreate, TaskResponse, ScriptResponse, ScriptUpdate,
    ImageResponse, ImageReview, ViralAnalysisResponse,
)
from src.auth.deps import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    product_result = await db.execute(select(Product).where(Product.id == body.product_id))
    if not product_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if body.type == "viral" and not body.viral_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="viral_url required for viral type")

    task = VideoTask(
        product_id=body.product_id,
        type=body.type,
        image_count=body.image_count,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from src.tasks.video_tasks import run_video_task
    celery_result = run_video_task.delay(str(task.id))
    task.celery_task_id = celery_result.id
    await db.commit()
    await db.refresh(task)

    return task


@router.get("")
async def list_tasks(
    product_id: UUID | None = None,
    type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    query = select(VideoTask).options(selectinload(VideoTask.script), selectinload(VideoTask.images))
    if product_id:
        query = query.where(VideoTask.product_id == product_id)
    if type:
        query = query.where(VideoTask.type == type)
    if status:
        query = query.where(VideoTask.status == status)

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size).order_by(VideoTask.created_at.desc()))
    items = result.scalars().all()
    total_result = await db.execute(select(func.count(VideoTask.id)))
    return {"items": items, "total": total_result.scalar()}


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/script", response_model=ScriptResponse)
async def get_script(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Script).where(Script.task_id == task_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@router.put("/{task_id}/script", response_model=ScriptResponse)
async def update_script(
    task_id: UUID,
    body: ScriptUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Script).where(Script.task_id == task_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    if body.edited_content is not None:
        script.edited_content = body.edited_content
    if body.image_prompts is not None:
        script.image_prompts = body.image_prompts
    if body.approved:
        script.status = "approved"
        task_result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
        task = task_result.scalar_one()
        task.status = "imaging"
        await db.commit()
        await db.refresh(script)
        # Resume the graph
        from src.tasks.video_tasks import run_video_task
        run_video_task.delay(str(task_id))
    else:
        await db.commit()
        await db.refresh(script)
    return script


@router.get("/{task_id}/images", response_model=list[ImageResponse])
async def list_images(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GeneratedImage).where(GeneratedImage.task_id == task_id).order_by(GeneratedImage.sort_order)
    )
    return result.scalars().all()


@router.put("/{task_id}/images/{image_id}")
async def review_image(
    task_id: UUID,
    image_id: UUID,
    body: ImageReview,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.task_id == task_id)
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    img.status = "approved" if body.action == "approve" else "rejected"
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
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.task_id == task_id)
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    img.status = "pending_review"
    img.image_url = None
    await db.commit()
    return {"status": "queued"}


@router.get("/{task_id}/video")
async def download_video(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task or task.status != "done":
        raise HTTPException(status_code=404, detail="Video not ready")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=task.result_video_url)


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
