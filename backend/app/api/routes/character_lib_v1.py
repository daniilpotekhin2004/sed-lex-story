"""API routes for character library management."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, status, Query
from app.schemas.character_lib import (
    AddReferenceRequest,
    CharacterLibCreate,
    CharacterLibList,
    CharacterLibUpdate,
    CharacterSearchRequest,
    GenerateReferenceRequest,
    LibraryCharacter,
    ReferenceImage,
)
from app.services.character_lib import get_character_lib
from app.core.config import get_settings

router = APIRouter(prefix="/character-lib", tags=["character-library"])


@router.post("", response_model=LibraryCharacter)
async def create_character(data: CharacterLibCreate):
    """Create a new character in the library."""
    settings = get_settings()
    if not settings.character_lib_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Character library is disabled"
        )
    
    lib = get_character_lib()
    return lib.create_character(data)


@router.get("", response_model=CharacterLibList)
async def list_characters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_public: bool = True,
):
    """List characters in the library."""
    lib = get_character_lib()
    return lib.list_characters(page=page, page_size=page_size, include_public=include_public)


@router.post("/search", response_model=CharacterLibList)
async def search_characters(request: CharacterSearchRequest):
    """Search characters with filters."""
    lib = get_character_lib()
    return lib.search_characters(request)


@router.get("/{char_id}", response_model=LibraryCharacter)
async def get_character(char_id: str):
    """Get character by ID."""
    lib = get_character_lib()
    character = lib.get_character(char_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )
    return character


@router.patch("/{char_id}", response_model=LibraryCharacter)
async def update_character(char_id: str, data: CharacterLibUpdate):
    """Update character in library."""
    lib = get_character_lib()
    character = lib.update_character(char_id, data)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )
    return character


@router.delete("/{char_id}")
async def delete_character(char_id: str):
    """Delete character from library."""
    lib = get_character_lib()
    if not lib.delete_character(char_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )
    return {"status": "deleted", "id": char_id}


@router.post("/{char_id}/references", response_model=ReferenceImage)
async def add_reference(char_id: str, request: AddReferenceRequest):
    """Add reference image to character."""
    lib = get_character_lib()
    ref = lib.add_reference_image(char_id, request)
    if not ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )
    return ref


@router.post("/{char_id}/references/generate", response_model=list)
async def generate_reference(char_id: str, request: GenerateReferenceRequest):
    """Generate reference images for character using SD."""
    lib = get_character_lib()
    refs = lib.generate_reference_image(char_id, request)
    if not refs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found or generation failed"
        )
    return refs


@router.delete("/{char_id}/references/{ref_id}")
async def remove_reference(char_id: str, ref_id: str):
    """Remove reference image from character."""
    lib = get_character_lib()
    if not lib.remove_reference_image(char_id, ref_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character or reference not found"
        )
    return {"status": "deleted", "ref_id": ref_id}


@router.get("/{char_id}/prompt")
async def get_character_prompt(char_id: str, include_style: bool = True):
    """Get combined prompt for character."""
    lib = get_character_lib()
    prompt = lib.get_character_prompt(char_id, include_style=include_style)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )
    return {"prompt": prompt}
