import json
from io import BytesIO
from zipfile import ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_db_session
from app.schemas.export import ProjectExport
from app.services.export import ExportService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/projects", tags=["export"])


@router.get("/{project_id}/export", response_model=ProjectExport)
async def export_project(
    project_id: str,
    export_format: str | None = Query(None, description="Set to 'zip' to download archive"),
    requested_format: str | None = Query(None, alias="format", include_in_schema=False),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectExport:
    service = ExportService(session)
    result = await service.export_project(project_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found or no graph")
    effective_format = requested_format or export_format
    if effective_format and effective_format.lower() == "zip":
        buffer = BytesIO()
        with ZipFile(buffer, "w") as zf:
            export_json = json.dumps(result.dict(), ensure_ascii=False, default=str, indent=2)
            zf.writestr("export.json", export_json)
            approved_images = []
            for scene_entry in result.scenes:
                if scene_entry.approved_image:
                    approved_images.append(
                        {
                            "scene_id": scene_entry.scene.id,
                            "image_id": scene_entry.approved_image.id,
                            "url": scene_entry.approved_image.url,
                            "metadata": scene_entry.approved_image.image_metadata,
                        }
                    )
            zf.writestr("approved_images.json", json.dumps(approved_images, ensure_ascii=False, default=str, indent=2))
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="project-{project_id}-export.zip"'},
        )
    return result
