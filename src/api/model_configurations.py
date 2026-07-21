from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.deps import get_current_user
from src.database import get_async_session
from src.models.model_configuration import ModelConfiguration, ProviderModelCatalog, StageModelDefault, StageModelSelection
from src.models.user import User
from src.schemas.model_configuration import (
    ModelConfigurationCreate, ModelConfigurationResponse, ModelConfigurationUpdate,
    ProviderModelCatalogResponse, StageModelDefaultResponse, StageModelDefaultUpsert,
)
from src.services.model_catalog import ensure_provider_model_catalog
from src.services.model_credentials import encrypt_credential
from src.services.model_verification import SafeModelVerifier, is_selectable

router = APIRouter(tags=["Model configurations"])
MODEL_SELECTION_STAGES = frozenset({"creative_planning", "scriptwriting", "keyframe_image", "clip_video", "voice_generation", "viral_analysis"})


def configuration_response(configuration: ModelConfiguration) -> ModelConfigurationResponse:
    template = configuration.catalog_model
    model_id = configuration.model_id or (template.model_id if template else None)
    display_name = configuration.display_name or (template.display_name if template else None)
    capabilities = configuration.capabilities or (template.capabilities if template else [])
    constraints = configuration.constraints or (template.constraints if template else {})
    return ModelConfigurationResponse(
        id=configuration.id, catalog_model_id=configuration.catalog_model_id,
        adapter=configuration.adapter, api_base=configuration.api_base,
        provider=configuration.adapter, model_id=model_id, display_name=display_name,
        capabilities=list(capabilities), constraints=dict(constraints), revision=configuration.revision,
        uses_platform_default=configuration.uses_platform_default,
        verification_status=configuration.verification_status,
        verification_error=configuration.verification_error,
        first_use_eligible=is_selectable(configuration),
        verified_at=configuration.verified_at, revoked_at=configuration.revoked_at,
        created_at=configuration.created_at, updated_at=configuration.updated_at,
    )


async def list_provider_model_catalog(capability: str | None = None, db: AsyncSession = Depends(get_async_session)) -> list[ProviderModelCatalogResponse]:
    await ensure_provider_model_catalog(db)
    models = (await db.scalars(select(ProviderModelCatalog).where(ProviderModelCatalog.is_available.is_(True)).order_by(ProviderModelCatalog.provider, ProviderModelCatalog.model_id))).all()
    if capability:
        models = [model for model in models if capability in model.capabilities]
    return [ProviderModelCatalogResponse.model_validate(model) for model in models]


async def _catalog_model(db: AsyncSession, catalog_model_id: UUID) -> ProviderModelCatalog:
    catalog = await db.scalar(select(ProviderModelCatalog).where(ProviderModelCatalog.id == catalog_model_id))
    if catalog is None or not catalog.is_available:
        raise HTTPException(status_code=422, detail="Catalog model is not available")
    return catalog


async def create_model_configuration(body: ModelConfigurationCreate, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)) -> ModelConfigurationResponse:
    catalog = await _catalog_model(db, body.catalog_model_id) if body.catalog_model_id else None
    if body.use_platform_default:
        raise HTTPException(status_code=422, detail="Platform defaults are not supported")
    configuration = ModelConfiguration(
        owner_user_id=user.id, catalog_model_id=catalog.id if catalog else None,
        adapter=body.adapter or catalog.provider,
        api_base=body.api_base,
        model_id=body.model_id or catalog.model_id,
        display_name=body.display_name or catalog.display_name,
        capabilities=body.capabilities if body.capabilities is not None else list(catalog.capabilities),
        constraints=body.constraints if body.constraints is not None else dict(catalog.constraints),
        credential_ciphertext=encrypt_credential(body.credential),
        uses_platform_default=False,
    )
    db.add(configuration)
    await db.commit()
    loaded = await db.scalar(select(ModelConfiguration).options(selectinload(ModelConfiguration.catalog_model)).where(ModelConfiguration.id == configuration.id))
    return configuration_response(loaded)


async def list_model_configurations(db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)) -> list[ModelConfigurationResponse]:
    configurations = (await db.scalars(select(ModelConfiguration).options(selectinload(ModelConfiguration.catalog_model)).where(ModelConfiguration.owner_user_id == user.id).order_by(ModelConfiguration.created_at.desc()))).all()
    return [configuration_response(configuration) for configuration in configurations]


async def owned_configuration(db: AsyncSession, user: User, configuration_id: UUID) -> ModelConfiguration:
    configuration = await db.scalar(select(ModelConfiguration).options(selectinload(ModelConfiguration.catalog_model)).where(ModelConfiguration.id == configuration_id, ModelConfiguration.owner_user_id == user.id))
    if configuration is None:
        raise HTTPException(status_code=404, detail="Model configuration not found")
    return configuration


async def reloaded_configuration(db: AsyncSession, configuration_id: UUID) -> ModelConfiguration:
    return await db.scalar(select(ModelConfiguration).options(selectinload(ModelConfiguration.catalog_model)).where(
        ModelConfiguration.id == configuration_id,
    ))


async def update_model_configuration(configuration_id: UUID, body: ModelConfigurationUpdate, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)) -> ModelConfigurationResponse:
    configuration = await owned_configuration(db, user, configuration_id)
    if configuration.revoked_at:
        raise HTTPException(status_code=409, detail="Revoked model configurations cannot be updated")
    changed = False
    for field in ("display_name", "adapter", "api_base", "model_id", "capabilities", "constraints"):
        value = getattr(body, field)
        if value is not None and getattr(configuration, field) != value:
            setattr(configuration, field, value)
            changed = True
    if body.credential is not None:
        configuration.credential_ciphertext = encrypt_credential(body.credential)
        configuration.uses_platform_default = False
        changed = True
    if changed:
        configuration.revision += 1
        configuration.verification_status = "unverified"
        configuration.verification_error = None
        configuration.verified_at = None
    await db.commit()
    return configuration_response(await reloaded_configuration(db, configuration.id))


