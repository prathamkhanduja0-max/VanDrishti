"""
backend/services/upload_service.py
Service for handling file uploads (RGB/LiDAR rasters, boundaries, GeoJSON),
validating spatial metadata with rasterio/geopandas, running automated capability
assessment via assess_upload.py, and persisting upload records in SQLite.
"""

import json
import os
import re
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


def extract_year_and_base(filename: str) -> tuple[Optional[int], str]:
    """
    Extracts a 4-digit year token from a filename and returns (year, base_without_year).
    Examples:
      'OSBS_large_2019.tif' -> (2019, 'OSBS_large')
      'OSBS_large_2018_RGB.tif' -> (2018, 'OSBS_large')
      'TEAK_043_2018.tif' -> (2018, 'TEAK_043')
    """
    stem = Path(filename).stem
    for tag in ["_RGB", "_image", "_rgb", "_img", "_CHM", "_chm", "_DTM", "_dtm", "_DSM", "_dsm", "_hyperspectral"]:
        if stem.endswith(tag):
            stem = stem[:-len(tag)]
            break

    match = re.search(r'(?:\b|_)(19\d{2}|20\d{2})(?:\b|_)', stem)
    if not match:
        return None, stem

    year = int(match.group(1))
    prefix = stem[:match.start()].rstrip('_')
    suffix = stem[match.end():].lstrip('_')
    base_no_year = f"{prefix}_{suffix}".strip('_') if (prefix and suffix) else (prefix or suffix)
    return year, base_no_year


def is_explicit_rgb_stem(stem: str, cand_base: str, cand_year: int) -> bool:
    """
    Checks if a candidate stem is explicitly an RGB image.
    Matches either:
      1. Bare format: f"{cand_base}_{cand_year}"
      2. Explicit RGB tag: f"{cand_base}_{cand_year}_RGB", f"{cand_base}_{cand_year}_rgb",
                           f"{cand_base}_{cand_year}_image", f"{cand_base}_{cand_year}_img"
    """
    stem_lower = stem.lower()
    cand_base_lower = cand_base.lower()
    bare_lower = f"{cand_base_lower}_{cand_year}"
    if stem_lower == bare_lower:
        return True
    for tag in ["_rgb", "_image", "_img"]:
        if stem_lower == f"{bare_lower}{tag}":
            return True
    return False


def is_explicit_chm_stem(stem: str, cand_base: str, cand_year: int) -> bool:
    """
    Checks if a candidate stem is explicitly a CHM raster.
    Must be f"{cand_base}_{cand_year}_CHM" or f"{cand_base}_{cand_year}_chm"
    """
    stem_lower = stem.lower()
    cand_base_lower = cand_base.lower()
    return stem_lower == f"{cand_base_lower}_{cand_year}_chm"


