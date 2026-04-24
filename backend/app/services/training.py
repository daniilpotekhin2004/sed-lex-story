from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import CharacterPreset, MaterialSet
from app.infra.sd_request_layer import get_sd_layer


class TrainingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def create_textual_inversion(
        self,
        *,
        token: str,
        user_id: str,
        character_id: Optional[str] = None,
        init_text: Optional[str] = None,
        num_vectors: int = 1,
        overwrite: bool = False,
    ) -> dict:
        sd_layer = get_sd_layer()
        info = sd_layer.client.create_embedding(
            name=token,
            num_vectors_per_token=num_vectors,
            overwrite=overwrite,
            init_text=init_text,
        )
        sd_layer.client.refresh_embeddings()

        if character_id:
            preset = await self.db.get(CharacterPreset, character_id)
            if not preset:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found")
            if preset.author_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this preset",
                )
            embeddings = list(preset.embeddings or [])
            if token not in embeddings:
                embeddings.append(token)
                preset.embeddings = embeddings
                await self.db.commit()
                await self.db.refresh(preset)

        return info or {}

    async def prepare_lora_dataset(
        self,
        *,
        material_set_id: str,
        token: str,
        user_id: str,
        label: Optional[str] = None,
        caption: Optional[str] = None,
        character_id: Optional[str] = None,
    ) -> dict:
        material = await self.db.get(MaterialSet, material_set_id)
        if not material:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material set not found")

        if character_id and material.asset_id != character_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Material set does not match the requested character",
            )

        urls = _extract_reference_urls(material.reference_images)
        if not urls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Material set has no reference images",
            )

        dataset_root = self.settings.training_data_path / "lora" / material_set_id
        dataset_id = uuid4().hex[:8]
        dataset_path = dataset_root / dataset_id
        dataset_path.mkdir(parents=True, exist_ok=True)

        written = 0
        caption_text = token
        if caption:
            caption_text = f"{caption_text}, {caption}"

        for idx, url in enumerate(urls):
            data = _load_asset_bytes(url, self.settings.assets_root)
            if not data:
                continue
            image_path = dataset_path / f"image_{idx:03d}.png"
            image_path.write_bytes(data)
            (dataset_path / f"image_{idx:03d}.txt").write_text(caption_text, encoding="utf-8")
            written += 1

        if written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to resolve any reference images for training",
            )

        metadata = material.material_metadata if isinstance(material.material_metadata, dict) else {}
        history = list(metadata.get("training_sets", [])) if isinstance(metadata.get("training_sets"), list) else []
        entry = {
            "id": dataset_id,
            "token": token,
            "label": label or material.label,
            "caption": caption,
            "path": str(dataset_path),
            "image_count": written,
            "created_at": datetime.utcnow().isoformat(),
        }
        history.append(entry)
        metadata["training_sets"] = history
        material.material_metadata = metadata
        await self.db.commit()
        await self.db.refresh(material)

        return {
            "dataset_path": str(dataset_path),
            "image_count": written,
            "token": token,
            "label": label or material.label,
            "material_set_id": material_set_id,
        }


def _extract_reference_urls(refs: list | None) -> list[str]:
    urls: list[str] = []
    for ref in refs or []:
        if not isinstance(ref, dict):
            continue
        url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
        if url:
            urls.append(str(url))
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _resolve_asset_path(url: str, assets_root: str) -> Optional[Path]:
    if not url or not url.startswith("/api/assets/"):
        return None
    rel = url[len("/api/assets/") :]
    return Path(assets_root) / rel


def _load_asset_bytes(url: str, assets_root: str) -> bytes | None:
    path = _resolve_asset_path(url, assets_root)
    if not path or not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None
