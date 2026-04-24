from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings


def normalize_uploaded_image(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data)) as image:
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid image.",
        ) from exc


async def read_uploaded_image(file: UploadFile) -> tuple[bytes, str]:
    filename = (file.filename or "upload.png").strip() or "upload.png"
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    return normalize_uploaded_image(raw), filename


def save_uploaded_image(entity_type: str, entity_id: str, asset_key: str, image_bytes: bytes) -> str:
    settings = get_settings()
    root = settings.generated_assets_path / "uploads" / entity_type / entity_id / asset_key
    root.mkdir(parents=True, exist_ok=True)
    filename = root / f"{uuid4().hex[:10]}.png"
    filename.write_bytes(image_bytes)
    rel = Path(filename).relative_to(settings.assets_root_path).as_posix()
    return f"/api/assets/{rel}"