def find_epoch_sibling_rasters(
    filename: str,
    search_dirs: Optional[list[Path]] = None
) -> tuple[Optional[Path], Optional[Path], dict[str, Any]]:
    """
    Finds earlier epoch rasters (rgb_t1, chm_t1) for multi-temporal analysis.
    Finds the closest earlier year to the uploaded raster's year.
    Returns (rgb_t1_path, chm_t1_path, candidate_info).
    """
    year, base_no_year = extract_year_and_base(filename)
    if not year or not base_no_year:
        return None, None, {}

    if search_dirs is None:
        search_dirs = [UPLOADS_DIR, REPO_ROOT / "data"]

    all_files: list[Path] = []
    seen: set[str] = set()
    for d in search_dirs:
        if not d.exists():
            continue
        if d == REPO_ROOT / "data":
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".tif", ".tiff")):
                        full_p = Path(root) / f
                        res = str(full_p.resolve())
                        if res not in seen:
                            all_files.append(full_p)
                            seen.add(res)
        else:
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in [".tif", ".tiff"]:
                    res = str(f.resolve())
                    if res not in seen:
                        all_files.append(f)
                        seen.add(res)

    rgb_candidates_by_year: dict[int, list[Path]] = {}
    chm_candidates_by_year: dict[int, list[Path]] = {}

    for f in all_files:
        cand_year, cand_base = extract_year_and_base(f.name)
        if cand_base == base_no_year and cand_year and cand_year < year:
            stem = f.stem
            if is_explicit_chm_stem(stem, cand_base, cand_year):
                chm_candidates_by_year.setdefault(cand_year, []).append(f)
            elif is_explicit_rgb_stem(stem, cand_base, cand_year):
                rgb_candidates_by_year.setdefault(cand_year, []).append(f)
            else:
                print(f"[VanDrishti Upload] Skipping unrecognized candidate file for epoch {cand_year}: {f.name}")

    earlier_years = sorted(set(list(rgb_candidates_by_year.keys()) + list(chm_candidates_by_year.keys())), reverse=True)
    if not earlier_years:
        return None, None, {}

    best_year = earlier_years[0]
    rgb_matches = rgb_candidates_by_year.get(best_year, [])
    chm_matches = chm_candidates_by_year.get(best_year, [])

    if len(earlier_years) > 1:
        print(
            f"[VanDrishti Upload] Multiple earlier epoch years found for '{base_no_year}' (uploaded: {year}):\n"
            f"  Candidate years: {earlier_years}\n"
            f"  Selecting closest earlier year: {best_year}"
        )
    if len(rgb_matches) > 1:
        print(
            f"[VanDrishti Upload] WARNING: Multiple rgb_t1 candidates for year {best_year}:\n"
            f"  Candidates: {[str(m) for m in rgb_matches]}\n"
            f"  Using first match: {rgb_matches[0]}"
        )
    if len(chm_matches) > 1:
        print(
            f"[VanDrishti Upload] WARNING: Multiple chm_t1 candidates for year {best_year}:\n"
            f"  Candidates: {[str(m) for m in chm_matches]}\n"
            f"  Using first match: {chm_matches[0]}"
        )

    rgb_t1_path = rgb_matches[0] if rgb_matches else None
    chm_t1_path = chm_matches[0] if chm_matches else None

    candidate_info = {
        "uploaded_year": year,
        "t1_year": best_year,
        "base_name": base_no_year,
        "all_earlier_years": earlier_years,
    }

    return rgb_t1_path, chm_t1_path, candidate_info


def find_sibling_raster(filename: str, suffix: str, search_dirs: Optional[list[Path]] = None) -> tuple[Optional[Path], list[str]]:
    """
    Looks for sibling rasters using NEON naming convention (<base>_<suffix>.tif).
    Checks UPLOADS_DIR and repository data directories.
    Returns (selected_path, all_matching_paths).
    """
    base_stem = Path(filename).stem
    for tag in ["_RGB", "_image", "_rgb", "_img"]:
        if base_stem.endswith(tag):
            base_stem = base_stem[:-len(tag)]
            break

    candidate_names = {
        f"{base_stem}_{suffix}.tif",
        f"{base_stem}_{suffix}.tiff",
        f"{base_stem}_{suffix.lower()}.tif",
        f"{base_stem}_{suffix.lower()}.tiff",
    }

    if search_dirs is None:
        search_dirs = [UPLOADS_DIR, REPO_ROOT / "data"]

    matches: list[Path] = []
    seen: set[str] = set()

    for d in search_dirs:
        if not d.exists():
            continue
        # Direct check first (fast O(1))
        for cand in candidate_names:
            cand_p = d / cand
            if cand_p.exists() and cand_p.is_file():
                real_str = str(cand_p.resolve())
                if real_str not in seen:
                    matches.append(cand_p)
                    seen.add(real_str)

        # If searching repository data tree, scan subdirectories if no direct match was found
        if d == REPO_ROOT / "data" and not matches:
            for root, _, files in os.walk(d):
                for f in files:
                    if f in candidate_names:
                        full_p = Path(root) / f
                        real_str = str(full_p.resolve())
                        if real_str not in seen:
                            matches.append(full_p)
                            seen.add(real_str)

    if len(matches) > 1:
        match_strs = [str(m.resolve()) for m in matches]
        print(
            f"[VanDrishti Upload] WARNING: Multiple sibling {suffix} candidates found for '{base_stem}':\n"
            f"  Candidates: {match_strs}\n"
            f"  Using first match: {match_strs[0]}"
        )

    selected = matches[0] if matches else None
    all_str_matches = [str(m.resolve()) for m in matches]
    return selected, all_str_matches


