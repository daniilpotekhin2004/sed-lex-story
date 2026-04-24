"""
Unified Asset Path Constants

Centralized asset path definitions for consistent usage across services.
"""

from pathlib import Path
from typing import Optional

class AssetPaths:
    """Centralized asset path management"""
    
    def __init__(self, base_path: str = "assets"):
        self.base = Path(base_path)
        self.generated = self.base / "generated"
        self.entities_root = self.generated / "entities"
    
    # Entity paths
    def character_path(self, character_id: str) -> Path:
        return self.entities_root / "characters" / character_id
    
    def character_sheets(self, character_id: str, version: str = "latest") -> Path:
        return self.character_path(character_id) / "sheets" / version
    
    def character_portraits(self, character_id: str, version: str = "latest") -> Path:
        return self.character_path(character_id) / "portraits" / version
    
    def character_sketches(self, character_id: str, version: str = "latest") -> Path:
        return self.character_path(character_id) / "sketches" / version
    
    def character_references(self, character_id: str) -> Path:
        return self.character_path(character_id) / "references"
    
    def character_voice(self, character_id: str) -> Path:
        return self.character_path(character_id) / "voice"
    
    # Location paths
    def location_path(self, location_id: str) -> Path:
        return self.entities_root / "locations" / location_id
    
    def location_sheets(self, location_id: str, version: str = "latest") -> Path:
        return self.location_path(location_id) / "sheets" / version
    
    def location_renders(self, location_id: str, version: str = "latest") -> Path:
        return self.location_path(location_id) / "renders" / version
    
    # Scene paths
    def scene_path(self, scene_id: str) -> Path:
        return self.entities_root / "scenes" / scene_id
    
    def scene_renders(self, scene_id: str, version: str = "latest") -> Path:
        return self.scene_path(scene_id) / "renders" / version
    
    def scene_storyboards(self, scene_id: str, version: str = "latest") -> Path:
        return self.scene_path(scene_id) / "storyboards" / version
    
    def scene_music(self, scene_id: str) -> Path:
        return self.scene_path(scene_id) / "music"
    
    # Generated content paths
    def voice_generated(self, entity_id: Optional[str] = None) -> Path:
        if entity_id:
            return self.character_voice(entity_id)
        return self.base / "generated" / "audio" / "voice"
    
    def music_generated(self, scene_id: Optional[str] = None) -> Path:
        if scene_id:
            return self.scene_music(scene_id)
        return self.base / "generated" / "audio" / "music"
    
    # System paths
    def comfyui_output(self) -> Path:
        # Keep ComfyUI output under generated so the whole model output tree lives in one place.
        return self.generated / "comfyui_output"
    
    def temp_processing(self) -> Path:
        return self.base / "temp" / "processing"
    
    def system_cache(self) -> Path:
        return self.base / "system" / "cache"

# Global instance
asset_paths = AssetPaths()
