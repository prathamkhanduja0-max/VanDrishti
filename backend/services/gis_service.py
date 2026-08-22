"""
backend/services/gis_service.py
Service for retrieving and serving GIS layers (GeoJSON and JSON summaries)
dynamically to the frontend dashboard.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from backend.config import FRONTEND_DATA_DIR, REPO_ROOT, RESULTS_GIS_DIR


def _read_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_boundary_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    # Priority: public WGS84 GeoJSON, fallback: results/gis
    target = FRONTEND_DATA_DIR / f"{site_name}_boundary.geojson"
    if not target.exists():
        target = FRONTEND_DATA_DIR / "OSBS_large_2019_boundary.geojson"
    if not target.exists():
        target = RESULTS_GIS_DIR / f"{site_name}_boundary.geojson"
    return _read_json_file(target)


def get_trees_geojson(site_name: str = "OSBS_large_2019", chm_valid_only: bool = True) -> Optional[Dict[str, Any]]:
    if chm_valid_only:
        target = FRONTEND_DATA_DIR / f"{site_name}_trees_chm_valid.geojson"
        if not target.exists():
            target = FRONTEND_DATA_DIR / "OSBS_large_2019_trees_chm_valid.geojson"
    else:
        target = FRONTEND_DATA_DIR / f"{site_name}_trees_filtered.geojson"
        if not target.exists():
            target = FRONTEND_DATA_DIR / "OSBS_large_2019_trees_with_boundary_status.geojson"
            
    if not target.exists():
        target = RESULTS_GIS_DIR / f"{site_name}_trees_filtered.geojson"
    return _read_json_file(target)


def get_priority_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    target = FRONTEND_DATA_DIR / f"{site_name}_verification_priority.geojson"
    if not target.exists():
        target = FRONTEND_DATA_DIR / "OSBS_large_2019_verification_priority.geojson"
    if not target.exists():
        target = RESULTS_GIS_DIR / f"{site_name}_verification_priority.geojson"
    return _read_json_file(target)


def get_route_geojson(site_name: str = "OSBS_large_2019", route_type: str = "terrain") -> Optional[Dict[str, Any]]:
    if route_type == "legacy" or route_type == "exg":
        target = FRONTEND_DATA_DIR / f"{site_name}_field_route_lcp_optimized.geojson"
        if not target.exists():
            target = FRONTEND_DATA_DIR / "OSBS_large_2019_field_route_lcp_optimized.geojson"
    else:
        target = FRONTEND_DATA_DIR / "route_terrain.geojson"
        if not target.exists():
            target = RESULTS_GIS_DIR / "route_terrain.geojson"
    return _read_json_file(target)


def get_health_grid_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    target = FRONTEND_DATA_DIR / "forest_health_grid.geojson"
    if not target.exists():
        target = RESULTS_GIS_DIR / "forest_health_grid.geojson"
    return _read_json_file(target)


def get_degradation_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    target = FRONTEND_DATA_DIR / "chm_loss_polygons.geojson"
    if not target.exists():
        target = RESULTS_GIS_DIR / "chm_loss_polygons.geojson"
    return _read_json_file(target)


def get_cost_surface_json(site_name: str = "osbs") -> Optional[Dict[str, Any]]:
    key = "teak" if "teak" in site_name.lower() else "osbs"
    target = FRONTEND_DATA_DIR / f"{key}_cost_surface.json"
    return _read_json_file(target)


def get_assessment_json(site_name: str = "osbs") -> Optional[Dict[str, Any]]:
    key = "teak" if "teak" in site_name.lower() else "osbs_full"
    target = FRONTEND_DATA_DIR / f"{key}_assessment.json"
    return _read_json_file(target)