def process_uploaded_file(file: UploadFile, file_type: str = "rgb_t2") -> Dict[str, Any]:
    upload_id = str(uuid.uuid4())
    job_dir = UPLOADS_DIR / upload_id
    job_dir.mkdir(parents=True, exist_ok=True)
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

        # Generate web-viewable PNG preview and WGS84 bounds for Leaflet ImageOverlay
        preview_url = None
        preview_bounds_wgs84 = None
        try:
            preview_res = generate_raster_preview(target_path, upload_id)
            preview_url = preview_res.get("preview_url")
            preview_bounds_wgs84 = preview_res.get("preview_bounds_wgs84")
            metadata["preview_url"] = preview_url
            metadata["preview_bounds_wgs84"] = preview_bounds_wgs84
            if not preview_res.get("has_crs"):
                metadata["preview_note"] = "Raster has no coordinate reference system (CRS) — map overlay disabled."
        except Exception as preview_err:
            metadata["preview_error"] = str(preview_err)

        # Auto-detect sibling CHM / DTM rasters using NEON naming convention (same epoch)
        chm_path, chm_matches = find_sibling_raster(file.filename, "CHM")
        dtm_path, dtm_matches = find_sibling_raster(file.filename, "DTM")

        # Auto-detect earlier epoch rasters (rgb_t1, chm_t1) for multi-temporal analysis
        rgb_t1_path, chm_t1_path, epoch_info = find_epoch_sibling_rasters(file.filename)

        detected_siblings = {}
        if chm_path:
            detected_siblings["chm"] = {
                "filename": chm_path.name,
                "path": str(chm_path.resolve()),
                "all_matches": chm_matches,
                "multiple_matches": len(chm_matches) > 1,
            }
        if dtm_path:
            detected_siblings["dtm"] = {
                "filename": dtm_path.name,
                "path": str(dtm_path.resolve()),
                "all_matches": dtm_matches,
                "multiple_matches": len(dtm_matches) > 1,
            }
        if rgb_t1_path:
            detected_siblings["rgb_t1"] = {
                "filename": rgb_t1_path.name,
                "path": str(rgb_t1_path.resolve()),
                "year": epoch_info.get("t1_year"),
            }
        if chm_t1_path:
            detected_siblings["chm_t1"] = {
                "filename": chm_t1_path.name,
                "path": str(chm_t1_path.resolve()),
                "year": epoch_info.get("t1_year"),
            }
        if epoch_info:
            detected_siblings["epoch_info"] = epoch_info

        metadata["detected_siblings"] = detected_siblings

        # Multi-temporal LiDAR analytics (Forest Health Score & Canopy Degradation)
        health_grid_meta = {"generated": False, "path": None, "cell_count": None, "reason": None}
        degradation_meta = {"generated": False, "path": None, "polygon_count": None, "reason": None}

        if chm_path and chm_t1_path:
            # 1. Forest Health Score
            try:
                from forest_health_score import run_health_score
                health_out_file = job_dir / "health_grid.geojson"
                health_res = run_health_score(
                    chm_t1_path=chm_t1_path,
                    chm_t2_path=chm_path,
                    out_vector=health_out_file,
                )
                cell_count = len(health_res.get("geojson", {}).get("features", []))
                health_grid_meta = {
                    "generated": True,
                    "path": str(health_out_file.resolve()),
                    "cell_count": cell_count,
                    "reason": None,
                }
                print(f"[health] cells={cell_count} -> {health_out_file}")
            except Exception as h_err:
                health_grid_meta["reason"] = str(h_err)
                print(f"[health] skipped: {h_err}")

            # 2. Degradation Loss Polygons
            try:
                from degradation_chm import run_degradation_chm
                deg_out_file = job_dir / "degradation.geojson"
                deg_res = run_degradation_chm(
                    chm_t1_path=chm_t1_path,
                    chm_t2_path=chm_path,
                    out_vector=deg_out_file,
                )
                poly_count = len(deg_res.get("geojson", {}).get("features", []))
                degradation_meta = {
                    "generated": True,
                    "path": str(deg_out_file.resolve()),
                    "polygon_count": poly_count,
                    "reason": None,
                }
                print(f"[degradation] polygons={poly_count} -> {deg_out_file}")
            except Exception as d_err:
                degradation_meta["reason"] = str(d_err)
                print(f"[degradation] skipped: {d_err}")
        else:
            missing_chms = []
            if not chm_path:
                missing_chms.append("chm_t2")
            if not chm_t1_path:
                missing_chms.append("chm_t1")
            skip_msg = f"Missing required multi-temporal CHM rasters ({', '.join(missing_chms)})"
            health_grid_meta["reason"] = skip_msg
            degradation_meta["reason"] = skip_msg
            print(f"[health] skipped: {skip_msg}")
            print(f"[degradation] skipped: {skip_msg}")

        metadata["health_grid"] = health_grid_meta
        metadata["degradation"] = degradation_meta

        # Run automated capability assessment
        try:
            import assess_upload
            assessment = assess_upload.assess_upload(
                target_path,
                chm_path=chm_path,
                dtm_path=dtm_path,
                rgb_t1_path=rgb_t1_path,
                chm_t1_path=chm_t1_path,
                run_detection=True,
            )
            if assessment:
                assessment["preview_url"] = preview_url
                assessment["preview_bounds_wgs84"] = preview_bounds_wgs84
                assessment["detected_siblings"] = detected_siblings
            metadata["assessment"] = assessment
        except Exception as assess_err:
            metadata["assessment_error"] = str(assess_err)

        # Generate routable cost surface for interactive Dijkstra routing
        try:
            from upload_cost_surface import build_upload_cost_surface
            cost_surface = build_upload_cost_surface(
                rgb_path=target_path,
                dtm_path=dtm_path,
                chm_path=chm_path,
                name=file.filename,
            )
            cost_surface_file = UPLOADS_DIR / f"{upload_id}_cost_surface.json"
            with open(cost_surface_file, "w", encoding="utf-8") as cs_f:
                json.dump(cost_surface, cs_f)
            metadata["cost_surface_file"] = str(cost_surface_file)
            metadata["routable"] = cost_surface.get("routable", False)
            metadata["routing_mode"] = cost_surface.get("mode_label")
            metadata["active_cost_terms"] = cost_surface.get("active_terms", [])
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
    
    # Return response including top-level assessment, preview_url, preview_bounds_wgs84 for frontend consumption
    record["assessment"] = assessment
    record["preview_url"] = metadata.get("preview_url")
    record["preview_bounds_wgs84"] = metadata.get("preview_bounds_wgs84")
    return record


