"""
assess_upload.py -- VanDrishti
Assesses an uploaded raster dataset, inspects its georeferencing, CRS, resolution,
and dimensions, and runs the module capability assessment by importing config_loader.py.

Rules enforced:
  - No CRS: detection runs (pixel space), area/distance/coords reported as UNAVAILABLE.
  - Geographic CRS (EPSG:4326): warns that metric ops need projected CRS; suggests UTM zone.
  - No DTM: routing DEGRADED, slope disabled.
  - No CHM: routing uses ExG fallback (DEGRADED); health score BLOCKED.
  - Single date only: degradation BLOCKED (needs two acquisition dates).
"""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Dict, Any, Optional

import numpy as np
import rasterio
from rasterio.transform import xy
from shapely.geometry import Point, mapping
import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader


def get_suggested_utm_epsg(lon: float, lat: float) -> int:
    """Calculates appropriate WGS84 UTM EPSG code from longitude and latitude."""
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def inspect_single_raster(raster_path: Path) -> Dict[str, Any]:
    """Inspects metadata, CRS, resolution, dimensions, and ground area of a raster."""
    if not raster_path.exists():
        return {
            "declared": True,
            "exists": False,
            "path": str(raster_path),
            "error": "File does not exist",
        }

    try:
        with rasterio.open(raster_path) as src:
            has_crs = src.crs is not None
            is_projected = bool(has_crs and src.crs.is_projected)
            
            width = src.width
            height = src.height
            bands = src.count
            dtype = str(src.dtypes[0])
            
            # Pixel resolution
            res_x = abs(src.transform.a)
            res_y = abs(src.transform.e)
            
            bounds = src.bounds
            
            # Ground area calculation
            if is_projected:
                area_m2 = (bounds.right - bounds.left) * (bounds.top - bounds.bottom)
                area_ha = area_m2 / 10000.0
                area_km2 = area_m2 / 1000000.0
                res_m = round((res_x + res_y) / 2.0, 3)
                center_x = (bounds.left + bounds.right) / 2.0
                center_y = (bounds.bottom + bounds.top) / 2.0
                suggested_utm = None
                bbox = [bounds.left, bounds.bottom, bounds.right, bounds.top]
            elif has_crs:  # Geographic CRS (e.g. EPSG:4326)
                res_m = "UNAVAILABLE (Geographic Degrees)"
                center_lon = (bounds.left + bounds.right) / 2.0
                center_lat = (bounds.bottom + bounds.top) / 2.0
                center_x, center_y = center_lon, center_lat
                suggested_utm = get_suggested_utm_epsg(center_lon, center_lat)
                # Approximate area via degree conversion at center latitude
                lat_rad = np.radians(center_lat)
                m_per_deg_lat = 111320.0
                m_per_deg_lon = 111320.0 * np.cos(lat_rad)
                width_m = abs(bounds.right - bounds.left) * m_per_deg_lon
                height_m = abs(bounds.top - bounds.bottom) * m_per_deg_lat
                area_m2 = width_m * height_m
                area_ha = area_m2 / 10000.0
                area_km2 = area_m2 / 1000000.0
                bbox = [bounds.left, bounds.bottom, bounds.right, bounds.top]
            else:  # No CRS
                res_m = "UNAVAILABLE"
                area_m2 = "UNAVAILABLE"
                area_ha = "UNAVAILABLE"
                area_km2 = "UNAVAILABLE"
                center_x, center_y = width / 2.0, height / 2.0
                suggested_utm = None
                bbox = [0, 0, width, height]

            return {
                "declared": True,
                "exists": True,
                "path": str(raster_path),
                "filename": raster_path.name,
                "shape": [height, width],
                "bands": bands,
                "dtype": dtype,
                "crs": str(src.crs) if has_crs else None,
                "georeferenced": has_crs,
                "projected": is_projected,
                "res_m": res_m,
                "res_raw": [res_x, res_y],
                "area_m2": round(area_m2, 1) if isinstance(area_m2, (int, float)) else area_m2,
                "area_ha": round(area_ha, 2) if isinstance(area_ha, (int, float)) else area_ha,
                "area_km2": round(area_km2, 4) if isinstance(area_km2, (int, float)) else area_km2,
                "bounds": [round(b, 6) for b in bbox],
                "center": [round(center_x, 6), round(center_y, 6)],
                "suggested_utm_epsg": suggested_utm,
            }
    except Exception as e:
        return {
            "declared": True,
            "exists": True,
            "path": str(raster_path),
            "filename": raster_path.name,
            "error": str(e),
        }


