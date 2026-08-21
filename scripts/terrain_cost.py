"""
terrain_cost.py  -- VanDrishti
Makes the "terrain-aware routing" claim actually true.

Your current impedance is:
      cost = 1.0 + 4.0 * ExG_norm
which is CANOPY DENSITY only. No elevation, no slope. Any reviewer who knows
NEON will spot that immediately.

This module builds:
      cost = terrain_cost(slope) * (1.0 + w_veg * ExG_norm)

where terrain_cost comes from Tobler's hiking function -- a published,
citable model of walking speed vs slope:

      v(S) = 6 * exp(-3.5 * |tan(S) + 0.05|)      [km/h]

The +0.05 offset means fastest walking is on a slight DOWNHILL (~-2.9 deg),
not flat -- which is empirically correct and a nice detail to mention.

Cost is time-per-metre, so Dijkstra now minimises TRAVEL TIME, not distance.
Report your route in BOTH minutes and metres after this change.

Usage:
    python terrain_cost.py --dtm data/raw/neon/osbs_dtm.tif \
                           --rgb data/raw/neon/osbs_2019.tif \
                           --out results/gis/cost_surface.tif
"""

import argparse

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject


# --------------------------------------------------------------------------
# Slope
# --------------------------------------------------------------------------
def slope_degrees(dtm, cellsize_x, cellsize_y):
    """Slope in degrees via central differences (Horn-style, simplified).

    cellsize_x / cellsize_y must be in the SAME units as the DTM z-values
    (metres for NEON). np.gradient handles the edges with one-sided diffs.
    """
    dz_dy, dz_dx = np.gradient(dtm, cellsize_y, cellsize_x)
    slope_rad = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))
    return np.degrees(slope_rad)


# --------------------------------------------------------------------------
# Tobler
# --------------------------------------------------------------------------
def tobler_cost(slope_deg, max_slope_deg=45.0, impassable_cost=1e6):
    """Time-per-metre cost surface from slope.

    Returns cost in hours-per-metre (relative units are all Dijkstra needs).
    Slopes beyond max_slope_deg are treated as effectively impassable so the
    router refuses cliffs instead of "cleverly" scaling them.
    """
    slope_deg = np.asarray(slope_deg, dtype=np.float64)
    tan_s = np.tan(np.radians(slope_deg))

    speed_kmh = 6.0 * np.exp(-3.5 * np.abs(tan_s + 0.05))
    speed_kmh = np.maximum(speed_kmh, 1e-6)  # guard div-by-zero

    cost = 1.0 / speed_kmh                    # hours per km, monotonic in slope
    cost = np.where(slope_deg > max_slope_deg, impassable_cost, cost)
    return cost


# --------------------------------------------------------------------------
# ExG
# --------------------------------------------------------------------------
def exg_normalised(rgb):
    """Excess Green, min-max normalised to [0,1].

    rgb: (3, H, W) array, any dtype. Uses chromatic coordinates so that
    brightness variation doesn't leak into the index.
    """
    r, g, b = rgb[0].astype(np.float64), rgb[1].astype(np.float64), rgb[2].astype(np.float64)
    total = r + g + b
    total[total == 0] = 1.0

    rn, gn, bn = r / total, g / total, b / total
    exg = 2.0 * gn - rn - bn                  # theoretical range [-1, 2]

    lo, hi = np.nanpercentile(exg, [2, 98])   # percentile clip = outlier-robust
    if hi - lo < 1e-9:
        return np.zeros_like(exg)
    return np.clip((exg - lo) / (hi - lo), 0.0, 1.0)


# --------------------------------------------------------------------------
# Align rasters
# --------------------------------------------------------------------------
def align_to(src_path, ref_profile, resampling=Resampling.bilinear, band=1):
    """Reproject/resample one band of src onto the reference grid.

    NEON DTM is usually 1 m while the RGB orthomosaic is 0.1 m -- they will
    NOT line up without this step. Silent misalignment here produces a cost
    surface that looks fine and is completely wrong.
    """
    with rasterio.open(src_path) as src:
        dst = np.zeros((ref_profile["height"], ref_profile["width"]), dtype=np.float64)
        reproject(
            source=rasterio.band(src, band),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            resampling=resampling,
        )
    return dst


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build_cost_surface(dtm_path, rgb_path, w_veg=4.0, target_res=1.0,
                       max_slope_deg=45.0, verbose=True):
    """Returns (cost, profile, diagnostics).

    The grid is defined by the DTM (typically 1 m) because routing at 0.1 m
    would give you 6.25 million nodes for no navigational benefit.
    """
    with rasterio.open(dtm_path) as d:
        profile = d.profile.copy()
        dtm = d.read(1).astype(np.float64)
        nodata = d.nodata
        res_x, res_y = d.res

    if nodata is not None:
        dtm = np.where(dtm == nodata, np.nan, dtm)
    # fill small gaps so gradient doesn't propagate NaN across the tile
    if np.isnan(dtm).any():
        dtm = np.where(np.isnan(dtm), np.nanmedian(dtm), dtm)

    slope = slope_degrees(dtm, res_x, res_y)
    t_cost = tobler_cost(slope, max_slope_deg=max_slope_deg)

    # RGB resampled onto the DTM grid
    with rasterio.open(rgb_path) as s:
        bands = [align_to(rgb_path, profile, band=i) for i in (1, 2, 3)]
    rgb = np.stack(bands, axis=0)
    exg_n = exg_normalised(rgb)

    cost = t_cost * (1.0 + w_veg * exg_n)

    profile.update(dtype="float32", count=1, compress="lzw", nodata=None)

    diag = {
        "grid_shape": cost.shape,
        "n_nodes": int(cost.size),
        "slope_deg_p50": float(np.nanpercentile(slope, 50)),
        "slope_deg_p95": float(np.nanpercentile(slope, 95)),
        "slope_deg_max": float(np.nanmax(slope)),
        "cost_min": float(np.nanmin(cost)),
        "cost_p50": float(np.nanpercentile(cost, 50)),
        "cost_max": float(np.nanmax(cost)),
    }

    if verbose:
        print("\n--- Terrain cost surface ---")
        for k, v in diag.items():
            print(f"  {k:<18}: {v}")
        if diag["slope_deg_p95"] < 2.0:
            print(
                "\n  NOTE: this site is nearly flat (p95 slope < 2 deg).\n"
                "  Terrain will barely change the route here -- that is a\n"
                "  legitimate FINDING, not a bug. Say so in the report, and\n"
                "  consider validating on a site with real relief.\n"
            )
        print()

    return cost.astype(np.float32), profile, diag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtm", required=True, help="NEON DTM GeoTIFF")
    ap.add_argument("--rgb", required=True, help="NEON RGB orthomosaic GeoTIFF")
    ap.add_argument("--out", required=True, help="output cost surface GeoTIFF")
    ap.add_argument("--w-veg", type=float, default=4.0)
    ap.add_argument("--max-slope", type=float, default=45.0)
    args = ap.parse_args()

    cost, profile, diag = build_cost_surface(
        args.dtm, args.rgb, w_veg=args.w_veg, max_slope_deg=args.max_slope
    )

    with rasterio.open(args.out, "w", **profile) as dst:
        dst.write(cost, 1)
    print(f"wrote cost surface -> {args.out}")


if __name__ == "__main__":
    main()
