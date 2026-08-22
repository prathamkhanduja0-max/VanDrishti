"""
backend/services/gis_service.py
Service for retrieving and serving GIS layers (GeoJSON and JSON summaries)
strictly site-aware without cross-site OSBS fallbacks.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from backend.config import FRONTEND_DATA_DIR, REPO_ROOT, RESULTS_GIS_DIR, UPLOADS_DIR


def _read_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_boundary_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    # Custom upload check
    if site_name.startswith("upload_") or (UPLOADS_DIR / site_name).exists():
        job_dir = UPLOADS_DIR / site_name
        return _read_json_file(job_dir / "boundary.geojson") or _read_json_file(job_dir / "raster_extent.geojson")

    # Preset sites
    candidates = [
        FRONTEND_DATA_DIR / f"{site_name}_boundary.geojson",
        RESULTS_GIS_DIR / f"{site_name}_boundary.geojson"
    ]
    if "osbs" in site_name.lower():
        candidates.append(FRONTEND_DATA_DIR / "project_boundary_OSBS_022.geojson")

    for path in candidates:
        res = _read_json_file(path)
        if res:
            return res
    return None


def get_trees_geojson(site_name: str = "OSBS_large_2019", chm_valid_only: bool = True) -> Optional[Dict[str, Any]]:
    # Custom upload check
    if site_name.startswith("upload_") or (UPLOADS_DIR / site_name).exists():
        job_dir = UPLOADS_DIR / site_name
        if chm_valid_only:
            return _read_json_file(job_dir / "trees_chm_valid.geojson")
        return _read_json_file(job_dir / "trees.geojson") or _read_json_file(job_dir / "trees_raw.geojson")

    # Preset sites
    if chm_valid_only:
        candidates = [
            FRONTEND_DATA_DIR / f"{site_name}_trees_chm_valid.geojson",
            RESULTS_GIS_DIR / f"{site_name}_trees_chm_valid.geojson"
        ]
    else:
        candidates = [
            FRONTEND_DATA_DIR / f"{site_name}_trees_filtered.geojson",
            FRONTEND_DATA_DIR / f"{site_name}_trees_with_boundary_status.geojson",
            RESULTS_GIS_DIR / f"{site_name}_trees_filtered.geojson",
            RESULTS_GIS_DIR / f"{site_name}_trees.geojson"
        ]

    for path in candidates:
        res = _read_json_file(path)
        if res:
            return res
    return None


def get_priority_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    # Custom upload check
    if site_name.startswith("upload_") or (UPLOADS_DIR / site_name).exists():
        job_dir = UPLOADS_DIR / site_name
        return _read_json_file(job_dir / "priority.geojson")

    candidates = [
        FRONTEND_DATA_DIR / f"{site_name}_verification_priority.geojson",
        RESULTS_GIS_DIR / f"{site_name}_verification_priority.geojson"
    ]
    for path in candidates:
        res = _read_json_file(path)
        if res:
            return res
    return None


def get_route_geojson(site_name: str = "OSBS_large_2019", route_type: str = "terrain") -> Optional[Dict[str, Any]]:
    # Custom upload check
    if site_name.startswith("upload_") or (UPLOADS_DIR / site_name).exists():
        job_dir = UPLOADS_DIR / site_name
        return _read_json_file(job_dir / "route.geojson")

    candidates = []
    if "teak" in site_name.lower():
        candidates = [
            FRONTEND_DATA_DIR / f"{site_name}_field_route_lcp.geojson",
            RESULTS_GIS_DIR / f"{site_name}_field_route_lcp.geojson"
        ]
    else:
        if route_type in ("legacy", "exg"):
            candidates = [
                FRONTEND_DATA_DIR / f"{site_name}_field_route_lcp_optimized.geojson",
                RESULTS_GIS_DIR / f"{site_name}_field_route_lcp_optimized.geojson"
            ]
        else:
            candidates = [
                FRONTEND_DATA_DIR / f"{site_name}_field_route_lcp_optimized.geojson",
                FRONTEND_DATA_DIR / "route_terrain.geojson",
                RESULTS_GIS_DIR / "route_terrain.geojson"
            ]

    for path in candidates:
        res = _read_json_file(path)
        if res:
            return res
    return None


def get_health_grid_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    if site_name.startswith("upload_") or (UPLOADS_DIR / site_name).exists():
        job_dir = UPLOADS_DIR / site_name
        return _read_json_file(job_dir / "health_grid.geojson")

    # Health grid is available for OSBS_large_2019
    if "osbs" in site_name.lower():
        candidates = [
            FRONTEND_DATA_DIR / f"{site_name}_health_grid.geojson",
            FRONTEND_DATA_DIR / "forest_health_grid.geojson",
            RESULTS_GIS_DIR / "forest_health_grid.geojson"
        ]
        for path in candidates:
            res = _read_json_file(path)
            if res:
                return res
    return None


def get_degradation_geojson(site_name: str = "OSBS_large_2019") -> Optional[Dict[str, Any]]:
    if site_name.startswith("upload_") or (UPLOADS_DIR / site_name).exists():
        job_dir = UPLOADS_DIR / site_name
        return _read_json_file(job_dir / "degradation.geojson")

    # Degradation polygons available for OSBS_large_2019
    if "osbs" in site_name.lower():
        candidates = [
            FRONTEND_DATA_DIR / f"{site_name}_chm_loss_polygons.geojson",
            FRONTEND_DATA_DIR / "chm_loss_polygons.geojson",
            RESULTS_GIS_DIR / "chm_loss_polygons.geojson"
        ]
        for path in candidates:
            res = _read_json_file(path)
            if res:
                return res
    return None


def get_cost_surface_json(site_name: str = "osbs") -> Optional[Dict[str, Any]]:
    key = "teak" if "teak" in site_name.lower() else "osbs"
    target = FRONTEND_DATA_DIR / f"{key}_cost_surface.json"
    return _read_json_file(target)


def get_assessment_json(site_name: str = "osbs") -> Optional[Dict[str, Any]]:
    key = "teak" if "teak" in site_name.lower() else "osbs_full"
    target = FRONTEND_DATA_DIR / f"{key}_assessment.json"
    return _read_json_file(target)
