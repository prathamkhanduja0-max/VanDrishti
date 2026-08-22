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
