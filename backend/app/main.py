from contextlib import asynccontextmanager
from pathlib import Path
import time
import traceback
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.api.routes import (
    ai_v1,
    ai_masters_v1,
    auth,
    characters,
    character_lib_v1,
    generation,
    generation_v1,
    generation_jobs_v1,
    multipass_v1,
    prompt_v1,
    scene_characters_v1,
    scene_composition_v1,
    export_v1,
    health,
    moderation,
    telemetry,
    presets,
    player_v1,
    project_releases_v1,
    quests,
    scenes,
    setup,
    user_presets,
    projects_v1,
    project_voiceover_v1,
    scenario_v1,
    legal_v1,
    style_profiles_v1,
    ops_v1,
    world_v1,
    material_sets_v1,
    studio_v1,
    training_v1,
    sd_options_v1,
    voice_generator,
    tts,
    narrative_ai_v1,
    ai_masters_v1,
    wizard_v1,
    admin_v1,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.telemetry import log_request
from app.infra.db import engine, init_db

# Initialize crypto optimizations for hardware acceleration
try:
    from .crypto_optimization import initialize_crypto_optimizations
    initialize_crypto_optimizations()
except ImportError:
    print("⚠️  Crypto optimizations not available")


settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    configure_logging(settings.log_level)
    await init_db()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )

    # Root cause: Frontend sends custom headers (X-Comfy-Api-Key, X-Sd-Provider, etc.)
    # that need to be allowed in CORS preflight requests
    allowed_origins = [origin for origin in settings.allowed_origins_list if origin != "*"]
    allow_credentials = True
    if not allowed_origins:
        # Fallback to wildcard without credentials when no explicit origins are configured.
        allowed_origins = ["*"]
        allow_credentials = False

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],  # Allow all HTTP methods
        allow_headers=["*"],  # Allow all headers including custom ones
        expose_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(auth.router, prefix="/api")
    application.include_router(ai_v1.router, prefix="/api")
    application.include_router(ai_masters_v1.router, prefix="/api")
    application.include_router(characters.router, prefix="/api")
    application.include_router(moderation.router, prefix="/api")
    application.include_router(generation.router, prefix="/api")
    application.include_router(generation_v1.router, prefix="/api")
    application.include_router(generation_jobs_v1.router, prefix="/api")
    application.include_router(prompt_v1.router, prefix="/api")
    application.include_router(scene_characters_v1.router, prefix="/api")
    application.include_router(scene_composition_v1.router, prefix="/api/v1")
    application.include_router(export_v1.router, prefix="/api")
    application.include_router(presets.router, prefix="/api")
    application.include_router(player_v1.router, prefix="/api")
    application.include_router(project_releases_v1.router, prefix="/api")
    application.include_router(user_presets.router, prefix="/api")
    application.include_router(quests.router, prefix="/api")
    application.include_router(scenes.router, prefix="/api")
    application.include_router(projects_v1.router, prefix="/api")
    application.include_router(project_voiceover_v1.router, prefix="/api")
    application.include_router(scenario_v1.router, prefix="/api")
    application.include_router(legal_v1.router, prefix="/api")
    application.include_router(style_profiles_v1.router, prefix="/api")
    application.include_router(ops_v1.router, prefix="/api")
    application.include_router(world_v1.router, prefix="/api")
    application.include_router(material_sets_v1.router, prefix="/api")
    application.include_router(studio_v1.router, prefix="/api")
    application.include_router(training_v1.router, prefix="/api")
    application.include_router(multipass_v1.router, prefix="/api/v1")
    application.include_router(character_lib_v1.router, prefix="/api/v1")
    application.include_router(sd_options_v1.router, prefix="/api/v1")
    application.include_router(voice_generator.router, prefix="/api")
    application.include_router(tts.router)
    application.include_router(narrative_ai_v1.router, prefix="/api")
    application.include_router(wizard_v1.router, prefix="/api")
    application.include_router(admin_v1.router, prefix="/api")
    application.include_router(telemetry.router, prefix="/api")

    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_msg = f"Unhandled exception: {exc}"
        tb = traceback.format_exc()
        logger.error(f"{error_msg}\n{tb}")
        print(f"ERROR: {error_msg}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "traceback": tb}
        )

    @application.middleware("http")
    async def add_request_logging(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        try:
            log_request(request.method, request.url.path, response.status_code, duration_ms)
        except Exception:
            # Logging must never break the main flow
            pass
        return response
    
    # Статические файлы для изображений
    assets_path = settings.assets_root_path
    assets_path.mkdir(parents=True, exist_ok=True)
    application.mount("/api/assets", StaticFiles(directory=str(assets_path)), name="assets")
    
    return application


app = create_app()

