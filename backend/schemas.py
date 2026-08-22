"""
backend/schemas.py
Pydantic data validation schemas for requests and responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Upload schemas
class UploadResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    file_path: str
    file_size_bytes: int
    crs: Optional[str] = None
    bounds: Optional[Dict[str, Any]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    assessment: Optional[Dict[str, Any]] = None


# Process & Job schemas
class ProcessRequest(BaseModel):
    site_name: Optional[str] = Field("OSBS_large_2019", description="Preset site name: 'OSBS_large_2019' or 'TEAK_043_2018'")
    config_file: Optional[str] = Field("config.yaml", description="Configuration filename relative to repo root")
    run_tsp: bool = Field(True, description="Whether to run Held-Karp TSP route optimization")
    run_degradation: bool = Field(True, description="Whether to run multi-temporal degradation analysis")
    run_health_score: bool = Field(True, description="Whether to run forest health scoring")
    reproject_wgs84: bool = Field(True, description="Whether to reproject outputs to WGS84 EPSG:4326 for GIS frontend")


class JobStatusResponse(BaseModel):
    job_id: str
    site_name: str
    config_path: Optional[str] = None
    status: str  # 'pending', 'running', 'completed', 'failed'
    progress_percent: int
    current_step: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    logs: Optional[str] = None
    results: Optional[Dict[str, Any]] = None


# Fire Hotspots schemas
class FireHotspotsRequest(BaseModel):
    preset: Optional[str] = Field("osbs_live", description="'osbs_live' or 'demo_active'")
    bbox: Optional[List[float]] = Field(None, description="Custom bounding box [west, south, east, north]")
    day_range: Optional[int] = Field(5, description="1 to 5 days query window")


class FireHotspotsResponse(BaseModel):
    preset: str
    aoi_name: str
    hotspot_count: int
    source: str
    geojson_url: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


# Assessment Schemas
class AssessmentResponse(BaseModel):
    site_name: str
    crs: Optional[str] = None
    is_projected: bool = False
    resolution_m: Optional[List[float]] = None
    dimensions_px: Optional[List[int]] = None
    ground_area_ha: Optional[float] = None
    capabilities: Dict[str, Any]
    rasters: Dict[str, Any]
