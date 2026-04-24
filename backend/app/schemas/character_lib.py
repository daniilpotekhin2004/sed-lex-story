"""Schemas for character library management."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CharacterGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class CharacterAge(str, Enum):
    CHILD = "child"
    TEEN = "teen"
    YOUNG_ADULT = "young_adult"
    ADULT = "adult"
    MIDDLE_AGED = "middle_aged"
    ELDERLY = "elderly"


class CharacterStyle(str, Enum):
    REALISTIC = "realistic"
    ANIME = "anime"
    CARTOON = "cartoon"
    SEMI_REALISTIC = "semi_realistic"
    STYLIZED = "stylized"


class ReferenceImageType(str, Enum):
    PORTRAIT = "portrait"
    FULL_BODY = "full_body"
    SIDE_VIEW = "side_view"
    BACK_VIEW = "back_view"
    EXPRESSION = "expression"
    POSE = "pose"
    OUTFIT = "outfit"
    CUSTOM = "custom"


class ReferenceImage(BaseModel):
    """Reference image for a character."""
    id: str
    type: ReferenceImageType
    url: str
    thumbnail_url: Optional[str] = None
    prompt_tags: List[str] = Field(default_factory=list)
    embedding_path: Optional[str] = Field(None, description="Path to TI embedding if trained")
    lora_path: Optional[str] = Field(None, description="Path to LoRA if trained")
    weight: float = Field(1.0, ge=0.0, le=2.0)
    created_at: Optional[datetime] = None


class CharacterEmbedding(BaseModel):
    """Trained embedding for a character."""
    name: str
    path: str
    type: str = Field("textual_inversion", description="textual_inversion or lora")
    trigger_word: str
    strength: float = Field(1.0, ge=0.0, le=2.0)
    trained_at: Optional[datetime] = None
    training_steps: Optional[int] = None


class LibraryCharacter(BaseModel):
    """Character stored in the library."""
    id: str
    name: str
    description: Optional[str] = None
    
    # Visual attributes
    gender: CharacterGender = CharacterGender.UNKNOWN
    age: CharacterAge = CharacterAge.ADULT
    style: CharacterStyle = CharacterStyle.REALISTIC
    
    # Prompt components
    appearance_prompt: str = Field(..., description="Core appearance description")
    negative_prompt: Optional[str] = None
    style_tags: List[str] = Field(default_factory=list)
    
    # Reference images
    reference_images: List[ReferenceImage] = Field(default_factory=list)
    primary_reference_id: Optional[str] = Field(None, description="ID of primary reference image")
    
    # Trained models
    embeddings: List[CharacterEmbedding] = Field(default_factory=list)
    
    # Metadata
    author_id: Optional[str] = None
    is_public: bool = False
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Usage stats
    usage_count: int = 0
    last_used_at: Optional[datetime] = None


class CharacterLibCreate(BaseModel):
    """Create a new character in library."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    gender: CharacterGender = CharacterGender.UNKNOWN
    age: CharacterAge = CharacterAge.ADULT
    style: CharacterStyle = CharacterStyle.REALISTIC
    appearance_prompt: str = Field(..., min_length=1)
    negative_prompt: Optional[str] = None
    style_tags: List[str] = Field(default_factory=list)
    is_public: bool = False
    tags: List[str] = Field(default_factory=list)


class CharacterLibUpdate(BaseModel):
    """Update character in library."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    gender: Optional[CharacterGender] = None
    age: Optional[CharacterAge] = None
    style: Optional[CharacterStyle] = None
    appearance_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    style_tags: Optional[List[str]] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None
    primary_reference_id: Optional[str] = None


class AddReferenceRequest(BaseModel):
    """Add reference image to character."""
    type: ReferenceImageType = ReferenceImageType.PORTRAIT
    image_data: str = Field(..., description="Base64 encoded image or URL")
    prompt_tags: List[str] = Field(default_factory=list)
    weight: float = Field(1.0, ge=0.0, le=2.0)


class GenerateReferenceRequest(BaseModel):
    """Generate reference image for character."""
    type: ReferenceImageType = ReferenceImageType.PORTRAIT
    additional_prompt: Optional[str] = None
    width: int = Field(512, ge=256, le=1024)
    height: int = Field(512, ge=256, le=1024)
    num_variants: int = Field(1, ge=1, le=4)


class CharacterLibList(BaseModel):
    """List of characters from library."""
    items: List[LibraryCharacter]
    total: int
    page: int
    page_size: int


class CharacterSearchRequest(BaseModel):
    """Search characters in library."""
    query: Optional[str] = None
    gender: Optional[CharacterGender] = None
    age: Optional[CharacterAge] = None
    style: Optional[CharacterStyle] = None
    tags: List[str] = Field(default_factory=list)
    include_public: bool = True
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
