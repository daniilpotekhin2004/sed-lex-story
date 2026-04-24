"""
Unified Asset Management Service

Provides centralized asset storage and retrieval for all entity types.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import json
from datetime import datetime

from tools.unify_asset_storage import UnifiedAssetPaths, AssetStorageManager

class AssetService:
    """Centralized asset management service"""
    
    def __init__(self, base_path: str = "assets"):
        self.paths = UnifiedAssetPaths(base_path)
        self.manager = AssetStorageManager(base_path)
    
    def save_character_asset(self, 
                           character_id: str,
                           asset_type: str,
                           file_data: bytes,
                           filename: str,
                           version: str = "latest",
                           metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Save character asset with proper organization"""
        
        # Determine asset path based on type
        if asset_type == "sheet":
            asset_path = self.paths.character_sheet(character_id, version)
        elif asset_type == "portrait":
            asset_path = self.paths.character_portraits(character_id, version)
        elif asset_type == "sketch":
            asset_path = self.paths.character_sketches(character_id, version)
        elif asset_type == "reference":
            asset_path = self.paths.character_references(character_id)
        else:
            asset_path = self.paths.base / "entities" / "characters" / character_id / asset_type
        
        asset_path.mkdir(parents=True, exist_ok=True)
        file_path = asset_path / filename
        
        # Save file
        file_path.write_bytes(file_data)
        
        # Create asset record
        return self.manager.create_asset_record(
            entity_type="characters",
            entity_id=character_id,
            asset_type=asset_type,
            file_path=file_path,
            metadata=metadata
        )
    
    def get_character_assets(self, character_id: str, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all assets for a character"""
        
        entity_path = self.paths.base / "entities" / "characters" / character_id
        records_file = entity_path / "assets.json"
        
        if not records_file.exists():
            return []
        
        try:
            records = json.loads(records_file.read_text())
            if asset_type:
                return [r for r in records if r.get("asset_type") == asset_type]
            return records
        except:
            return []
    
    def save_voice_asset(self,
                        entity_id: Optional[str],
                        file_data: bytes,
                        filename: str,
                        metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Save voice asset"""
        
        asset_path = self.paths.voice_generated(entity_id)
        asset_path.mkdir(parents=True, exist_ok=True)
        file_path = asset_path / filename
        
        file_path.write_bytes(file_data)
        
        return self.manager.create_asset_record(
            entity_type="characters" if entity_id else "system",
            entity_id=entity_id or "global",
            asset_type="voice",
            file_path=file_path,
            metadata=metadata
        )
    
    def cleanup_temp_assets(self, max_age_hours: int = 24):
        """Clean up temporary assets older than specified hours"""
        
        temp_path = self.paths.temp_processing()
        if not temp_path.exists():
            return 0
        
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        cleaned = 0
        
        for item in temp_path.rglob("*"):
            if item.is_file() and item.stat().st_mtime < cutoff_time:
                item.unlink()
                cleaned += 1
        
        return cleaned
