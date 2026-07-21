"""Freeze compatible user defaults into a Video Task without copying secrets."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from src.models.model_configuration import ModelConfiguration, StageModelDefault, StageModelSelection
from src.models.task import VideoTask


TASK_STAGES = ("creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation")
VIRAL_ONLY_STAGES = ("viral_analysis",)


class ModelSelectionUnavailableError(ValueError):
    pass


def stages_for_task(task_type: str) -> tuple[str, ...]:
    return TASK_STAGES + (VIRAL_ONLY_STAGES if task_type == "viral" else ())


def resolution_snapshot(configuration: ModelConfiguration) -> dict:
    catalog = configuration.catalog_model
    return {
        "configuration_id": str(configuration.id),
        "selection_version": 1,
        "provider": catalog.provider,
        "model_id": catalog.model_id,
        "capability_revision": catalog.capability_revision,
        "constraints": dict(catalog.constraints or {}),
        "uses_platform_default": configuration.uses_platform_default,
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
        if configuration.verification_status != "verified":
            raise ModelSelectionUnavailableError(f"Selection for {stage} is not verified")
        if stage not in configuration.catalog_model.capabilities:
            raise ModelSelectionUnavailableError(f"Selection for {stage} is not capability-compatible")
        selection = StageModelSelection(
            task_id=task.id, stage=stage, model_configuration_id=configuration.id,
            selection_version=1, resolution_snapshot=resolution_snapshot(configuration), availability_status="available",
        )
        db.add(selection)
        selections.append(selection)
    await db.flush()
    return selections


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
    if configuration.verification_status != "verified":
        raise HTTPException(status_code=422, detail="Only verified model configurations can be selected")
    if stage not in configuration.catalog_model.capabilities:
        raise HTTPException(status_code=422, detail="Model configuration is not compatible with this stage")
    selection.model_configuration_id = configuration.id
    selection.selection_version += 1
    selection.resolution_snapshot = {
        **resolution_snapshot(configuration), "selection_version": selection.selection_version,
    }
    selection.availability_status = "available"
    await db.flush()
    return selection
