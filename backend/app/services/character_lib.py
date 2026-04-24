"""Character library service for managing reusable characters."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4

from app.core.config import get_settings
from app.infra.sd_request_layer import get_sd_layer
from app.infra.storage import LocalImageStorage
from app.services.pipeline_profiles import get_pipeline_resolver, PipelineSeedContext
from app.utils.sd_options import extract_sd_option_overrides
from app.schemas.character_lib import (
    AddReferenceRequest,
    CharacterAge,
    CharacterGender,
    CharacterLibCreate,
    CharacterLibList,
    CharacterLibUpdate,
    CharacterSearchRequest,
    CharacterStyle,
    GenerateReferenceRequest,
    LibraryCharacter,
    ReferenceImage,
    ReferenceImageType,
)

logger = logging.getLogger(__name__)


class CharacterLibraryService:
    """Service for managing character library stored on filesystem."""
    
    def __init__(self):
        self.settings = get_settings()
        self.lib_path = self.settings.character_lib_full_path
        self.lib_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.lib_path / "index.json"
        self._index: Dict[str, LibraryCharacter] = {}
        self._load_index()
    
    def _load_index(self) -> None:
        """Load character index from disk."""
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                for char_id, char_data in data.items():
                    self._index[char_id] = LibraryCharacter(**char_data)
            except Exception as e:
                logger.error(f"Failed to load character index: {e}")
                self._index = {}
    
    def _save_index(self) -> None:
        """Save character index to disk."""
        data = {
            char_id: char.dict() for char_id, char in self._index.items()
        }
        # Convert datetime objects to ISO strings
        for char_data in data.values():
            for key in ["created_at", "updated_at", "last_used_at"]:
                if char_data.get(key) and isinstance(char_data[key], datetime):
                    char_data[key] = char_data[key].isoformat()
            for ref in char_data.get("reference_images", []):
                if ref.get("created_at") and isinstance(ref["created_at"], datetime):
                    ref["created_at"] = ref["created_at"].isoformat()
            for emb in char_data.get("embeddings", []):
                if emb.get("trained_at") and isinstance(emb["trained_at"], datetime):
                    emb["trained_at"] = emb["trained_at"].isoformat()
        
        self._index_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8"
        )
    
    def _get_character_dir(self, char_id: str) -> Path:
        """Get directory for a character's assets."""
        return self.lib_path / char_id
    
    def create_character(
        self,
        data: CharacterLibCreate,
        author_id: Optional[str] = None,
    ) -> LibraryCharacter:
        """Create a new character in the library."""
        char_id = uuid4().hex
        now = datetime.utcnow()
        
        character = LibraryCharacter(
            id=char_id,
            name=data.name,
            description=data.description,
            gender=data.gender,
            age=data.age,
            style=data.style,
            appearance_prompt=data.appearance_prompt,
            negative_prompt=data.negative_prompt,
            style_tags=data.style_tags,
            is_public=data.is_public,
            tags=data.tags,
            author_id=author_id,
            created_at=now,
            updated_at=now,
        )
        
        # Create character directory
        char_dir = self._get_character_dir(char_id)
        char_dir.mkdir(parents=True, exist_ok=True)
        (char_dir / "references").mkdir(exist_ok=True)
        (char_dir / "embeddings").mkdir(exist_ok=True)
        
        self._index[char_id] = character
        self._save_index()
        
        logger.info(f"Created character {char_id}: {data.name}")
        return character
    
    def get_character(self, char_id: str) -> Optional[LibraryCharacter]:
        """Get character by ID."""
        return self._index.get(char_id)
    
    def update_character(
        self,
        char_id: str,
        data: CharacterLibUpdate,
    ) -> Optional[LibraryCharacter]:
        """Update character in library."""
        character = self._index.get(char_id)
        if not character:
            return None
        
        update_data = data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(character, field, value)
        
        character.updated_at = datetime.utcnow()
        self._index[char_id] = character
        self._save_index()
        
        return character
    
    def delete_character(self, char_id: str) -> bool:
        """Delete character from library."""
        if char_id not in self._index:
            return False
        
        # Remove directory
        char_dir = self._get_character_dir(char_id)
        if char_dir.exists():
            shutil.rmtree(char_dir)
        
        del self._index[char_id]
        self._save_index()
        
        logger.info(f"Deleted character {char_id}")
        return True
    
    def list_characters(
        self,
        page: int = 1,
        page_size: int = 20,
        author_id: Optional[str] = None,
        include_public: bool = True,
    ) -> CharacterLibList:
        """List characters with pagination."""
        chars = list(self._index.values())
        
        # Filter by access. Treat unowned (author_id=None) entries as shared library.
        if author_id:
            chars = [
                c
                for c in chars
                if c.author_id == author_id
                or (include_public and (c.is_public or c.author_id is None))
            ]
        elif include_public:
            chars = [c for c in chars if c.is_public or c.author_id is None]
        
        # Sort by name
        chars.sort(key=lambda c: c.name.lower())
        
        total = len(chars)
        start = (page - 1) * page_size
        end = start + page_size
        
        return CharacterLibList(
            items=chars[start:end],
            total=total,
            page=page,
            page_size=page_size,
        )
    
    def search_characters(
        self,
        request: CharacterSearchRequest,
        author_id: Optional[str] = None,
    ) -> CharacterLibList:
        """Search characters with filters."""
        chars = list(self._index.values())
        
        # Filter by access. Treat unowned (author_id=None) entries as shared library.
        if author_id:
            chars = [
                c
                for c in chars
                if c.author_id == author_id
                or (request.include_public and (c.is_public or c.author_id is None))
            ]
        elif request.include_public:
            chars = [c for c in chars if c.is_public or c.author_id is None]
        
        # Apply filters
        if request.query:
            query = request.query.lower()
            chars = [
                c for c in chars
                if query in c.name.lower()
                or (c.description and query in c.description.lower())
                or query in c.appearance_prompt.lower()
            ]
        
        if request.gender:
            chars = [c for c in chars if c.gender == request.gender]
        
        if request.age:
            chars = [c for c in chars if c.age == request.age]
        
        if request.style:
            chars = [c for c in chars if c.style == request.style]
        
        if request.tags:
            chars = [
                c for c in chars
                if any(t in c.tags for t in request.tags)
            ]
        
        total = len(chars)
        start = (request.page - 1) * request.page_size
        end = start + request.page_size
        
        return CharacterLibList(
            items=chars[start:end],
            total=total,
            page=request.page,
            page_size=request.page_size,
        )
    
    def add_reference_image(
        self,
        char_id: str,
        request: AddReferenceRequest,
    ) -> Optional[ReferenceImage]:
        """Add reference image to character."""
        character = self._index.get(char_id)
        if not character:
            return None
        
        ref_id = uuid4().hex
        char_dir = self._get_character_dir(char_id)
        refs_dir = char_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        
        # Save image
        import base64
        if request.image_data.startswith("data:"):
            _, data = request.image_data.split(",", 1)
            image_bytes = base64.b64decode(data)
        else:
            image_bytes = base64.b64decode(request.image_data)
        
        image_path = refs_dir / f"{ref_id}.png"
        image_path.write_bytes(image_bytes)
        
        # Create reference entry
        rel_path = image_path.relative_to(self.settings.assets_root_path).as_posix()
        ref = ReferenceImage(
            id=ref_id,
            type=request.type,
            url=f"/api/assets/{rel_path}",
            prompt_tags=request.prompt_tags,
            weight=request.weight,
            created_at=datetime.utcnow(),
        )
        
        character.reference_images.append(ref)
        
        # Set as primary if first reference
        if not character.primary_reference_id:
            character.primary_reference_id = ref_id
        
        character.updated_at = datetime.utcnow()
        self._index[char_id] = character
        self._save_index()
        
        return ref
    
    def generate_reference_image(
        self,
        char_id: str,
        request: GenerateReferenceRequest,
    ) -> List[ReferenceImage]:
        """Generate reference images for character using SD."""
        character = self._index.get(char_id)
        if not character:
            return []
        
        # Build prompt based on reference type
        type_prompts = {
            ReferenceImageType.PORTRAIT: "portrait, face close-up, head and shoulders",
            ReferenceImageType.FULL_BODY: "full body, standing pose, head to toe",
            ReferenceImageType.SIDE_VIEW: "side view, profile, side angle",
            ReferenceImageType.BACK_VIEW: "back view, from behind",
            ReferenceImageType.EXPRESSION: "facial expression, emotion, face focus",
            ReferenceImageType.POSE: "dynamic pose, action pose",
            ReferenceImageType.OUTFIT: "outfit focus, clothing details, fashion",
        }
        
        type_prompt = type_prompts.get(request.type, "")
        prompt = f"{character.appearance_prompt}, {type_prompt}"
        if request.additional_prompt:
            prompt = f"{prompt}, {request.additional_prompt}"
        if character.style_tags:
            prompt = f"{prompt}, {', '.join(character.style_tags)}"

        resolver = get_pipeline_resolver()
        sd_layer = get_sd_layer()
        option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        resolved = resolver.resolve(
            kind="character_ref",
            overrides={
                "width": request.width,
                "height": request.height,
                "sampler": option_overrides.get("sampler"),
                "scheduler": option_overrides.get("scheduler"),
                "seed_policy": "random",
            },
            seed_context=PipelineSeedContext(
                kind="character_ref",
                character_id=char_id,
                slot=str(request.type),
            ),
        )

        # Generate images
        images = sd_layer.generate_simple(
            prompt=prompt,
            negative_prompt=character.negative_prompt,
            num_images=request.num_variants,
            width=resolved.width,
            height=resolved.height,
            cfg_scale=resolved.cfg_scale,
            steps=resolved.steps,
            seed=resolved.seed,
            sampler=resolved.sampler,
            scheduler=resolved.scheduler,
            model_id=resolved.model_id,
            vae_id=resolved.vae_id,
            loras=[lora.model_dump() for lora in resolved.loras],
        )
        
        # Save and create references
        refs: List[ReferenceImage] = []
        char_dir = self._get_character_dir(char_id)
        refs_dir = char_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        
        for img_bytes in images:
            ref_id = uuid4().hex
            image_path = refs_dir / f"{ref_id}.png"
            image_path.write_bytes(img_bytes)
            
            rel_path = image_path.relative_to(self.settings.assets_root_path).as_posix()
            ref = ReferenceImage(
                id=ref_id,
                type=request.type,
                url=f"/api/assets/{rel_path}",
                created_at=datetime.utcnow(),
            )
            refs.append(ref)
            character.reference_images.append(ref)
        
        if not character.primary_reference_id and refs:
            character.primary_reference_id = refs[0].id
        
        character.updated_at = datetime.utcnow()
        self._index[char_id] = character
        self._save_index()
        
        return refs
    
    def remove_reference_image(
        self,
        char_id: str,
        ref_id: str,
    ) -> bool:
        """Remove reference image from character."""
        character = self._index.get(char_id)
        if not character:
            return False
        
        # Find and remove reference
        ref_idx = next(
            (i for i, r in enumerate(character.reference_images) if r.id == ref_id),
            None
        )
        if ref_idx is None:
            return False
        
        ref = character.reference_images.pop(ref_idx)
        
        # Delete file
        if ref.url.startswith("/api/assets/"):
            rel = ref.url[len("/api/assets/"):]
            path = self.settings.assets_root_path / rel
            if path.exists():
                path.unlink()
        
        # Update primary if needed
        if character.primary_reference_id == ref_id:
            character.primary_reference_id = (
                character.reference_images[0].id
                if character.reference_images else None
            )
        
        character.updated_at = datetime.utcnow()
        self._index[char_id] = character
        self._save_index()
        
        return True
    
    def get_character_prompt(
        self,
        char_id: str,
        include_style: bool = True,
    ) -> Optional[str]:
        """Get combined prompt for character."""
        character = self._index.get(char_id)
        if not character:
            return None
        
        parts = [character.appearance_prompt]
        if include_style and character.style_tags:
            parts.extend(character.style_tags)
        
        return ", ".join(parts)
    
    def get_character_references(
        self,
        char_id: str,
        types: Optional[List[ReferenceImageType]] = None,
    ) -> List[Tuple[str, bytes]]:
        """Get reference images as bytes for generation."""
        character = self._index.get(char_id)
        if not character:
            return []
        
        refs = character.reference_images
        if types:
            refs = [r for r in refs if r.type in types]
        
        result: List[Tuple[str, bytes]] = []
        for ref in refs:
            if ref.url.startswith("/api/assets/"):
                rel = ref.url[len("/api/assets/"):]
                path = self.settings.assets_root_path / rel
                if path.exists():
                    result.append((ref.id, path.read_bytes()))
        
        return result
    
    def record_usage(self, char_id: str) -> None:
        """Record character usage."""
        character = self._index.get(char_id)
        if character:
            character.usage_count += 1
            character.last_used_at = datetime.utcnow()
            self._index[char_id] = character
            self._save_index()


# Global instance
_character_lib: Optional[CharacterLibraryService] = None


def get_character_lib() -> CharacterLibraryService:
    """Get or create character library service."""
    global _character_lib
    if _character_lib is None:
        _character_lib = CharacterLibraryService()
    return _character_lib