def generate_raster_preview(raster_path: Path, upload_id: str) -> Dict[str, Any]:
    """Generates a downsampled, 8-bit normalized PNG preview and computes WGS84 bounds for Leaflet ImageOverlay."""
    import numpy as np
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds

    preview_file = UPLOADS_DIR / f"{upload_id}_preview.png"
    preview_url = f"/api/upload/{upload_id}/preview"

    with rasterio.open(raster_path) as src:
        has_crs = bool(src.crs)
        w, h = src.width, src.height
        count = src.count

        max_dim = 1024
        scale = min(1.0, max_dim / max(w, h))
        out_w = max(1, int(round(w * scale)))
        out_h = max(1, int(round(h * scale)))

        num_bands = min(3, count)
        band_indices = list(range(1, num_bands + 1))

        data = src.read(
            band_indices,
            out_shape=(num_bands, out_h, out_w),
            resampling=Resampling.bilinear,
        )

        norm_bands = []
        for b in range(num_bands):
            arr = data[b].astype(np.float32)
            finite = arr[np.isfinite(arr)]
            if finite.size == 0:
                norm_bands.append(np.zeros((out_h, out_w), dtype=np.uint8))
                continue
            vmax = float(finite.max())
            vmin = float(finite.min())
            if vmax <= 1.5 and vmin >= -0.5:
                norm = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
            elif vmax > 255.0:
                p2, p98 = np.percentile(finite, [2, 98])
                if p98 - p2 < 1e-6:
                    norm = np.zeros((out_h, out_w), dtype=np.uint8)
                else:
                    norm = np.clip((arr - p2) / (p98 - p2) * 255.0, 0, 255).astype(np.uint8)
            else:
                norm = np.clip(arr, 0, 255).astype(np.uint8)
            norm_bands.append(norm)

        if num_bands == 1:
            rgb_arr = np.stack([norm_bands[0], norm_bands[0], norm_bands[0]], axis=-1)
        elif num_bands == 2:
            rgb_arr = np.stack([norm_bands[0], norm_bands[1], norm_bands[0]], axis=-1)
        else:
            rgb_arr = np.stack([norm_bands[0], norm_bands[1], norm_bands[2]], axis=-1)

        img = Image.fromarray(rgb_arr)
        img.save(preview_file, format="PNG")

        preview_bounds_wgs84 = None
        if has_crs:
            try:
                left, bottom, right, top = src.bounds
                minx, miny, maxx, maxy = transform_bounds(src.crs, "EPSG:4326", left, bottom, right, top)
                # Leaflet order: [[south, west], [north, east]] -> [[miny, minx], [maxy, maxx]]
                preview_bounds_wgs84 = [[float(miny), float(minx)], [float(maxy), float(maxx)]]
            except Exception as e:
                print(f"Warning: could not reproject bounds to WGS84: {e}")

        return {
            "preview_url": preview_url,
            "preview_bounds_wgs84": preview_bounds_wgs84,
            "preview_file": str(preview_file),
            "has_crs": has_crs,
        }


