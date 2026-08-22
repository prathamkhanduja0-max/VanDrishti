"""
upload_cost_surface.py -- VanDrishti

Builds a routable cost surface from an UPLOADED raster set, emitting the same JSON schema
that frontend/src/utils/dijkstra.js already consumes. This is what makes interactive
point-to-point routing work on user data instead of only on the two bundled presets.

Design rules this module follows deliberately:

  1. NO DUPLICATED PHYSICS. Slope, Tobler impedance and ExG normalisation are imported from
     terrain_cost.py, which is the single source of truth. A second copy of the cost formula
     would drift from the first and silently produce routes that disagree with the reported
     ablation numbers.

  2. NO HARDCODED EXTENT OR RESOLUTION. The grid is derived from the uploaded raster's own
     bounds and CRS. Routing resolution is chosen from the node budget, not fixed at 1 m, so
     a 40 m tile and a 1 km tile both stay solvable, and the chosen value is reported.

  3. DEGRADED MODES ARE LABELLED, NOT FAKED. With no DTM there is no slope term, so the
     surface is vegetation-only and says so via active_terms / mode_label. The frontend
     already renders these as cost-term badges. Calling an ExG-only surface
     "terrain-aware" would be the exact overclaim this project has been removing.

  4. UNITS STAY COMPARABLE. In ExG-only mode the base impedance is Tobler's flat-ground
     rate rather than an arbitrary 1.0, so route times remain in hours-per-km and are
     comparable with full terrain-aware runs.

Usage:
    python upload_cost_surface.py --rgb uploads/site.tif \
                                  [--dtm uploads/site_dtm.tif] [--chm uploads/site_chm.tif] \
                                  --out frontend/public/data/upload_cost_surface.json
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from terrain_cost import slope_degrees, tobler_cost, exg_normalised, align_to  # noqa: E402


# Tobler's cost on flat ground (hours per km). Used as the ExG-only baseline so that
# vegetation-only routes report times on the same scale as terrain-aware ones.
FLAT_GROUND_COST = float(tobler_cost(np.array([0.0]))[0])

# Dijkstra on an 8-connected grid is O(N log N); this budget keeps interactive routing
# responsive in the browser. It caps NODES, not area -- resolution adapts to fit.
DEFAULT_NODE_BUDGET = 62_500          # 250 x 250, matching the bundled preset grids
MIN_ROUTING_RES_M = 0.5               # finer than this is navigationally meaningless on foot


def choose_routing_resolution(width_m: float, height_m: float,
                              node_budget: int = DEFAULT_NODE_BUDGET,
                              native_res_m: float = 1.0) -> float:
    """Picks a routing cell size that fits the node budget for this particular extent.

    Returns a resolution in metres. Never finer than the source raster (that would invent
    detail) and never finer than MIN_ROUTING_RES_M (that would only add nodes, not
    navigational information).
    """
    area_m2 = max(width_m * height_m, 1.0)
    res_for_budget = float(np.sqrt(area_m2 / node_budget))
    return float(max(res_for_budget, native_res_m, MIN_ROUTING_RES_M))


def _resample_rgb_to_grid(rgb_path: Path, out_h: int, out_w: int) -> np.ndarray:
    """Reads RGB averaged down onto the routing grid.

    Averaging (not nearest) matters: the routing cell represents the mean traversability of
    that patch of ground, so a single bright pixel should not dictate the cell's cost.
    """
    with rasterio.open(rgb_path) as src:
        bands = min(src.count, 3)
        idx = list(range(1, bands + 1))
        arr = src.read(idx, out_shape=(bands, out_h, out_w), resampling=Resampling.average)
        arr = arr.astype(np.float64)
        if bands == 1:
            arr = np.repeat(arr, 3, axis=0)
        elif bands == 2:
            arr = np.concatenate([arr, arr[:1]], axis=0)
    return arr


def build_upload_cost_surface(
    rgb_path: Path,
    dtm_path: Optional[Path] = None,
    chm_path: Optional[Path] = None,
    w_veg: float = 4.0,
    w_chm: float = 4.0,
    max_slope_deg: float = 45.0,
    node_budget: int = DEFAULT_NODE_BUDGET,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds the frontend-compatible cost surface dict for an uploaded raster set.

    Returns a dict with a `routable` flag. Routing requires a PROJECTED CRS: without one
    there is no metre scale, so slope, Tobler time and route length are all undefined. That
    case is reported honestly rather than routed in pixel units and labelled in metres.
    """
    with rasterio.open(rgb_path) as src:
        crs = src.crs
        has_crs = crs is not None
        is_projected = bool(has_crs and crs.is_projected)
        bounds = src.bounds
        native_res_m = (abs(src.transform.a) + abs(src.transform.e)) / 2.0

    if not is_projected:
        return {
            "routable": False,
            "reason": (
                "Uploaded raster has no projected CRS. Slope, walking time and route length "
                "are undefined without a metre-based coordinate system."
                if not has_crs else
                f"Uploaded raster is in a geographic CRS ({crs}). Reproject to a UTM zone "
                "to enable routing."
            ),
            "crs": str(crs) if has_crs else None,
            "is_projected": False,
        }

    width_m = float(bounds.right - bounds.left)
    height_m = float(bounds.top - bounds.bottom)
    res_m = choose_routing_resolution(width_m, height_m,
                                      node_budget=node_budget,
                                      native_res_m=native_res_m)

    out_w = max(int(round(width_m / res_m)), 2)
    out_h = max(int(round(height_m / res_m)), 2)
    # Recompute the true cell size from the integer grid so reported res matches the grid.
    res_x = width_m / out_w
    res_y = height_m / out_h
    res_m = float((res_x + res_y) / 2.0)

    active_terms = []
    notes = []

    # ---- Vegetation impedance (always available from RGB) --------------------------
    rgb = _resample_rgb_to_grid(rgb_path, out_h, out_w)
    exg_n = exg_normalised(rgb)
    active_terms.append("ExG")

    # ---- Canopy impedance from CHM, if supplied ------------------------------------
    chm_n = None
    if chm_path is not None and Path(chm_path).exists():
        ref_profile = {
            "height": out_h, "width": out_w, "crs": crs,
            "transform": rasterio.transform.from_bounds(
                bounds.left, bounds.bottom, bounds.right, bounds.top, out_w, out_h),
        }
        chm = align_to(str(chm_path), ref_profile, resampling=Resampling.average)
        chm = np.where(np.isfinite(chm), chm, 0.0)
        chm_max = float(np.nanpercentile(chm, 98))
        if chm_max > 1e-6:
            chm_n = np.clip(chm / chm_max, 0.0, 1.0)
            active_terms.append("CHM")
        else:
            notes.append("CHM supplied but contains no usable height range; term skipped.")

    # ---- Terrain impedance from DTM, if supplied -----------------------------------
    slope_diag = None
    if dtm_path is not None and Path(dtm_path).exists():
        ref_profile = {
            "height": out_h, "width": out_w, "crs": crs,
            "transform": rasterio.transform.from_bounds(
                bounds.left, bounds.bottom, bounds.right, bounds.top, out_w, out_h),
        }
        dtm = align_to(str(dtm_path), ref_profile, resampling=Resampling.bilinear)
        if np.isnan(dtm).any():
            dtm = np.where(np.isnan(dtm), np.nanmedian(dtm), dtm)
        slope = slope_degrees(dtm, res_x, res_y)
        base = tobler_cost(slope, max_slope_deg=max_slope_deg)
        active_terms.append("Slope")
        slope_diag = {
            "slope_deg_p50": float(np.nanpercentile(slope, 50)),
            "slope_deg_p95": float(np.nanpercentile(slope, 95)),
            "slope_deg_max": float(np.nanmax(slope)),
            "relief_m": float(np.nanmax(dtm) - np.nanmin(dtm)),
        }
        if slope_diag["slope_deg_p95"] < 2.0:
            notes.append(
                "Site is nearly flat (p95 slope < 2 deg); terrain will barely alter the "
                "route here. That is a property of the site, not a routing failure.")
    else:
        # ExG-only: hold the base at Tobler's flat-ground rate so times stay in h/km.
        base = np.full((out_h, out_w), FLAT_GROUND_COST, dtype=np.float64)
        notes.append(
            "No DTM supplied: slope term disabled. Impedance is vegetation-only and is a "
            "weak proxy for traversability; route times are uncalibrated.")

    # ---- Combine -------------------------------------------------------------------
    veg_factor = 1.0 + w_veg * exg_n
    if chm_n is not None:
        veg_factor = veg_factor + w_chm * chm_n
    cost = base * veg_factor

    mode_label = "terrain-aware" if "Slope" in active_terms else (
        "canopy-aware (no terrain)" if "CHM" in active_terms else "optical proxy only")

    wgs84 = transform_bounds(crs, "EPSG:4326",
                             bounds.left, bounds.bottom, bounds.right, bounds.top)

    return {
        "routable": True,
        "name": name or Path(rgb_path).stem,
        "crs": str(crs),
        "is_projected": True,
        "active_terms": active_terms,
        "mode_label": mode_label,
        "res_m": round(res_m, 4),
        "native_res_m": round(native_res_m, 4),
        "shape": [out_h, out_w],
        "n_nodes": int(out_h * out_w),
        "utm_bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
        "wgs84_bounds": [wgs84[0], wgs84[1], wgs84[2], wgs84[3]],
        "cost_units": "hours per km (Tobler-derived)",
        "weights": {"w_veg": w_veg, "w_chm": w_chm if chm_n is not None else None},
        "diagnostics": {
            "cost_min": float(np.nanmin(cost)),
            "cost_p50": float(np.nanpercentile(cost, 50)),
            "cost_max": float(np.nanmax(cost)),
            **(slope_diag or {}),
        },
        "notes": notes,
        "cost_grid": np.asarray(cost, dtype=np.float32).tolist(),
    }


