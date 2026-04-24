from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings,SettingsConfigDict
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


def _normalize_sqlite_url(url: str) -> str:
    if not url.startswith("sqlite"):
        return url

    try:
        parsed = make_url(url)
    except Exception:
        return url

    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return url

    database_path = Path(parsed.database)
    if not database_path.is_absolute():
        database_path = (PROJECT_ROOT / database_path).resolve()

    # Preserve native absolute drive paths on Windows. Prefixing an extra slash
    # turns `F:/...` into `/F:/...`, which breaks sqlite+aiosqlite.
    normalized_database = database_path.as_posix()

    return parsed.set(database=normalized_database).render_as_string(hide_password=False)


class Settings(BaseSettings):

    app_name: str = Field("LexQuest Backend", env="APP_NAME")
    environment: str = Field("local", env="ENVIRONMENT")
    version: str = Field("0.1.0", validation_alias="APP_VERSION")

    backend_host: str = Field("0.0.0.0", env="BACKEND_HOST")
    backend_port: int = Field(8888, env="BACKEND_PORT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    allowed_origins: str = Field("*", env="ALLOWED_ORIGINS")
    secret_key: str = Field("change-me", env="SECRET_KEY")
    
    # JWT settings
    jwt_secret_key: str = Field("change-me-jwt-secret", env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    postgres_user: str = Field("lexquest", env="POSTGRES_USER")
    postgres_password: str = Field("lexquest", env="POSTGRES_PASSWORD")
    postgres_db: str = Field("lexquest", env="POSTGRES_DB")
    postgres_host: str = Field("postgres", env="POSTGRES_HOST")
    postgres_port: int = Field(5432, env="POSTGRES_PORT")
    database_url: Optional[str] = Field(None, env="DATABASE_URL")

    redis_url: str = Field("redis://redis:6379/0", env="REDIS_URL")
    sd_api_url: str = Field("http://localhost:7860", env="SD_API_URL")
    sd_provider: str = Field("a1111", env="SD_PROVIDER")
    sd_fallback_provider: str = Field("a1111", env="SD_FALLBACK_PROVIDER")
    sd_comfy_url: str = Field("http://localhost:8188", env="SD_COMFY_URL")
    sd_comfy_workflow_txt2img: str = Field("", env="SD_COMFY_WORKFLOW_TXT2IMG")
    sd_comfy_workflow_img2img: str = Field("", env="SD_COMFY_WORKFLOW_IMG2IMG")
    sd_comfy_output_nodes_txt2img: str = Field("", env="SD_COMFY_OUTPUT_NODES_TXT2IMG")
    sd_comfy_output_nodes_img2img: str = Field("", env="SD_COMFY_OUTPUT_NODES_IMG2IMG")
    sd_comfy_api_url: str = Field("https://cloud.comfy.org/api", env="SD_COMFY_API_URL")
    sd_comfy_api_key: Optional[str] = Field("comfyui-9bb7abe29fd48865f7d05479eb9ea9b85fc4cc6b587ef80eb2369ddd5bcb58c8", env="SD_COMFY_API_KEY")
    sd_comfy_api_key_header: str = Field("X-API-Key", env="SD_COMFY_API_KEY_HEADER")
    sd_comfy_api_key_prefix: str = Field("", env="SD_COMFY_API_KEY_PREFIX")
    comfy_api_balance_usd: Optional[float] = Field(None, env="COMFY_API_BALANCE_USD")
    comfy_api_cost_per_job_usd: Optional[float] = Field(None, env="COMFY_API_COST_PER_JOB_USD")
    sd_poe_api_url: str = Field("https://api.poe.com/v1", env="SD_POE_API_URL")
    sd_poe_api_key: Optional[str] = Field(None, env="SD_POE_API_KEY")
    sd_poe_model: str = Field("GPT-Image-1", env="SD_POE_MODEL")
    sd_poe_quality: str = Field("low", env="SD_POE_QUALITY")
    sd_comfy_model: str = Field("qwen-rapid-nsfw-v9.0-Q4_K_M.gguf", env="SD_COMFY_MODEL")
    sd_comfy_vae: str = Field("qwen-image\\qwen_image_vae.safetensors", env="SD_COMFY_VAE")
    sd_comfy_sampler: str = Field("dpmpp_2m", env="SD_COMFY_SAMPLER")
    sd_comfy_scheduler: str = Field("karras", env="SD_COMFY_SCHEDULER")
    # Store ComfyUI outputs inside the generated assets subdirectory.  Keeping all generated
    # content under a single tree simplifies asset management and reflects the relationship
    # between different types of generated outputs.
    sd_comfy_output_dir: str = Field("assets/generated/comfyui_output", env="SD_COMFY_OUTPUT_DIR")
    comfyui_force_gpu: bool = Field(False, env="COMFYUI_FORCE_GPU")
    
    # ComfyUI paths and execution
    comfyui_path: str = Field("F:/ComfyUI", env="COMFYUI_PATH")
    comfyui_python: str = Field("", env="COMFYUI_PYTHON")
    comfyui_port: int = Field(8188, env="COMFYUI_PORT")
    sd_mock_mode: bool = Field(False, env="SD_MOCK_MODE")
    sd_request_log_dir: str = Field("logs/sd", env="SD_REQUEST_LOG_DIR")
    sd_request_log_retention_days: int = Field(2, env="SD_REQUEST_LOG_RETENTION_DAYS")
    sd_request_log_max_mb: int = Field(100, env="SD_REQUEST_LOG_MAX_MB")
    translation_cache_file: str = Field(
        "logs/translation_cache.json",
        validation_alias="TRANSLATION_CACHE_PATH",
    )

    # Pipeline profile settings
    pipeline_profiles_file: str = Field(
        "app/config/pipeline_profiles.json",
        validation_alias="PIPELINE_PROFILE_PATH",
    )
    style_profile_templates_file: str = Field(
        "app/config/style_profile_templates.json",
        validation_alias="STYLE_PROFILE_TEMPLATES_PATH",
    )

    pipeline_profile_default_id: str = Field("sd35_default", env="PIPELINE_PROFILE_DEFAULT_ID")
    pipeline_profile_default_version: Optional[int] = Field(None, env="PIPELINE_PROFILE_DEFAULT_VERSION")
    # ControlNet settings
    controlnet_enabled: bool = Field(True, env="CONTROLNET_ENABLED")
    controlnet_models: str = Field("openpose,canny,depth,lineart", env="CONTROLNET_MODELS")
    controlnet_default_weight: float = Field(1.0, env="CONTROLNET_DEFAULT_WEIGHT")
    controlnet_default_guidance_start: float = Field(0.0, env="CONTROLNET_DEFAULT_GUIDANCE_START")
    controlnet_default_guidance_end: float = Field(1.0, env="CONTROLNET_DEFAULT_GUIDANCE_END")
    controlnet_openpose_module: str = Field("openpose_full", env="CONTROLNET_OPENPOSE_MODULE")
    controlnet_openpose_model: str = Field("control_v11p_sd15_openpose", env="CONTROLNET_OPENPOSE_MODEL")
    controlnet_reference_module: str = Field("reference_only", env="CONTROLNET_REFERENCE_MODULE")
    controlnet_reference_model: str = Field("control_v11p_sd15_reference", env="CONTROLNET_REFERENCE_MODEL")
    controlnet_pose_weight: float = Field(1.0, env="CONTROLNET_POSE_WEIGHT")
    controlnet_reference_weight: float = Field(0.6, env="CONTROLNET_REFERENCE_WEIGHT")
    controlnet_processor_res: int = Field(512, env="CONTROLNET_PROCESSOR_RES")
    controlnet_threshold_a: float = Field(64, env="CONTROLNET_THRESHOLD_A")
    controlnet_threshold_b: float = Field(64, env="CONTROLNET_THRESHOLD_B")
    roop_alwayson_template: str = Field("", validation_alias="ROOP_ALWAYS_ON_TEMPLATE")
    roop_require_single: bool = Field(True, env="ROOP_REQUIRE_SINGLE")
    character_quality_enabled: bool = Field(True, env="CHARACTER_QUALITY_ENABLED")
    character_quality_interrogate_model: str = Field("clip", env="CHARACTER_QUALITY_INTERROGATE_MODEL")
    character_quality_min_score: float = Field(0.35, env="CHARACTER_QUALITY_MIN_SCORE")
    character_quality_face_min_score: float = Field(0.45, env="CHARACTER_QUALITY_FACE_MIN_SCORE")
    character_quality_body_min_score: float = Field(0.35, env="CHARACTER_QUALITY_BODY_MIN_SCORE")
    character_quality_max_attempts: int = Field(1, env="CHARACTER_QUALITY_MAX_ATTEMPTS")
    character_quality_use_openpose: bool = Field(True, env="CHARACTER_QUALITY_USE_OPENPOSE")
    character_quality_use_ip_adapter: bool = Field(True, env="CHARACTER_QUALITY_USE_IP_ADAPTER")
    character_quality_denoise: float = Field(0.55, env="CHARACTER_QUALITY_DENOISE")
    character_quality_face_weight: float = Field(0.85, env="CHARACTER_QUALITY_FACE_WEIGHT")
    character_quality_body_weight: float = Field(0.65, env="CHARACTER_QUALITY_BODY_WEIGHT")
    character_reference_multiview_enabled: bool = Field(
        False, env="CHARACTER_REFERENCE_MULTIVIEW_ENABLED"
    )
    character_reference_prompts_file: str = Field(
        "app/config/character_reference_prompts.json", env="CHARACTER_REFERENCE_PROMPTS_PATH"
    )
    training_data_subdir: str = Field("training", env="TRAINING_DATA_SUBDIR")
    
    # Multipass generation settings
    multipass_enabled: bool = Field(True, env="MULTIPASS_ENABLED")
    multipass_max_passes: int = Field(5, env="MULTIPASS_MAX_PASSES")
    multipass_default_passes: int = Field(3, env="MULTIPASS_DEFAULT_PASSES")
    
    # Character library settings
    character_lib_path: str = Field("assets/character_lib", env="CHARACTER_LIB_PATH")
    character_lib_enabled: bool = Field(True, env="CHARACTER_LIB_ENABLED")

    assets_root: str = Field("assets", env="ASSETS_ROOT")
    generated_assets_subdir: str = Field("generated", env="GENERATED_ASSETS_SUBDIR")

    celery_task_always_eager: bool = Field(False, env="CELERY_TASK_ALWAYS_EAGER")

    # Frontend settings
    vite_port: int = Field(5174, env="VITE_PORT")
    frontend_port: int = Field(5174, env="FRONTEND_PORT")
    
    # OpenAI/LLM settings  
    openai_model: Optional[str] = Field(None, env="OPENAI_MODEL")
    openai_base_url: Optional[str] = Field(None, env="OPENAI_BASE_URL")
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    llm_temperature: Optional[float] = Field(None, validation_alias="OPENAI_TEMPERATURE")
    llm_top_p: Optional[float] = Field(None, validation_alias="OPENAI_TOP_P")
    llm_frequency_penalty: Optional[float] = Field(
        None, validation_alias="OPENAI_FREQUENCY_PENALTY"
    )
    llm_presence_penalty: Optional[float] = Field(
        None, validation_alias="OPENAI_PRESENCE_PENALTY"
    )
    llm_max_tokens: Optional[int] = Field(None, validation_alias="OPENAI_MAX_TOKENS")
    llm_timeout_seconds: Optional[float] = Field(90.0, validation_alias="OPENAI_TIMEOUT")
    llm_max_retries: int = Field(5, validation_alias="OPENAI_MAX_RETRIES")
    llm_backoff_base: float = Field(1.0, validation_alias="OPENAI_BACKOFF_BASE")
    llm_backoff_max: float = Field(20.0, validation_alias="OPENAI_BACKOFF_MAX")
    ai_sequence_model: Optional[str] = Field(None, env="AI_SEQUENCE_MODEL")
    ai_sequence_fallback_model: Optional[str] = Field("gpt-4.1-mini", env="AI_SEQUENCE_FALLBACK_MODEL")
    ai_sequence_temperature: float = Field(0.9, env="AI_SEQUENCE_TEMPERATURE")
    ai_sequence_top_p: float = Field(0.9, env="AI_SEQUENCE_TOP_P")
    ai_sequence_frequency_penalty: float = Field(1.1, env="AI_SEQUENCE_FREQUENCY_PENALTY")
    ai_sequence_presence_penalty: float = Field(0.1, env="AI_SEQUENCE_PRESENCE_PENALTY")
    ai_sequence_debug_log_enabled: bool = Field(True, env="AI_SEQUENCE_DEBUG_LOG_ENABLED")
    ai_sequence_debug_log_file: str = Field(
        "logs/ai_sequence_draft_failures.jsonl",
        env="AI_SEQUENCE_DEBUG_LOG_FILE",
    )
    wizard_critic_model: Optional[str] = Field(None, env="WIZARD_CRITIC_MODEL")
    wizard_critic_prompt_file: str = Field(
        "app/config/prompts/wizard_step7_critic.md",
        validation_alias="WIZARD_CRITIC_PROMPT_PATH",
    )

    # Optional "creative" mode features powered by AI masters (narrative/entity/voice helpers).
    # Disabled by default so the project runs without any external LLM/TTS configuration.
    ai_masters_creative_enabled: bool = Field(False, env="AI_MASTERS_CREATIVE_ENABLED")
    llm_access_dat_path: Optional[str] = Field(None, validation_alias="ACCESS_DAT_PATH")

    # TTS settings (OpenAI-compatible by default)
    tts_base_url: Optional[str] = Field(None, env="TTS_BASE_URL")
    tts_api_key: Optional[str] = Field(None, env="TTS_API_KEY")
    tts_model: Optional[str] = Field(None, env="TTS_MODEL")
    tts_voice: Optional[str] = Field(None, env="TTS_VOICE")
    tts_endpoint: str = Field("/audio/speech", env="TTS_ENDPOINT")
    tts_format: str = Field("mp3", env="TTS_FORMAT")
    tts_format_field: str = Field("response_format", env="TTS_FORMAT_FIELD")
    tts_language_field: Optional[str] = Field(None, env="TTS_LANGUAGE_FIELD")
    tts_voice_prompt_field: Optional[str] = Field(None, env="TTS_VOICE_PROMPT_FIELD")
    tts_use_voice_profile: bool = Field(True, env="TTS_USE_VOICE_PROFILE")
    tts_timeout_seconds: Optional[float] = Field(None, validation_alias="TTS_TIMEOUT")
    tts_provider: str = Field("auto", env="TTS_PROVIDER")
    tts_comfy_workflow_path: Optional[str] = Field(None, env="TTS_COMFY_WORKFLOW_PATH")
    tts_comfy_output_nodes: str = Field("", env="TTS_COMFY_OUTPUT_NODES")
    tts_comfy_text_node_id: Optional[str] = Field(None, env="TTS_COMFY_TEXT_NODE_ID")
    tts_comfy_voice_node_id: Optional[str] = Field(None, env="TTS_COMFY_VOICE_NODE_ID")
    tts_comfy_model_choice: Optional[str] = Field(None, env="TTS_COMFY_MODEL_CHOICE")
    tts_comfy_seed: Optional[int] = Field(None, env="TTS_COMFY_SEED")

    # Telegram bot (optional)
    telegram_bot_enabled: bool = Field(True, env="TELEGRAM_BOT_ENABLED")
    telegram_bot_token: Optional[str] = Field(None, env="TELEGRAM_BOT_TOKEN")
    telegram_bot_backend_url: str = Field("http://localhost:8888", env="TELEGRAM_BOT_BACKEND_URL")
    telegram_bot_poll_timeout: int = Field(25, env="TELEGRAM_BOT_POLL_TIMEOUT")
    telegram_bot_admin_ids: str = Field("", env="TELEGRAM_BOT_ADMIN_IDS")
    
    # LLM aliases for backward compatibility
    @property
    def llm_api_key(self) -> Optional[str]:
        return self.openai_api_key
    
    @property
    def llm_base_url(self) -> Optional[str]:
        return self.openai_base_url
    
    @property
    def llm_model(self) -> Optional[str]:
        return self.openai_model

    class Config:
        env_file = str(ENV_FILE) if ENV_FILE.exists() else ".env"
        env_file_encoding = "utf-8"
        str_strip_whitespace=True
        
    @validator("database_url", pre=True, always=True)
    def assemble_db_url(cls, v: Optional[str], values: dict) -> str:
        if v:
            return _normalize_sqlite_url(v)
        url = (
            f"postgresql+asyncpg://{values['postgres_user']}:{values['postgres_password']}"
            f"@{values['postgres_host']}:{values['postgres_port']}/{values['postgres_db']}"
        )
        return _normalize_sqlite_url(url)

    @property
    def allowed_origins_list(self) -> List[str]:
        if self.allowed_origins == "*":
            # For development, allow all common localhost ports + additional ports
            return [
                "http://localhost",
                "https://localhost",
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:5174",
                "http://localhost:5175",
                "http://localhost:5176",
                "http://localhost:8080",
                "http://localhost:8888",
                "http://127.0.0.1",
                "https://127.0.0.1",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://127.0.0.1:5175",
                "http://127.0.0.1:5176",
                "http://127.0.0.1:8080",
                "http://127.0.0.1:8888",
                # Allow all localhost for development
                "*"
            ]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def controlnet_models_list(self) -> List[str]:
        return [m.strip() for m in self.controlnet_models.split(",") if m.strip()]

    @property
    def telegram_bot_admin_ids_list(self) -> List[int]:
        values: List[int] = []
        for token in self.telegram_bot_admin_ids.split(","):
            part = token.strip()
            if not part:
                continue
            try:
                values.append(int(part))
            except ValueError:
                continue
        return values

    @property
    def character_lib_full_path(self) -> Path:
        return Path(self.character_lib_path)

    @property
    def assets_root_path(self) -> Path:
        """Get the absolute path to assets directory."""
        assets_path = Path(self.assets_root)
        if assets_path.is_absolute():
            return assets_path
        else:
            # If relative, resolve from project root (parent of backend dir)
            backend_dir = Path(__file__).parent.parent.parent  # Go up from app/core/config.py to backend/
            project_root = backend_dir.parent  # Go up one more to project root
            return (project_root / self.assets_root).resolve()

    @property
    def generated_assets_path(self) -> Path:
        return self.assets_root_path / self.generated_assets_subdir

    @property
    def training_data_path(self) -> Path:
        return self.assets_root_path / self.training_data_subdir

    @property
    def pipeline_profiles_path(self) -> Path:
        path = Path(self.pipeline_profiles_file)
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return (backend_dir / path).resolve()

    @property
    def style_profile_templates_path(self) -> Path:
        path = Path(self.style_profile_templates_file)
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return (backend_dir / path).resolve()

    @property
    def character_reference_prompts_path(self) -> Path:
        path = Path(self.character_reference_prompts_file)
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return (backend_dir / path).resolve()

    @property
    def translation_cache_path(self) -> Path:
        path = Path(self.translation_cache_file)
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return (backend_dir / path).resolve()

    @property
    def ai_sequence_debug_log_path(self) -> Path:
        path = Path(self.ai_sequence_debug_log_file)
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return (backend_dir / path).resolve()

    @property
    def wizard_critic_prompt_path(self) -> Path:
        path = Path(self.wizard_critic_prompt_file)
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).parent.parent.parent
        return (backend_dir / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache to reload from environment."""
    get_settings.cache_clear()