def _normalize_to_8bit(arr: np.ndarray) -> np.ndarray:
    """Rescales arbitrary-dtype imagery (float reflectance, uint16, etc.) to a 0-255 range.

    The ExG brightness gate assumes 8-bit digital numbers. Uploaded rasters are commonly
    float32 reflectance (0-1) or uint16 (0-65535); without rescaling the gate either
    rejects every pixel (float) or accepts every pixel (uint16), producing a silent
    zero-detection or a saturated false-positive field.
    """
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr)
    vmax = float(finite.max())
    vmin = float(finite.min())
    if vmax <= 1.5 and vmin >= -0.5:          # float reflectance 0-1
        scale = 255.0
        return np.clip(arr * scale, 0, 255)
    if vmax > 255.0:                           # uint16 / int32 imagery
        p2, p98 = np.percentile(finite, [2, 98])
        if p98 - p2 < 1e-6:
            return np.zeros_like(arr)
        return np.clip((arr - p2) / (p98 - p2) * 255.0, 0, 255)
    return np.clip(arr, 0, 255)                # already 8-bit-like


def run_fast_tree_detection(raster_path: Path, max_dim: int = 1500,
<<<<<<< HEAD
                            render_cap: int = 3000) -> Dict[str, Any]:
=======
                            render_cap: int = 3000,
                            min_crown_sep_m: float = 2.0,
                            exg_percentile: float = 65.0,
                            min_green_dn: float = 30.0) -> Dict[str, Any]:
>>>>>>> main
    """Fast optical crown-peak preview (ExG local maxima) for uploaded rasters.

    NOTE: This is NOT the DeepForest/YOLOv8 detector used by the main pipeline. It is an
    unsupervised greenness-peak heuristic intended only for instant upload feedback.
    Counts are not calibrated crown counts and carry no validation.

<<<<<<< HEAD
=======
    Peak separation is specified in GROUND METRES (`min_crown_sep_m`) and converted to a
    pixel window using the raster's own resolution, matching the 2 m centroid dedup used by
    the main detection pipeline. A fixed pixel window would make the count a function of
    pixel size rather than of the forest: the same scene resampled 0.1 m -> 0.4 m swings the
    raw count by well over an order of magnitude.

    LIMITATION: ground-referencing the window reduces but does not remove resolution
    sensitivity. Measured on one OSBS scene resampled 0.1/0.2/0.4 m, the count spread falls
    from ~26x (fixed 5 px window) to ~2.4x. The residual comes from resampling smoothing the
    ExG field, which shifts the percentile threshold and suppresses weak maxima. Counts from
    rasters of different ground resolution are therefore NOT directly comparable, and
    `resolution_normalized` denotes the window basis only, not a validated invariance claim.

>>>>>>> main
    `render_cap` limits how many features are serialised to GeoJSON for browser rendering,
    but the full peak count is always reported separately so the number shown to the user
    is never a truncation artifact. Retained peaks are selected by descending ExG strength
    (not raster row order) so the sample is spatially unbiased across the scene.
    """
    with rasterio.open(raster_path) as src:
        has_crs = src.crs is not None
        is_projected = bool(has_crs and src.crs.is_projected)
        crs = src.crs
        transform = src.transform
        count = src.count
<<<<<<< HEAD
=======
        native_res_m = (abs(transform.a) + abs(transform.e)) / 2.0 if is_projected else None
>>>>>>> main

        # Read RGB bands
        if count >= 3:
            rgb = src.read([1, 2, 3]).astype(np.float32)
        elif count == 1:
            band1 = src.read(1).astype(np.float32)
            rgb = np.stack([band1, band1, band1], axis=0)
        else:
            return {"count": 0, "count_rendered": 0, "features": [], "geojson": None,
<<<<<<< HEAD
                    "truncated": False, "method": "exg_peak_heuristic"}
=======
                    "truncated": False, "method": "exg_peak_heuristic",
                    "resolution_normalized": False}