async def revoke_model_configuration(configuration_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)) -> ModelConfigurationResponse:
    configuration = await owned_configuration(db, user, configuration_id)
    configuration.credential_ciphertext = None
    configuration.verification_status = "revoked"
    configuration.verification_error = None
    configuration.revoked_at = datetime.now(timezone.utc)
    selections = (await db.scalars(select(StageModelSelection).where(
        StageModelSelection.model_configuration_id == configuration.id,
        StageModelSelection.started_at.is_(None),
    ))).all()
    for selection in selections:
        selection.availability_status = "replacement_required"
    await db.commit()
    return configuration_response(await reloaded_configuration(db, configuration.id))


async def verify_model_configuration(configuration_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user), verifier=None) -> ModelConfigurationResponse:
    """Perform only a provider-safe availability probe, never a generation."""
    configuration = await owned_configuration(db, user, configuration_id)
    if configuration.revoked_at:
        raise HTTPException(status_code=409, detail="Revoked model configurations cannot be verified")
    verifier = verifier or SafeModelVerifier()
    result = await verifier.verify_configuration(configuration)
    configuration.verification_status = "verified" if result.available else "unverified"
    configuration.verification_error = None if result.available else result.error
    configuration.verified_at = datetime.now(timezone.utc) if result.available else None
    await db.commit()
    return configuration_response(await reloaded_configuration(db, configuration.id))


async def set_stage_model_default(stage: str, body: StageModelDefaultUpsert, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)) -> StageModelDefaultResponse:
    if stage not in MODEL_SELECTION_STAGES:
        raise HTTPException(status_code=404, detail="Unknown model selection stage")
    configuration = await owned_configuration(db, user, body.model_configuration_id)
    if not is_selectable(configuration):
        raise HTTPException(status_code=422, detail="Only verified model configurations can be selected")
    if stage not in configuration.capabilities:
        raise HTTPException(status_code=422, detail="Model configuration is not compatible with this stage")
    default = await db.scalar(select(StageModelDefault).where(
        StageModelDefault.owner_user_id == user.id, StageModelDefault.stage == stage,
    ))
    if default is None:
        default = StageModelDefault(owner_user_id=user.id, stage=stage, model_configuration_id=configuration.id)
        db.add(default)
    else:
        default.model_configuration_id = configuration.id
    await db.commit()
    return StageModelDefaultResponse(stage=stage, model_configuration_id=configuration.id)


async def list_stage_model_defaults(db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)) -> list[StageModelDefaultResponse]:
    defaults = (await db.scalars(select(StageModelDefault).where(
        StageModelDefault.owner_user_id == user.id,
    ).order_by(StageModelDefault.stage))).all()
    return [StageModelDefaultResponse(stage=item.stage, model_configuration_id=item.model_configuration_id) for item in defaults]


async def delete_model_configuration(configuration_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)) -> Response:
    configuration = await owned_configuration(db, user, configuration_id)
    referenced = await db.scalar(select(StageModelDefault.id).where(StageModelDefault.model_configuration_id == configuration.id).limit(1))
    referenced = referenced or await db.scalar(select(StageModelSelection.id).where(StageModelSelection.model_configuration_id == configuration.id).limit(1))
    if referenced:
        raise HTTPException(status_code=409, detail="Referenced model configurations cannot be deleted")
    await db.delete(configuration)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/provider-model-catalog", response_model=list[ProviderModelCatalogResponse])
async def provider_model_catalog_route(capability: str | None = None, db: AsyncSession = Depends(get_async_session)):
    return await list_provider_model_catalog(capability, db)


@router.post("/model-configurations", response_model=ModelConfigurationResponse, status_code=status.HTTP_201_CREATED)
async def create_model_configuration_route(body: ModelConfigurationCreate, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await create_model_configuration(body, db, user)


@router.get("/model-configurations", response_model=list[ModelConfigurationResponse])
async def list_model_configurations_route(db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await list_model_configurations(db, user)


@router.patch("/model-configurations/{configuration_id}", response_model=ModelConfigurationResponse)
async def update_model_configuration_route(configuration_id: UUID, body: ModelConfigurationUpdate, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await update_model_configuration(configuration_id, body, db, user)


@router.post("/model-configurations/{configuration_id}/revoke", response_model=ModelConfigurationResponse)
async def revoke_model_configuration_route(configuration_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await revoke_model_configuration(configuration_id, db, user)


@router.post("/model-configurations/{configuration_id}/verify", response_model=ModelConfigurationResponse)
async def verify_model_configuration_route(configuration_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await verify_model_configuration(configuration_id, db, user)


@router.get("/stage-model-defaults", response_model=list[StageModelDefaultResponse])
async def list_stage_model_defaults_route(db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await list_stage_model_defaults(db, user)


@router.put("/stage-model-defaults/{stage}", response_model=StageModelDefaultResponse)
async def set_stage_model_default_route(stage: str, body: StageModelDefaultUpsert, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await set_stage_model_default(stage, body, db, user)


@router.delete("/model-configurations/{configuration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_configuration_route(configuration_id: UUID, db: AsyncSession = Depends(get_async_session), user: User = Depends(get_current_user)):
    return await delete_model_configuration(configuration_id, db, user)