def get_upload_preview_path(upload_id: str) -> Optional[Path]:
    """Returns the Path to the PNG preview for an upload ID, generating it if necessary."""
    preview_file = UPLOADS_DIR / f"{upload_id}_preview.png"
    if preview_file.exists():
        return preview_file

    from backend.database import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT file_path FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    conn.close()
    if row and Path(row["file_path"]).exists():
        try:
            res = generate_raster_preview(Path(row["file_path"]), upload_id)
            if Path(res["preview_file"]).exists():
                return Path(res["preview_file"])
        except Exception:
            pass
    return None


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
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            detected_siblings = metadata.get("detected_siblings", {})
            chm_p = Path(detected_siblings["chm"]["path"]) if "chm" in detected_siblings else find_sibling_raster(row["filename"], "CHM")[0]
            dtm_p = Path(detected_siblings["dtm"]["path"]) if "dtm" in detected_siblings else find_sibling_raster(row["filename"], "DTM")[0]

            cost_surface = build_upload_cost_surface(
                rgb_path=file_path,
                dtm_path=dtm_p,
                chm_path=chm_p,
                name=row["filename"]
            )
            with open(cost_surface_file, "w", encoding="utf-8") as cs_f:
                json.dump(cost_surface, cs_f)
            return cost_surface
        except Exception as err:
            return {"routable": False, "reason": f"Failed generating cost surface: {err}"}

    return {"routable": False, "reason": "Upload is not a valid raster dataset for cost surface generation"}


def generate_upload_report_file(upload_id: str, format: str = "pdf") -> tuple[Optional[Path], str, str]:
    """Generates the assessment report (PDF or CSV) on-the-fly for an upload ID."""
    from generate_area_report import generate_area_report
    from backend.database import get_db_connection

    conn = get_db_connection()
    row = conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    conn.close()

    if not row:
        return None, "", ""

    metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    assessment = metadata.get("assessment")
    file_path = Path(row["file_path"])

    if not assessment and file_path.exists():
        try:
            import assess_upload
            detected_siblings = metadata.get("detected_siblings", {})
            chm_p = Path(detected_siblings["chm"]["path"]) if "chm" in detected_siblings else find_sibling_raster(row["filename"], "CHM")[0]
            dtm_p = Path(detected_siblings["dtm"]["path"]) if "dtm" in detected_siblings else find_sibling_raster(row["filename"], "DTM")[0]

            if "rgb_t1" in detected_siblings and "chm_t1" in detected_siblings:
                rgb_t1_p = Path(detected_siblings["rgb_t1"]["path"])
                chm_t1_p = Path(detected_siblings["chm_t1"]["path"])
            else:
                found_rgb_t1, found_chm_t1, _ = find_epoch_sibling_rasters(row["filename"])
                rgb_t1_p = Path(detected_siblings["rgb_t1"]["path"]) if "rgb_t1" in detected_siblings else found_rgb_t1
                chm_t1_p = Path(detected_siblings["chm_t1"]["path"]) if "chm_t1" in detected_siblings else found_chm_t1

            assessment = assess_upload.assess_upload(
                file_path,
                chm_path=chm_p,
                dtm_path=dtm_p,
                rgb_t1_path=rgb_t1_p,
                chm_t1_path=chm_t1_p,
                run_detection=True
            )
        except Exception:
            assessment = None

    if not assessment:
        assessment = {
            "filename": row["filename"],
            "raster_info": {
                "filename": row["filename"],
                "crs": row["crs"],
                "georeferenced": bool(row["crs"]),
                "shape": [row["height"] or 0, row["width"] or 0],
            },
            "summary": {
                "summary_text": f"Upload record {row['filename']}",
                "available_count": 1,
                "total_modules": 6,
            },
            "checklist": [],
        }

    format_lower = format.lower()
    if format_lower not in ["pdf", "csv", "md"]:
        format_lower = "pdf"

    # Always generate freshly to reflect current state
    report_files = generate_area_report(assessment_data=assessment)
    target_path = report_files.get(format_lower)
    stem = report_files.get("stem", Path(row["filename"]).stem)
    filename = f"{stem}_assessment.{format_lower}"
    media_type = "application/pdf" if format_lower == "pdf" else ("text/csv" if format_lower == "csv" else "text/markdown")

    return target_path, filename, media_type


