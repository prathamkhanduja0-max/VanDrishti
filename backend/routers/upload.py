"""
backend/routers/upload.py
Router handling raster/vector data uploads and spatial validation.
"""

from typing import List
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from backend.schemas import UploadResponse
from backend.services.upload_service import process_uploaded_file
from backend.database import list_uploads

router = APIRouter(prefix="/api/upload", tags=["Uploads"])


@router.post("", response_model=UploadResponse, summary="Upload RGB/LiDAR raster or boundary GeoJSON")
async def upload_file(
    file: UploadFile = File(..., description="Raster (.tif) or vector (.geojson, .shp) dataset"),
    file_type: str = Form("rgb_t2", description="Role: 'rgb_t2', 'rgb_t1', 'chm_t2', 'chm_t1', 'dtm', 'boundary'"),
):
    try:
        record = process_uploaded_file(file, file_type)
        return record
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded file: {str(e)}")


@router.get("/list", response_model=List[UploadResponse], summary="List uploaded datasets and their metadata")
async def get_uploaded_files():
    return list_uploads()

@router.get("/{upload_id}/cost-surface", summary="Get or generate routable cost surface for uploaded raster")
async def get_cost_surface(upload_id: str):
    from backend.services.upload_service import get_upload_cost_surface
    cs = get_upload_cost_surface(upload_id)
    if not cs:
        raise HTTPException(status_code=404, detail=f"Cost surface not found for upload {upload_id}")
    return cs


@router.get("/{upload_id}/preview", summary="Get web preview image (PNG) for uploaded raster")
async def get_upload_preview(upload_id: str):
    from fastapi.responses import FileResponse
    from backend.services.upload_service import get_upload_preview_path

    preview_path = get_upload_preview_path(upload_id)
    if not preview_path or not preview_path.exists():
        raise HTTPException(status_code=404, detail=f"Preview image not found for upload {upload_id}")
    return FileResponse(preview_path, media_type="image/png")


@router.get("/{upload_id}/report", summary="Generate and download assessment report (PDF/CSV) for uploaded dataset")
async def get_upload_report(upload_id: str, format: str = "pdf"):
    from fastapi.responses import FileResponse
    from backend.services.upload_service import generate_upload_report_file

    file_path, filename, media_type = generate_upload_report_file(upload_id, format=format)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Failed to generate report for upload {upload_id}")
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



