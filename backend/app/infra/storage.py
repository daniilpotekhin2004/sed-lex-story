from __future__ import annotations

from pathlib import Path
from typing import Iterable, List
from uuid import uuid4


class LocalImageStorage:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_images(self, scene_id: str, images: Iterable[bytes]) -> List[str]:
        """Save images under a folder and return absolute file paths.

        We intentionally generate *unique* filenames for each save call. This
        avoids two common problems:

        1) Browser/proxy caching when an asset URL stays the same after a
           regeneration.
        2) Overwriting previously saved variants when multiple images are
           produced sequentially into the same folder.
        """
        scene_dir = self.base_path / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        paths: List[str] = []
        for idx, data in enumerate(images):
            filename = scene_dir / f"{uuid4().hex[:8]}-variant-{idx + 1}.png"
            with filename.open("wb") as fp:
                fp.write(data)
            paths.append(str(filename))
        return paths

    def save_images_for_scene(self, project_id: str, scene_id: str, images: Iterable[bytes]) -> List[str]:
        """Save images under project/scene folders."""
        scene_dir = self.base_path / str(project_id) / str(scene_id)
        scene_dir.mkdir(parents=True, exist_ok=True)

        paths: List[str] = []
        for idx, data in enumerate(images):
            filename = scene_dir / f"{uuid4().hex[:8]}-variant-{idx + 1}.png"
            with filename.open("wb") as fp:
                fp.write(data)
            paths.append(str(filename))
        return paths
    def save_entity_images(self, entity_type: str, entity_id: str, asset_type: str, 
                          images: Iterable[bytes], version: str = "latest") -> List[str]:
        """Save images for a specific entity with proper organization"""
        folder_path = f"entities/{entity_type}/{entity_id}/{asset_type}/{version}"
        return self.save_images(folder_path, images)
    
    def save_character_asset(self, character_id: str, asset_type: str, 
                           images: Iterable[bytes], version: str = "latest") -> List[str]:
        """Save character-specific assets"""
        return self.save_entity_images("characters", character_id, asset_type, images, version)
    
    def save_location_asset(self, location_id: str, asset_type: str,
                          images: Iterable[bytes], version: str = "latest") -> List[str]:
        """Save location-specific assets"""
        return self.save_entity_images("locations", location_id, asset_type, images, version)
    
    def save_scene_asset(self, scene_id: str, asset_type: str,
                        images: Iterable[bytes], version: str = "latest") -> List[str]:
        """Save scene-specific assets"""
        return self.save_entity_images("scenes", scene_id, asset_type, images, version)

