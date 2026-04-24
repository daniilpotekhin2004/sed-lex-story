"""Schemas for multipass slide generation with ControlNet."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ControlNetModule(str, Enum):
    """Available ControlNet modules."""
    OPENPOSE = "openpose"
    OPENPOSE_FULL = "openpose_full"
    OPENPOSE_FACE = "openpose_face"
    OPENPOSE_HAND = "openpose_hand"
    CANNY = "canny"
    DEPTH = "depth"
    DEPTH_MIDAS = "depth_midas"
    DEPTH_ZOE = "depth_zoe"
    LINEART = "lineart"
    LINEART_ANIME = "lineart_anime"
    SOFTEDGE = "softedge"
    SCRIBBLE = "scribble"
    SEGMENTATION = "segmentation"
    REFERENCE_ONLY = "reference_only"
    IP_ADAPTER = "ip-adapter"
    IP_ADAPTER_FACE = "ip-adapter-face"


class ControlNetUnit(BaseModel):
    """Single ControlNet unit configuration."""
    module: ControlNetModule = Field(..., description="ControlNet preprocessor module")
    model: Optional[str] = Field(None, description="ControlNet model name (auto-detected if None)")
    weight: float = Field(1.0, ge=0.0, le=2.0, description="ControlNet weight")
    guidance_start: float = Field(0.0, ge=0.0, le=1.0, description="When to start applying ControlNet")
    guidance_end: float = Field(1.0, ge=0.0, le=1.0, description="When to stop applying ControlNet")
    processor_res: int = Field(512, ge=64, le=2048, description="Preprocessor resolution")
    threshold_a: float = Field(64, description="Threshold A for preprocessor")
    threshold_b: float = Field(64, description="Threshold B for preprocessor")
    input_image: Optional[str] = Field(None, description="Base64 or URL of input image")
    resize_mode: int = Field(1, ge=0, le=2, description="0=Just Resize, 1=Crop and Resize, 2=Resize and Fill")
    low_vram: bool = Field(False, description="Enable low VRAM mode")
    pixel_perfect: bool = Field(False, description="Enable pixel perfect mode")


class PassType(str, Enum):
    """Types of generation passes."""
    SKETCH = "sketch"           # Initial rough sketch
    LINEART = "lineart"         # Clean lineart pass
    BASE_COLOR = "base_color"   # Base colors
    SHADING = "shading"         # Shading and lighting
    DETAIL = "detail"           # Fine details
    FINAL = "final"             # Final refinement
    CUSTOM = "custom"           # Custom pass


class GenerationPass(BaseModel):
    """Configuration for a single generation pass."""
    pass_type: PassType = Field(..., description="Type of this pass")
    prompt_suffix: Optional[str] = Field(None, description="Additional prompt for this pass")
    negative_suffix: Optional[str] = Field(None, description="Additional negative prompt")
    denoising_strength: float = Field(0.5, ge=0.0, le=1.0, description="Denoising strength for img2img")
    controlnet_units: List[ControlNetUnit] = Field(default_factory=list, description="ControlNet units for this pass")
    cfg_scale: Optional[float] = Field(None, description="Override CFG scale for this pass")
    steps: Optional[int] = Field(None, description="Override steps for this pass")
    use_previous_output: bool = Field(True, description="Use output from previous pass as input")
    sampler: Optional[str] = Field(None, description="Override sampler for this pass")


class MultipassRequest(BaseModel):
    """Request for multipass slide generation."""
    prompt: str = Field(..., min_length=1, description="Main generation prompt")
    negative_prompt: Optional[str] = Field(None, description="Negative prompt")
    width: int = Field(768, ge=256, le=2048, description="Output width")
    height: int = Field(512, ge=256, le=2048, description="Output height")
    seed: Optional[int] = Field(None, description="Random seed (-1 for random)")
    cfg_scale: float = Field(7.0, ge=1.0, le=30.0, description="CFG scale")
    steps: int = Field(20, ge=1, le=150, description="Sampling steps")
    sampler: str = Field("Euler a", description="Sampler name")
    scheduler: Optional[str] = Field(None, description="Scheduler name")
    model_id: Optional[str] = Field(None, description="Model checkpoint id")
    vae_id: Optional[str] = Field(None, description="VAE id")
    loras: Optional[List[dict]] = Field(None, description="LoRA list [{name, weight}]")
    pipeline_profile_id: Optional[str] = Field(None, description="Pipeline profile id")
    pipeline_profile_version: Optional[int] = Field(None, description="Pipeline profile version")
    
    # Multipass configuration
    passes: List[GenerationPass] = Field(default_factory=list, description="Generation passes")
    auto_passes: bool = Field(True, description="Auto-generate passes if none provided")
    num_auto_passes: int = Field(3, ge=1, le=5, description="Number of auto passes")
    
    # Character references
    character_ids: List[str] = Field(default_factory=list, description="Character IDs from library")
    character_weights: Dict[str, float] = Field(default_factory=dict, description="Per-character weights")
    
    # Initial image (optional)
    init_image: Optional[str] = Field(None, description="Base64 or URL of initial image")
    init_denoising: float = Field(0.7, ge=0.0, le=1.0, description="Initial denoising strength")
    
    # Output options
    save_intermediate: bool = Field(False, description="Save intermediate pass results")
    output_folder: Optional[str] = Field(None, description="Custom output folder")


class PassResult(BaseModel):
    """Result of a single generation pass."""
    pass_index: int
    pass_type: PassType
    image_url: str
    prompt_used: str
    negative_used: Optional[str]
    seed_used: int
    duration_ms: int
    controlnet_applied: List[str] = Field(default_factory=list)


class MultipassResult(BaseModel):
    """Result of multipass generation."""
    task_id: str
    final_image_url: str
    passes: List[PassResult]
    total_duration_ms: int
    characters_used: List[str] = Field(default_factory=list)
    seed: int
    width: int
    height: int


class MultipassStatus(BaseModel):
    """Status of multipass generation task."""
    task_id: str
    state: str
    current_pass: int
    total_passes: int
    progress_percent: float
    current_pass_type: Optional[PassType] = None
    error: Optional[str] = None
    result: Optional[MultipassResult] = None