def main():
    ap = argparse.ArgumentParser(description="Build routable cost surface from an upload")
    ap.add_argument("--rgb", required=True)
    ap.add_argument("--dtm", default=None)
    ap.add_argument("--chm", default=None)
    ap.add_argument("--w-veg", type=float, default=4.0)
    ap.add_argument("--w-chm", type=float, default=4.0)
    ap.add_argument("--node-budget", type=int, default=DEFAULT_NODE_BUDGET)
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    surf = build_upload_cost_surface(
        rgb_path=Path(args.rgb),
        dtm_path=Path(args.dtm) if args.dtm else None,
        chm_path=Path(args.chm) if args.chm else None,
        w_veg=args.w_veg, w_chm=args.w_chm,
        node_budget=args.node_budget, name=args.name,
    )

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(surf, f)

    if surf.get("routable"):
        print(f"cost surface -> {out_p}")
        print(f"  mode      : {surf['mode_label']}  terms={surf['active_terms']}")
        print(f"  grid      : {surf['shape'][0]}x{surf['shape'][1]} @ {surf['res_m']} m "
              f"({surf['n_nodes']:,} nodes)")
        for n in surf["notes"]:
            print(f"  note      : {n}")
    else:
        print(f"NOT ROUTABLE: {surf['reason']}")


if __name__ == "__main__":
    main()
