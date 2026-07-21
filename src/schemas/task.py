from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class TaskCreate(BaseModel):
    product_id: UUID
    type: str
    image_count: int = 4
    viral_url: str | None = None
    script_overrides: dict | None = None
    style_overrides: dict | None = None
    stage_model_configuration_ids: dict[str, UUID] | None = None


class ScriptResponse(BaseModel):
    id: UUID
    task_id: UUID
    content: str
    edited_content: str | None
    image_prompts: list[str]
    voiceover_text: str | None
    status: str

    model_config = {"from_attributes": True}

class CreativeBriefResponse(BaseModel):
    id: UUID
    task_id: UUID
    content: dict
    status: str
    model_config = {"from_attributes": True}


class CreativeBriefUpdate(BaseModel):
    approved: bool
    content: dict | None = None
    feedback: str | None = None


class ShotPlanResponse(BaseModel):
    id: UUID
    task_id: UUID
    shots: list[dict]
    status: str

    model_config = {"from_attributes": True}


class ShotPlanUpdate(BaseModel):
    approved: bool
    shots: list[dict] | None = None
    feedback: str | None = None


class ScriptUpdate(BaseModel):
    approved: bool
    edited_content: str | None = None
    image_prompts: list[str] | None = None
    feedback: str | None = None


class ImageResponse(BaseModel):
    id: UUID
    task_id: UUID
    prompt: str
    image_url: str | None
    asset_id: UUID | None = None
    access_url: str | None = None
    sort_order: int
    status: str
    generation_context: dict = {}

    model_config = {"from_attributes": True}


class ImageReview(BaseModel):
    action: str
    feedback: str | None = None


class CandidateReview(BaseModel):
    action: str
    feedback: str | None = None


class RegenerateRequest(BaseModel):
    feedback: str
    model_configuration_id: UUID | None = None


class VideoCandidateResponse(BaseModel):
    id: UUID
    task_id: UUID
    asset_id: UUID | None = None
    access_url: str | None = None
    kind: str
    sort_order: int
    version: int
    status: str
    is_current: bool
    generation_context: dict = {}

    model_config = {"from_attributes": True}


class EditingBlueprintResponse(BaseModel):
    id: UUID
    task_id: UUID
    entries: list[dict]
    status: str
    model_config = {"from_attributes": True}


class ViralAnalysisResponse(BaseModel):
    id: UUID
    task_id: UUID | None
    source_url: str
    original_script: str | None
    script_structure: dict | None
    shot_list: list[dict]
    style_params: dict | None

    model_config = {"from_attributes": True}


class GenerationRecordResponse(BaseModel):
    id: UUID
    task_id: UUID
    stage: str
    substep: str
    attempt: int
    provider: str
    model: str
    parameters: dict
    normalized_input: dict
    normalized_output: dict
    provider_payload: dict
    media_asset_ids: list[str]
    provenance: dict
    model_resolution_snapshot: dict = {}
    training_candidate: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerationRecordExportRequest(BaseModel):
    record_ids: list[UUID]


class StageModelSelectionUpdate(BaseModel):
    model_configuration_id: UUID


class StageModelSelectionResponse(BaseModel):
    stage: str
    model_configuration_id: UUID
    selection_version: int
    resolution_snapshot: dict
    availability_status: str
    started_at: datetime | None

    model_config = {"from_attributes": True}


class TaskResponse(BaseModel):
    id: UUID
    product_id: UUID | None
    product_snapshot: dict
    type: str
    status: str
    current_step: str | None
    image_count: int
    error_message: str | None
    result_video_url: str | None
    result_video_asset_id: UUID | None = None
    progress_log: list[dict] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