>>>>>>> main

        # Rescale to 8-bit-equivalent so the brightness gate is dtype-independent
        rgb = _normalize_to_8bit(rgb)

        # Subsample if massive for instant interactive response
        h, w = rgb.shape[1], rgb.shape[2]
        step = 1
        if max(h, w) > max_dim:
            step = int(np.ceil(max(h, w) / max_dim))
            rgb = rgb[:, ::step, ::step]

        # Peak-separation window in ground metres -> pixels at the working resolution.
        if native_res_m and native_res_m > 0:
            working_res_m = native_res_m * step
            win = int(round(min_crown_sep_m / working_res_m))
            win = max(3, win + 1 - (win % 2))     # odd, >= 3
            scale_invariant = True
        else:
            win = 5                                # unprojected: no ground scale available
            working_res_m = None
            scale_invariant = False

        r, g, b = rgb[0], rgb[1], rgb[2]
        # Excess Green Index (ExG = 2G - R - B)
        exg = 2.0 * g - r - b

        # Local peak detection for crown centers
        from scipy.ndimage import maximum_filter
<<<<<<< HEAD
        threshold = np.percentile(exg[exg > 0], 65) if np.any(exg > 0) else 10.0
        local_max = maximum_filter(exg, size=5) == exg
        peaks = (exg > threshold) & local_max & (g > 30.0)
=======
        threshold = np.percentile(exg[exg > 0], exg_percentile) if np.any(exg > 0) else 10.0
        local_max = maximum_filter(exg, size=win) == exg
        peaks = (exg > threshold) & local_max & (g > min_green_dn)
>>>>>>> main

        y_indices, x_indices = np.where(peaks)
        total_peaks = int(y_indices.size)

        # Rank by ExG strength so any cap keeps the strongest peaks scene-wide,
        # instead of np.where's row-major order which biases to the top of the image.
        if total_peaks > render_cap:
            strengths = exg[y_indices, x_indices]
            keep = np.argsort(strengths)[::-1][:render_cap]
            keep.sort()
            y_indices, x_indices = y_indices[keep], x_indices[keep]
            truncated = True
        else:
            truncated = False

        features = []
        for i, (py_sub, px_sub) in enumerate(zip(y_indices, x_indices), 1):
            px = px_sub * step
            py = py_sub * step
            conf = float(np.clip((exg[py_sub, px_sub] - threshold) / (threshold + 1e-5), 0.50, 0.98))

            if has_crs:
                gx, gy = xy(transform, py, px)
            else:
                gx, gy = px, py

            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(gx, 7), round(gy, 7)]
                },
                "properties": {
                    "tree_id": i,
                    "exg_strength": round(conf, 3),
                    "pixel_x": int(px),
                    "pixel_y": int(py),
                    "georeferenced": has_crs
                }
            }
            features.append(feat)

        geojson_data = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": str(crs) if has_crs else "UNREFERENCED"}
            },
            "features": features
        }
        return {
            "count": total_peaks,
            "count_rendered": len(features),
            "truncated": truncated,
            "method": "exg_peak_heuristic",
<<<<<<< HEAD
=======
            "resolution_normalized": scale_invariant,
            "params": {
                "min_crown_sep_m": min_crown_sep_m,
                "working_res_m": round(working_res_m, 4) if working_res_m else None,
                "peak_window_px": win,
                "exg_percentile": exg_percentile,
                "min_green_dn": min_green_dn,
                "subsample_step": step,
            },
>>>>>>> main
            "geojson": geojson_data,
        }


def _detection_message(det_status: str, det: Dict[str, Any]) -> str:
    """Builds an honest detection summary line for the frontend checklist."""
    if det_status == "BLOCKED":
        return "Missing valid RGB raster"
    if det.get("error"):
        return f"Preview failed: {det['error']}"
    total = det.get("count", 0)
    method = det.get("method", "exg_peak_heuristic")

    if method == "deepforest":
        msg = f"{total:,} crowns detected via DeepForest (NEON-pretrained RetinaNet)"
        dropped = det.get("filters", {}).get("size_dropped", 0) + det.get("filters", {}).get("dedup_dropped", 0)
        if dropped > 0:
            msg += f" ({dropped} filtered by crown size/dedup)"
        return msg

    if total == 0:
        return "No vegetation peaks found (check imagery bands / vegetation cover)"
    msg = f"{total:,} greenness peaks (fast optical preview, not AI-validated)"
    if det.get("truncated"):
        msg += f" — {det.get('count_rendered', 0):,} strongest shown on map"
    if det.get("fallback_reason"):
        msg += f" (ExG fallback: {det['fallback_reason']})"
    return msg


