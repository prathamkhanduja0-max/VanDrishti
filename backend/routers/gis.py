"""
backend/routers/gis.py
Router for serving GeoJSON layers and cost surfaces directly to the WebGIS dashboard.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from backend.services.gis_service import (
    get_assessment_json,
    get_boundary_geojson,
    get_cost_surface_json,
    get_degradation_geojson,
    get_health_grid_geojson,
    get_priority_geojson,
    get_route_geojson,
    get_trees_geojson,
)

router = APIRouter(tags=["GIS Data Layers"])


# Standard GIS paths
@router.get("/api/gis/boundary", summary="Get study area boundary GeoJSON")
@router.get("/api/boundary", summary="Get study area boundary GeoJSON (alias)")
async def fetch_boundary(site: str = Query("OSBS_large_2019", description="Site identifier")):
    data = get_boundary_geojson(site)
    if not data:
        raise HTTPException(status_code=404, detail=f"Boundary GeoJSON for site '{site}' not found")
    return JSONResponse(content=data)


@router.get("/api/gis/trees", summary="Get individual detected tree crowns GeoJSON")
@router.get("/api/trees", summary="Get individual detected tree crowns GeoJSON (alias)")
async def fetch_trees(
    site: str = Query("OSBS_large_2019", description="Site identifier"),
    chm_valid: bool = Query(True, description="Filter for LiDAR CHM validated crowns only"),
):
    data = get_trees_geojson(site, chm_valid_only=chm_valid)
    if not data:
        raise HTTPException(status_code=404, detail=f"Trees GeoJSON for site '{site}' not found")
    return JSONResponse(content=data)


@router.get("/api/gis/priority", summary="Get verification-priority scored tree crowns GeoJSON")
@router.get("/api/priority", summary="Get verification-priority scored tree crowns GeoJSON (alias)")
async def fetch_priority(site: str = Query("OSBS_large_2019", description="Site identifier")):
    data = get_priority_geojson(site)
    if not data:
        raise HTTPException(status_code=404, detail=f"Priority GeoJSON for site '{site}' not found")
    return JSONResponse(content=data)


@router.get("/api/gis/route", summary="Get optimal terrain-aware patrol route GeoJSON")
@router.get("/api/route", summary="Get optimal terrain-aware patrol route GeoJSON (alias)")
async def fetch_route(
    site: str = Query("OSBS_large_2019", description="Site identifier"),
    route_type: str = Query("terrain", description="'terrain' (Held-Karp on DTM+CHM) or 'legacy' (ExG)"),
):
    data = get_route_geojson(site, route_type=route_type)
    if not data:
        raise HTTPException(status_code=404, detail=f"Route GeoJSON for site '{site}' not found")
    return JSONResponse(content=data)


@router.get("/api/gis/health-grid", summary="Get composite Forest Health Score 25m grid GeoJSON")
@router.get("/api/health-grid", summary="Get composite Forest Health Score 25m grid GeoJSON (alias)")
async def fetch_health_grid(site: str = Query("OSBS_large_2019", description="Site identifier")):
    data = get_health_grid_geojson(site)
    if not data:
        raise HTTPException(status_code=404, detail=f"Forest health grid GeoJSON for site '{site}' not found")
    return JSONResponse(content=data)


@router.get("/api/gis/degradation", summary="Get multi-temporal LiDAR canopy loss polygons GeoJSON")
@router.get("/api/degradation", summary="Get multi-temporal LiDAR canopy loss polygons GeoJSON (alias)")
async def fetch_degradation(site: str = Query("OSBS_large_2019", description="Site identifier")):
    data = get_degradation_geojson(site)
    if not data:
        raise HTTPException(status_code=404, detail=f"Degradation GeoJSON for site '{site}' not found")
    return JSONResponse(content=data)


@router.get("/api/gis/cost-surface", summary="Get 2D cost surface matrix for client Dijkstra pathfinding")
async def fetch_cost_surface(site: str = Query("osbs", description="'osbs' or 'teak'")):
    data = get_cost_surface_json(site)
    if not data:
        raise HTTPException(status_code=404, detail=f"Cost surface for site '{site}' not found")
    return JSONResponse(content=data)


@router.get("/api/gis/assessment", summary="Get site capability assessment summary")
@router.get("/api/assessment", summary="Get site capability assessment summary (alias)")
async def fetch_assessment(site: str = Query("osbs", description="'osbs' or 'teak'")):
    data = get_assessment_json(site)
    if not data:
        raise HTTPException(status_code=404, detail=f"Assessment for site '{site}' not found")
    return JSONResponse(content=data)
