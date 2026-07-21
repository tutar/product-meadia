"""Persist non-sensitive model resolution provenance for task executions."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.generation_record import GenerationRecord
from src.models.model_configuration import StageModelSelection


async def persist_generation_record(
    db: AsyncSession, *, task_id: UUID, execution_stage: str, substep: str, attempt: int,
    provider: str, model: str, parameters: dict, normalized_input: dict,
    normalized_output: dict, provider_payload: dict,
) -> GenerationRecord:
    """Record an invocation using its frozen selection, never its credential."""
    selections = (await db.scalars(select(StageModelSelection).where(
        StageModelSelection.task_id == task_id,
    ))).all()
    selection = next((candidate for candidate in selections if (
        candidate.resolution_snapshot or {}
    ).get("model_id") == model), None)
    record = GenerationRecord(
        task_id=task_id, stage=execution_stage, substep=substep, attempt=attempt,
        provider=provider, model=model, parameters=parameters,
        normalized_input=normalized_input, normalized_output=normalized_output,
        provider_payload=provider_payload, provenance={},
        model_resolution_snapshot={
            **(dict(selection.resolution_snapshot) if selection else {}),
            "invocation_parameters": dict(parameters),
            "retry_count": max(0, attempt - 1),
        },
    )
    db.add(record)
    await db.flush()
    return record