def assess_upload(
    raster_path: Path,
    chm_path: Optional[Path] = None,
    dtm_path: Optional[Path] = None,
    rgb_t1_path: Optional[Path] = None,
    chm_t1_path: Optional[Path] = None,
    run_detection: bool = True
) -> Dict[str, Any]:
    """Generates the full capability report for the uploaded raster."""
    primary_info = inspect_single_raster(raster_path)
    
    # Construct rasters manifest compatible with config_loader.MODULE_REQUIREMENTS
    rasters = {
        "rgb_t2": primary_info,
        "chm_t2": inspect_single_raster(chm_path) if chm_path else {"declared": False, "exists": False},
        "dtm": inspect_single_raster(dtm_path) if dtm_path else {"declared": False, "exists": False},
        "rgb_t1": inspect_single_raster(rgb_t1_path) if rgb_t1_path else {"declared": False, "exists": False},
        "chm_t1": inspect_single_raster(chm_t1_path) if chm_t1_path else {"declared": False, "exists": False},
        "dsm": {"declared": False, "exists": False}
    }

    # Reuse config_loader.assess directly (No duplication)
    capabilities = config_loader.assess(rasters)
    warnings = config_loader.crs_warnings(rasters)

    # Calculate modules summary count
    full_count = sum(1 for c in capabilities.values() if c["level"] == "FULL")
    deg_count = sum(1 for c in capabilities.values() if c["level"] == "DEGRADED")
    blocked_count = sum(1 for c in capabilities.values() if c["level"] == "BLOCKED")
    total_modules = len(capabilities)
    available_count = full_count + deg_count

    # Run detection on the uploaded image if valid: Try DeepForest FIRST, then fallback to ExG
    detection_results = {"count": 0, "features": []}
    if run_detection and primary_info.get("exists") and not primary_info.get("error"):
        deepforest_ran = False
        try:
            from upload_detect_deepforest import detect_upload_deepforest
            df_res = detect_upload_deepforest(raster_path)
            if df_res.get("ok"):
                detection_results = df_res
                deepforest_ran = True
            else:
                fallback_reason = df_res.get("detail") or df_res.get("reason") or "DeepForest unavailable"
        except Exception as df_err:
            fallback_reason = str(df_err)

        if not deepforest_ran:
            try:
                detection_results = run_fast_tree_detection(raster_path)
                if "fallback_reason" in locals():
                    detection_results["fallback_reason"] = fallback_reason
            except Exception as det_err:
                detection_results = {"count": 0, "error": str(det_err), "method": "failed"}

    # Structured checklist for frontend rendering
    checklist = []
    
    # 1. Detection
    det_cap = capabilities.get("detection", {})
    det_status = det_cap.get("level", "BLOCKED")
    checklist.append({
        "module": "Tree Detection",
        "key": "detection",
        "level": det_status,
        "message": _detection_message(det_status, detection_results),
        "details": det_cap.get("lost_capability", []),
        "note": det_cap.get("note", "")
    })

    # 2. Routing
    route_cap = capabilities.get("routing", {})
    route_status = route_cap.get("level", "BLOCKED")
    route_msg = "Slope-aware Held-Karp TSP route" if route_status == "FULL" else "No DTM/CHM: slope disabled, using 2D optical ExG impedance"
    checklist.append({
        "module": "Patrol Routing",
        "key": "routing",
        "level": route_status,
        "message": route_msg,
        "details": route_cap.get("lost_capability", []),
        "note": route_cap.get("note", "")
    })

    # 3. Verification Priority
    prio_cap = capabilities.get("priority", {})
    prio_status = prio_cap.get("level", "BLOCKED")
    checklist.append({
        "module": "Priority Audit",
        "key": "priority",
        "level": prio_status,
        "message": "Confidence proxy tagging" if prio_status != "BLOCKED" else "Corridor geometry missing",
        "details": prio_cap.get("lost_capability", []),
        "note": prio_cap.get("note", "")
    })

    # 4. Degradation
    deg_cap = capabilities.get("degradation", {})
    deg_status = deg_cap.get("level", "BLOCKED")
    checklist.append({
        "module": "Canopy Degradation",
        "key": "degradation",
        "level": deg_status,
        "message": "Multi-temporal loss differencing" if deg_status == "FULL" else "Needs two acquisition dates (single epoch uploaded)",
        "details": deg_cap.get("lost_capability", []),
        "note": deg_cap.get("note", "")
    })

    # 5. Forest Health Score
    health_cap = capabilities.get("health_score", {})
    health_status = health_cap.get("level", "BLOCKED")
    checklist.append({
        "module": "Forest Health Score",
        "key": "health_score",
        "level": health_status,
        "message": "25m composite grid scoring" if health_status == "FULL" else "Needs multi-temporal LiDAR CHMs",
        "details": health_cap.get("lost_capability", []),
        "note": health_cap.get("note", "")
    })

    # 6. Fire Risk
    fire_cap = capabilities.get("fire", {})
    checklist.append({
        "module": "Fire Hotspots",
        "key": "fire",
        "level": fire_cap.get("level", "FULL"),
        "message": "NASA FIRMS live satellite feed (VIIRS 375m)",
        "details": [],
        "note": fire_cap.get("note", "")
    })

    summary_text = f"{available_count} of {total_modules} modules available for this dataset"

    report = {
        "filename": primary_info.get("filename", raster_path.name),
        "raster_info": primary_info,
        "capabilities": capabilities,
        "checklist": checklist,
        "summary": {
            "available_count": available_count,
            "total_modules": total_modules,
            "full_count": full_count,
            "degraded_count": deg_count,
            "blocked_count": blocked_count,
            "summary_text": summary_text,
        },
        "warnings": warnings,
        "detection_results": {
            "count": detection_results.get("count", 0),
<<<<<<< HEAD
            "count_rendered": detection_results.get("count_rendered", 0),
            "truncated": detection_results.get("truncated", False),
            "method": detection_results.get("method", "exg_peak_heuristic"),
=======
            "raw_count": detection_results.get("raw_count", detection_results.get("count", 0)),
            "count_rendered": detection_results.get("count_rendered", detection_results.get("count", 0)),
            "truncated": detection_results.get("truncated", False),
            "method": detection_results.get("method", "exg_peak_heuristic"),
            "fallback_reason": detection_results.get("fallback_reason"),
            "resolution_normalized": detection_results.get("resolution_normalized", False),
            "filters": detection_results.get("filters", {}),
            "detector_params": detection_results.get("detector_params", {}),
            "notes": detection_results.get("notes", []),
            "params": detection_results.get("params", {}),
>>>>>>> main
            "error": detection_results.get("error"),
            "geojson": detection_results.get("geojson")
        }
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="VanDrishti Upload Capability Assessment")
    parser.add_argument("raster", help="Path to uploaded raster GeoTIFF")
    parser.add_argument("--chm", default=None, help="Optional CHM raster path")
    parser.add_argument("--dtm", default=None, help="Optional DTM raster path")
    parser.add_argument("--rgb-t1", default=None, help="Optional earlier epoch RGB raster path")
    parser.add_argument("--chm-t1", default=None, help="Optional earlier epoch CHM raster path")
    parser.add_argument("--out-json", default=None, help="Path to save output JSON report")
    parser.add_argument("--out-geojson", default=None, help="Path to save detection GeoJSON")
    args = parser.parse_args()

    raster_path = Path(args.raster)
    if not raster_path.is_absolute():
        raster_path = REPO_ROOT / raster_path

    chm_p = Path(args.chm) if args.chm else None
    dtm_p = Path(args.dtm) if args.dtm else None
    rgb1_p = Path(args.rgb_t1) if args.rgb_t1 else None
    chm1_p = Path(args.chm_t1) if args.chm_t1 else None

    report = assess_upload(
        raster_path=raster_path,
        chm_path=chm_p,
        dtm_path=dtm_p,
        rgb_t1_path=rgb1_p,
        chm_t1_path=chm1_p,
        run_detection=True
    )

    # Save output JSON if requested or to public data
    if args.out_json:
        out_p = Path(args.out_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Report JSON written to: {out_p}")

    if args.out_geojson and report.get("detection_results", {}).get("geojson"):
        out_geo = Path(args.out_geojson)
        out_geo.parent.mkdir(parents=True, exist_ok=True)
        with open(out_geo, "w", encoding="utf-8") as f:
            json.dump(report["detection_results"]["geojson"], f, indent=2)
        print(f"Detection GeoJSON written to: {out_geo}")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
