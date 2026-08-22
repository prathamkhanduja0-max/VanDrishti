"""
backend/services/upload_service.py
Service for handling file uploads (RGB/LiDAR rasters, boundaries, GeoJSON),
validating spatial metadata with rasterio/geopandas, running automated capability
assessment via assess_upload.py, and persisting upload records in SQLite.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import geopandas as gpd
import rasterio
from fastapi import UploadFile

from backend.config import REPO_ROOT, UPLOADS_DIR
from backend.database import create_upload_record

# Ensure scripts directory is in sys.path
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def process_uploaded_file(file: UploadFile, file_type: str = "rgb_t2") -> Dict[str, Any]:
    upload_id = str(uuid.uuid4())
    safe_filename = f"{upload_id}_{file.filename}"
    target_path = UPLOADS_DIR / safe_filename
    
    # Save uploaded file
    file_bytes = file.file.read()
    file_size = len(file_bytes)
    with open(target_path, "wb") as f:
        f.write(file_bytes)
        
    crs = None
    bounds = None
    width = None
    height = None
    metadata: Dict[str, Any] = {}
    assessment: Optional[Dict[str, Any]] = None
    
    # 1. Raster Processing (.tif, .tiff, .img, .vrt)
    if target_path.suffix.lower() in [".tif", ".tiff", ".img", ".vrt"]:
        try:
            with rasterio.open(target_path) as src:
                crs = str(src.crs) if src.crs else None
                width = int(src.width)
                height = int(src.height)
                b = src.bounds
                bounds = {
                    "left": float(b.left),
                    "bottom": float(b.bottom),
                    "right": float(b.right),
                    "top": float(b.top),
                }
                metadata["bands"] = int(src.count)
                metadata["dtype"] = str(src.dtypes[0])
                metadata["resolution"] = [float(abs(src.transform.a)), float(abs(src.transform.e))]
                metadata["is_projected"] = bool(src.crs and src.crs.is_projected)
        except Exception as e:
            metadata["raster_inspect_error"] = str(e)

        # Run automated capability assessment
        try:
            import assess_upload
            assessment = assess_upload.assess_upload(target_path, run_detection=True)
            metadata["assessment"] = assessment
        except Exception as assess_err:
            metadata["assessment_error"] = str(assess_err)

        # Generate routable cost surface for interactive Dijkstra routing
        try:
            from upload_cost_surface import build_upload_cost_surface
            cost_surface = build_upload_cost_surface(rgb_path=target_path, name=file.filename)
            cost_surface_file = UPLOADS_DIR / f"{upload_id}_cost_surface.json"
            with open(cost_surface_file, "w", encoding="utf-8") as cs_f:
                json.dump(cost_surface, cs_f)
            metadata["cost_surface_file"] = str(cost_surface_file)
            metadata["routable"] = cost_surface.get("routable", False)
            metadata["routing_mode"] = cost_surface.get("mode_label")
        except Exception as cs_err:
            metadata["cost_surface_error"] = str(cs_err)

    # 2. Vector Processing (.geojson, .json, .shp, .gpkg, .kml)
    elif target_path.suffix.lower() in [".geojson", ".json", ".shp", ".gpkg", ".kml"]:
        try:
            gdf = gpd.read_file(target_path)
            crs = str(gdf.crs) if gdf.crs else None
            total_bounds = gdf.total_bounds  # minx, miny, maxx, maxy
            bounds = {
                "left": float(total_bounds[0]),
                "bottom": float(total_bounds[1]),
                "right": float(total_bounds[2]),
                "top": float(total_bounds[3]),
            }
            metadata["feature_count"] = int(len(gdf))
            metadata["geom_types"] = [str(t) for t in gdf.geom_type.unique()]
            
            # Construct a vector capability assessment profile
            assessment = {
                "filename": file.filename,
                "vector_info": {
                    "filename": file.filename,
                    "feature_count": int(len(gdf)),
                    "geometry_types": metadata["geom_types"],
                    "crs": crs,
                    "georeferenced": bool(crs),
                    "bounds": [bounds["left"], bounds["bottom"], bounds["right"], bounds["top"]],
                },
                "raster_info": {
                    "filename": file.filename,
                    "shape": [metadata["feature_count"], 0],
                    "bands": 0,
                    "dtype": "vector/geojson",
                    "crs": crs,
                    "georeferenced": bool(crs),
                    "projected": bool(gdf.crs and gdf.crs.is_projected) if gdf.crs else False,
                    "res_m": "Vector (Continuous)",
                    "area_ha": "N/A (Corridor / Project Boundary)",
                    "bounds": [bounds["left"], bounds["bottom"], bounds["right"], bounds["top"]],
                },
                "checklist": [
                    {
                        "module": "Project Corridor",
                        "key": "corridor",
                        "level": "FULL" if crs else "DEGRADED",
                        "message": f"Loaded {metadata['feature_count']} features ({', '.join(metadata['geom_types'])})",
                        "details": [],
                        "note": "Suitable as statutory project boundary for priority engine",
                    },
                    {
                        "module": "CRS Alignment",
                        "key": "crs",
                        "level": "FULL" if crs else "BLOCKED",
                        "message": f"CRS: {crs}" if crs else "Unreferenced vector layer",
                        "details": [],
                        "note": "Requires matching CRS with RGB/LiDAR raster acquisitions",
                    },
                ],
                "summary": {
                    "available_count": 1 if crs else 0,
                    "total_modules": 2,
                    "full_count": 1 if crs else 0,
                    "degraded_count": 0,
                    "blocked_count": 1 if not crs else 0,
                    "summary_text": f"Vector corridor uploaded successfully ({metadata['feature_count']} features)",
                },
            }
            metadata["assessment"] = assessment
        except Exception as e:
            metadata["vector_inspect_error"] = str(e)

    # Persist in SQLite uploads table
    record = create_upload_record(
        upload_id=upload_id,
        filename=file.filename,
        file_type=file_type,
        file_path=str(target_path),
        file_size_bytes=file_size,
        crs=crs,
        bounds=bounds,
        width=width,
        height=height,
        metadata=metadata,
    )
    
    # Return response including top-level assessment for immediate frontend consumption
    record["assessment"] = assessment
    return record


def get_upload_cost_surface(upload_id: str) -> Dict[str, Any]:
    """Retrieves or generates on-the-fly the cost surface for a specific upload."""
    from backend.database import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    conn.close()
    if not row:
        return {"routable": False, "reason": f"Upload record '{upload_id}' not found"}

    file_path = Path(row["file_path"])
    cost_surface_file = UPLOADS_DIR / f"{upload_id}_cost_surface.json"
    if cost_surface_file.exists():
        try:
            with open(cost_surface_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if file_path.suffix.lower() in [".tif", ".tiff", ".img", ".vrt"] and file_path.exists():
        try:
            from upload_cost_surface import build_upload_cost_surface
            cost_surface = build_upload_cost_surface(rgb_path=file_path, name=row["filename"])
            with open(cost_surface_file, "w", encoding="utf-8") as cs_f:
                json.dump(cost_surface, cs_f)
            return cost_surface
        except Exception as err:
            return {"routable": False, "reason": f"Failed generating cost surface: {err}"}

    return {"routable": False, "reason": "Upload is not a valid raster dataset for cost surface generation"}
