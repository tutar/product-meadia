"""Freeze compatible user defaults into a Video Task without copying secrets."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from fastapi import HTTPException

from src.models.model_configuration import ModelConfiguration, StageModelDefault, StageModelSelection
from src.models.task import VideoTask
from src.services.model_verification import is_selectable


TASK_STAGES = ("creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation")
VIRAL_ONLY_STAGES = ("viral_analysis",)


class ModelSelectionUnavailableError(ValueError):
    pass


def stages_for_task(task_type: str) -> tuple[str, ...]:
    return TASK_STAGES + (VIRAL_ONLY_STAGES if task_type == "viral" else ())


def configuration_details(configuration: ModelConfiguration) -> dict:
    """Resolve copied User fields, with catalog fallback for pre-release rows."""
    template = configuration.catalog_model
    return {
        "adapter": configuration.adapter or (template.provider if template else "openai"),
        "api_base": configuration.api_base,
        "model_id": configuration.model_id or (template.model_id if template else None),
        "capabilities": list(configuration.capabilities or (template.capabilities if template else [])),
        "constraints": dict(configuration.constraints or (template.constraints if template else {})),
        "configuration_revision": configuration.revision,
    }


def resolution_snapshot(configuration: ModelConfiguration, *, selection_version: int) -> dict:
    return {
        "configuration_id": str(configuration.id),
        **configuration_details(configuration),
        "selection_version": selection_version,
    }


async def freeze_stage_model_selections(
    db: AsyncSession, task: VideoTask, owner_user_id, *, overrides: dict[str, object] | None = None,
) -> list[StageModelSelection]:
    """Copy defaults once; later default edits have no path to mutate this task."""
    defaults = (await db.scalars(select(StageModelDefault).options(
        selectinload(StageModelDefault.model_configuration).selectinload(ModelConfiguration.catalog_model)
    ).where(
        StageModelDefault.owner_user_id == owner_user_id,
        StageModelDefault.stage.in_(stages_for_task(task.type)),
    ))).all()
    requested = overrides or {}
    available_stages = set(stages_for_task(task.type))
    unknown_stages = set(requested) - available_stages
    if unknown_stages:
        raise ModelSelectionUnavailableError(f"Unknown model selection stages: {', '.join(sorted(unknown_stages))}")
    defaults_by_stage = {item.stage: item for item in defaults}
    missing_stages = [stage for stage in stages_for_task(task.type) if stage not in requested and stage not in defaults_by_stage]
    if missing_stages:
        raise ModelSelectionUnavailableError(
            "A verified model selection is required for every task stage: "
            + ", ".join(missing_stages)
        )
    selections = []
    for stage in stages_for_task(task.type):
        if stage in requested:
            configuration = await db.scalar(select(ModelConfiguration).options(
                selectinload(ModelConfiguration.catalog_model)
            ).where(
                ModelConfiguration.id == requested[stage], ModelConfiguration.owner_user_id == owner_user_id,
            ))
            if configuration is None:
                raise ModelSelectionUnavailableError(f"Override for {stage} is not owned by this user")
        elif default := defaults_by_stage.get(stage):
            configuration = default.model_configuration
        else:  # guarded above; keep the invariant local to this loop.
            raise ModelSelectionUnavailableError(f"No model selection exists for {stage}")
        if not is_selectable(configuration):
            raise ModelSelectionUnavailableError(f"Selection for {stage} is not verified")
        if stage not in configuration_details(configuration)["capabilities"]:
            raise ModelSelectionUnavailableError(f"Selection for {stage} is not capability-compatible")
        selection = StageModelSelection(
            task_id=task.id, stage=stage, model_configuration_id=configuration.id,
            selection_version=1,
            resolution_snapshot={"configuration_id": str(configuration.id), "selection_version": 1, "state": "pending_resolution"},
            availability_status="available",
        )
        db.add(selection)
        selections.append(selection)
    await db.flush()
    return selections


async def resolve_stage_model_selection(db: AsyncSession, task_id, stage: str) -> StageModelSelection:
    """Atomically freeze one stage's non-sensitive invocation details at start."""
    selection = await db.scalar(select(StageModelSelection).options(
        selectinload(StageModelSelection.model_configuration).selectinload(ModelConfiguration.catalog_model)
    ).where(
        StageModelSelection.task_id == task_id, StageModelSelection.stage == stage,
    ).with_for_update())
    if selection is None:
        raise ModelSelectionUnavailableError(f"No model selection exists for {stage}")
    if selection.started_at is not None:
        return selection
    configuration = selection.model_configuration
    if configuration.revoked_at is not None or not is_selectable(configuration):
        selection.availability_status = "replacement_required"
        raise ModelSelectionUnavailableError(f"Selection for {stage} is not available")
    details = configuration_details(configuration)
    if stage not in details["capabilities"]:
        selection.availability_status = "replacement_required"
        raise ModelSelectionUnavailableError(f"Selection for {stage} is not capability-compatible")
    selection.resolution_snapshot = resolution_snapshot(configuration, selection_version=selection.selection_version)
    selection.started_at = datetime.now(timezone.utc)
    await db.flush()
    return selection


async def replace_stage_model_selection(
    db: AsyncSession, task: VideoTask, owner_user_id, stage: str, replacement_configuration_id,
    *, explicit_regeneration: bool = False,
) -> StageModelSelection:
    """Explicitly replace one unstarted stage; generated output is never reinterpreted."""
    if task.user_id != owner_user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    selection = await db.scalar(select(StageModelSelection).where(
        StageModelSelection.task_id == task.id, StageModelSelection.stage == stage,
    ))
    if selection is None:
        raise HTTPException(status_code=404, detail="Stage selection not found")
    if selection.started_at is not None and selection.availability_status == "available" and not explicit_regeneration:
        raise HTTPException(status_code=409, detail="Stage has already started; regenerate explicitly to replace its model")
    if explicit_regeneration and stage != "clip_video":
        raise HTTPException(status_code=422, detail="Only clip regeneration can replace a started model selection")
    configuration = await db.scalar(select(ModelConfiguration).options(selectinload(ModelConfiguration.catalog_model)).where(
        ModelConfiguration.id == replacement_configuration_id,
        ModelConfiguration.owner_user_id == owner_user_id,
    ))
    if configuration is None:
        raise HTTPException(status_code=404, detail="Model configuration not found")
    if not is_selectable(configuration):
        raise HTTPException(status_code=422, detail="Only verified model configurations can be selected")
    if stage not in configuration_details(configuration)["capabilities"]:
        raise HTTPException(status_code=422, detail="Model configuration is not compatible with this stage")
    selection.model_configuration_id = configuration.id
    selection.selection_version += 1
    selection.resolution_snapshot = {"configuration_id": str(configuration.id), "selection_version": selection.selection_version, "state": "pending_resolution"}
    selection.availability_status = "available"
    selection.started_at = None
    await db.flush()
    return selection
