from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, get_optional_user, require_author
from app.domain.models import User, GenerationTaskType
from app.infra.db import get_session as get_db_session_session
from app.schemas.characters import (
    CharacterPresetCreate,
    CharacterPresetUpdate,
    CharacterPresetRead,
    CharacterPresetList,
    SceneCharacterCreate,
    SceneCharacterUpdate,
    SceneCharacterRead,
    GenerateWithCharactersRequest,
    CharacterRenderRequest,
    SDPromptResponse,
)
from app.schemas.generation_overrides import GenerationOverrides
from app.schemas.generation_job import AssetGenerationJobCreate, GenerationJobRead
from app.services.generation_job import GenerationJobService
from app.services.character import CharacterService
from app.services.asset_uploads import read_uploaded_image
from fastapi import BackgroundTasks
from app.domain.models import GenerationJob
from app.core.deps import get_current_user
from uuid import uuid4
import logging
logger = logging.getLogger(__name__)
from app.api.deps import get_db_session

router = APIRouter(prefix="/characters", tags=["characters"])


@router.post("/presets", response_model=CharacterPresetRead, status_code=status.HTTP_201_CREATED)
async def create_character_preset(
    data: CharacterPresetCreate,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Создать пресет персонажа (только для авторов)."""
    service = CharacterService(db)
    preset = await service.create_preset(data, current_user.id)
    return preset


@router.get("/presets", response_model=CharacterPresetList)
async def list_character_presets(
    only_mine: bool = Query(False, description="Только мои пресеты"),
    only_public: bool = Query(False, description="Только публичные пресеты"),
    character_type: Optional[str] = Query(None, description="Фильтр по типу персонажа"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db_session_session),
):
    """
    Получить список пресетов персонажей.
    - Без авторизации: только публичные
    - С авторизацией: свои + публичные (или фильтры)
    """
    service = CharacterService(db)
    user_id = current_user.id if current_user else None
    
    presets, total = await service.list_presets(
        user_id=user_id,
        only_mine=only_mine,
        only_public=only_public,
        character_type=character_type,
        page=page,
        page_size=page_size,
        project_id=None,
    )
    
    return CharacterPresetList(
        items=[CharacterPresetRead.model_validate(preset) for preset in presets],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/presets/{preset_id}", response_model=CharacterPresetRead)
async def get_character_preset(
    preset_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Получить пресет персонажа по ID."""
    service = CharacterService(db)
    user_id = current_user.id if current_user else None
    preset = await service.get_preset(preset_id, user_id)
    return preset


@router.put("/presets/{preset_id}", response_model=CharacterPresetRead)
async def update_character_preset(
    preset_id: str,
    data: CharacterPresetUpdate,
    unsafe: bool = Query(False, description="Allow overwriting imported presets"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Обновить пресет персонажа (только автор)."""
    service = CharacterService(db)
    preset = await service.update_preset(preset_id, data, current_user.id, unsafe=unsafe)
    return preset


@router.post(
    "/presets/{preset_id}/sketch",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_character_sketch(
    preset_id: str,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Enqueue character sketch generation."""
    service = GenerationJobService(db)
    payload = AssetGenerationJobCreate(
        task_type=GenerationTaskType.CHARACTER_SKETCH,
        entity_type="character",
        entity_id=preset_id,
    )
    job = await service.create_asset_job(payload, user_id=current_user.id)
    return job


@router.post(
    "/presets/{preset_id}/sheet",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_character_sheet(
    preset_id: str,
    overrides: Optional[GenerationOverrides] = Body(None),
    project_id: Optional[str] = Query(None, description="Project id to reuse its style profile defaults"),
    style_profile_id: Optional[str] = Query(None, description="Explicit style profile id to use"),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Generate and store a character reference sheet (multi-view)."""
    gen = GenerationJobService(db)
    return await gen.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.CHARACTER_SHEET,
            entity_type="character",
            entity_id=preset_id,
            project_id=project_id,
            style_profile_id=style_profile_id,
            overrides=overrides,
        ),
        user_id=current_user.id,
    )


@router.post(
    "/presets/{preset_id}/references/{kind}",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_character_reference(
    preset_id: str,
    kind: str,
    overrides: Optional[GenerationOverrides] = Body(None),
    project_id: Optional[str] = Query(None, description="Project id to reuse its style profile defaults"),
    style_profile_id: Optional[str] = Query(None, description="Explicit style profile id to use"),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Regenerate a single reference image slot for a character preset."""
    gen = GenerationJobService(db)
    return await gen.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.CHARACTER_REFERENCE,
            entity_type="character",
            entity_id=preset_id,
            project_id=project_id,
            style_profile_id=style_profile_id,
            kind=kind,
            overrides=overrides,
        ),
        user_id=current_user.id,
    )


@router.post("/presets/{preset_id}/references/{kind}/upload", response_model=CharacterPresetRead)
async def upload_character_reference(
    preset_id: str,
    kind: str,
    file: UploadFile = File(...),
    set_as_preview: bool = Form(True),
    unsafe: bool = Query(False, description="Allow overwriting imported presets"),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    image_bytes, filename = await read_uploaded_image(file)
    service = CharacterService(db)
    preset = await service.upload_reference_image(
        preset_id,
        kind,
        user_id=current_user.id,
        image_bytes=image_bytes,
        filename=filename,
        unsafe=unsafe,
        set_as_preview=set_as_preview,
    )
    return preset


@router.post(
    "/presets/{preset_id}/render",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def render_character_representation(
    preset_id: str,
    payload: CharacterRenderRequest,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Enqueue canonical/variant character representations generation."""
    gen = GenerationJobService(db)
    return await gen.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.CHARACTER_RENDER,
            entity_type="character",
            entity_id=preset_id,
            payload=payload.model_dump(exclude_none=True),
        ),
        user_id=current_user.id,
    )


@router.post(
    "/presets/{preset_id}/multiview",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_character_multiview(
    preset_id: str,
    overrides: Optional[GenerationOverrides] = Body(None),
    project_id: Optional[str] = Query(None, description="Project id to reuse its style profile defaults"),
    style_profile_id: Optional[str] = Query(None, description="Explicit style profile id to use"),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """
    Generate multi-view character images using sequential img2img processing.
    
    Process:
    1. Generate initial character image (txt2img) 
    2. Generate multiple views sequentially (img2img) with view-specific prompts
    3. Preserve character identity and consistency across all views
    
    Views generated: front_view, side_profile, three_quarter, back_view, close_up
    """
    gen = GenerationJobService(db)
    return await gen.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.CHARACTER_MULTIVIEW,
            entity_type="character",
            entity_id=preset_id,
            project_id=project_id,
            style_profile_id=style_profile_id,
            overrides=overrides,
        ),
        user_id=current_user.id,
    )


@router.post(
    "/presets/{preset_id}/multiview",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_character_multiview(
    preset_id: str,
    overrides: Optional[GenerationOverrides] = Body(None),
    project_id: Optional[str] = Query(None, description="Project id to reuse its style profile defaults"),
    style_profile_id: Optional[str] = Query(None, description="Explicit style profile id to use"),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """
    Generate multi-view character images using sequential img2img processing.
    
    Process:
    1. Generate initial character image (txt2img) 
    2. Generate multiple views sequentially (img2img) with view-specific prompts
    3. Preserve character identity and consistency across all views
    
    Views generated: front_view, side_profile, three_quarter, back_view, close_up
    """
    gen = GenerationJobService(db)
    return await gen.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.CHARACTER_MULTIVIEW,
            entity_type="character",
            entity_id=preset_id,
            project_id=project_id,
            style_profile_id=style_profile_id,
            overrides=overrides,
        ),
        user_id=current_user.id,
    )


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character_preset(
    preset_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Удалить пресет персонажа (только автор)."""
    service = CharacterService(db)
    await service.delete_preset(preset_id, current_user.id)


@router.get("/projects/{project_id}/characters", response_model=CharacterPresetList)
async def list_project_characters(
    project_id: str,
    db: AsyncSession = Depends(get_db_session_session),
):
    service = CharacterService(db)
    presets, total = await service.list_presets(project_id=project_id, page=1, page_size=500)
    return CharacterPresetList(items=presets, total=total, page=1, page_size=500)


@router.post("/projects/{project_id}/characters/import", response_model=CharacterPresetRead, status_code=status.HTTP_201_CREATED)
async def import_character_preset(
    project_id: str,
    preset_id: str = Query(..., description="Studio preset id"),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    service = CharacterService(db)
    preset = await service.import_preset(project_id, preset_id, current_user.id)
    return preset


# Scene Characters endpoints

@router.post("/scenes/{scene_id}/characters", response_model=SceneCharacterRead, status_code=status.HTTP_201_CREATED)
async def add_character_to_scene(
    scene_id: str,
    data: SceneCharacterCreate,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Добавить персонажа к сцене (только для авторов)."""
    service = CharacterService(db)
    scene_char = await service.add_character_to_scene(scene_id, data, current_user.id)
    return scene_char


@router.get("/scenes/{scene_id}/characters", response_model=list[SceneCharacterRead])
async def get_scene_characters(
    scene_id: str,
    db: AsyncSession = Depends(get_db_session_session),
):
    """Получить всех персонажей сцены."""
    service = CharacterService(db)
    characters = await service.get_scene_characters(scene_id)
    return characters


@router.put("/scene-characters/{scene_character_id}", response_model=SceneCharacterRead)
async def update_scene_character(
    scene_character_id: str,
    data: SceneCharacterUpdate,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Обновить персонажа в сцене (только для авторов)."""
    service = CharacterService(db)
    scene_char = await service.update_scene_character(scene_character_id, data, current_user.id)
    return scene_char


@router.delete("/scene-characters/{scene_character_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_character_from_scene(
    scene_character_id: str,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session_session),
):
    """Удалить персонажа из сцены (только для авторов)."""
    service = CharacterService(db)
    await service.remove_character_from_scene(scene_character_id, current_user.id)


# Utility endpoints

@router.post("/generate-prompt", response_model=SDPromptResponse)
async def generate_combined_prompt(
    data: GenerateWithCharactersRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session_session),
):
    """
    Сгенерировать комбинированный промпт для Stable Diffusion
    с учетом нескольких персонажей и их LoRA/embeddings.
    """
    service = CharacterService(db)
    result = await service.generate_combined_prompt(
        data.prompt,
        data.character_ids,
        current_user.id
    )
    
    return SDPromptResponse(
        prompt=result["prompt"],
        negative_prompt=result["negative_prompt"],
        lora_models=result["lora_models"],
        embeddings=result["embeddings"],
        characters=data.character_ids,
    )


@router.post("/generate-3step")
async def generate_character_3step(
    preset_id: str,
    scene_prompt: Optional[str] = None,
    use_wildcards: bool = True,
    overrides: Optional[GenerationOverrides] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session_session)
):
    """Generate character using 3-step workflow: portrait -> multiview -> scene"""
    
    try:
        # Create generation job
        job = GenerationJob(
            id=uuid4().hex,
            user_id=current_user.id,
            job_type="character_3step",
            status="running",
            progress=0,
            stage="initializing",
            results={}
        )
        db.add(job)
        await db.commit()
        
        # Start background task
        background_tasks = BackgroundTasks()
        background_tasks.add_task(
            execute_3step_generation,
            preset_id=preset_id,
            user_id=current_user.id,
            scene_prompt=scene_prompt,
            use_wildcards=use_wildcards,
            overrides=overrides,
            job_id=job.id,
            db=db
        )
        
        return {
            "job_id": job.id,
            "status": "started",
            "message": "3-step character generation started"
        }
        
    except Exception as e:
        logger.error(f"Failed to start 3-step generation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start generation: {str(e)}"
        )

async def execute_3step_generation(
    preset_id: str,
    user_id: str,
    scene_prompt: Optional[str],
    use_wildcards: bool,
    overrides: Optional[GenerationOverrides],
    job_id: str,
    db: AsyncSession
):
    """Background task for 3-step generation"""
    
    try:
        character_service = CharacterService(db)
        
        result = character_service.generate_character_3step_workflow(
            preset_id=preset_id,
            user_id=user_id,
            scene_prompt=scene_prompt,
            use_wildcards=use_wildcards,
            overrides=overrides,
            job_id=job_id
        )
        
        # Update job status
        job = await db.get(GenerationJob, job_id)
        if job:
            job.status = "completed"
            job.progress = 100
            job.stage = "complete"
            await db.commit()
        
        logger.info(f"3-step generation completed for preset {preset_id}")
        
    except Exception as e:
        logger.error(f"3-step generation failed: {e}")
        
        # Update job with error
        job = await db.get(GenerationJob, job_id)
        if job:
            job.status = "failed"
            job.stage = "error"
            job.results["error"] = str(e)
            await db.commit()

@router.get("/workflow-status/{job_id}")
async def get_workflow_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session_session)
):
    """Get status of 3-step workflow generation"""
    
    job = await db.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "results": job.results,
        "created_at": job.created_at,
        "updated_at": job.updated_at
    }

