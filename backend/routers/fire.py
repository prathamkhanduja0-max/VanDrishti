"""
backend/routers/fire.py
Router for NASA FIRMS active fire / thermal anomaly hotspot monitoring.
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from backend.services.fire_service import query_firms_hotspots

router = APIRouter(prefix="/api", tags=["Fire Monitoring"])


@router.get("/fire-hotspots", summary="Get NASA FIRMS VIIRS active fire hotspots")
async def get_fire_hotspots(
    preset: str = Query("osbs_live", description="Preset: 'osbs_live' (Florida) or 'demo_active' (California)"),
    day_range: int = Query(5, ge=1, le=5, description="Observation temporal window in days"),
):
    try:
        data = query_firms_hotspots(preset=preset, day_range=day_range)
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fire-hotspots/refresh", summary="Force refresh NASA FIRMS live observation query")
async def refresh_fire_hotspots(
    preset: str = Query("osbs_live", description="Preset: 'osbs_live' or 'demo_active'"),
    day_range: int = Query(5, ge=1, le=5, description="Temporal window"),
):
    try:
        data = query_firms_hotspots(preset=preset, day_range=day_range)
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
