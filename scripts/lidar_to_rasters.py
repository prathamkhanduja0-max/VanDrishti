"""
lidar_to_rasters.py  -- VanDrishti

The recon found NO DTM under data/raw/, and the only CHM rasters cover 40 m
tiles -- none for OSBS_large_2019.tif (250 m). But .laz point clouds ARE
present, and both products can be derived from them.

Produces, on a grid aligned to a reference raster:
    DTM  = ground surface elevation      (from classification == 2)
    DSM  = highest return per cell       (canopy top)
    CHM  = DSM - DTM                     (canopy height above ground)

Why this matters for VanDrishti:
  - DTM makes terrain_cost.py work -> the "terrain-aware" claim becomes true.
  - CHM is a FAR better routing impedance than ExG. ExG says "this pixel is
    green"; CHM says "there is 18 m of tree here". A ranger cannot walk
    through 18 m of tree. Green grass and dense canopy look similar in ExG
    and completely different in CHM.
  - CHM also enables real degradation detection (height loss cannot be caused
    by a different sun angle) and a structural-diversity term for the health
    score.

Requires: laspy[laz]  (pip install "laspy[laz]" scipy)

Usage:
    python scripts/lidar_to_rasters.py \
        --laz data/raw/neon/large/OSBS_large.laz \
        --ref data/raw/neon/large/OSBS_large_2019.tif \
        --res 1.0 \
        --out-dtm data/raw/neon/large/OSBS_large_DTM.tif \
        --out-chm data/raw/neon/large/OSBS_large_CHM.tif
"""

import argparse

import numpy as np
import rasterio
from rasterio.transform import from_origin

try:
    import laspy
except ImportError:
    raise SystemExit('laspy not installed. Run:  pip install "laspy[laz]" scipy')

from scipy.ndimage import distance_transform_edt

GROUND_CLASS = 2  # ASPRS standard: 2 = ground


# --------------------------------------------------------------------------
def read_points(laz_path, bounds=None):
    """Load x, y, z, classification. Optionally clip to (minx,miny,maxx,maxy)."""
    with laspy.open(laz_path) as fh:
        las = fh.read()

    x = np.asarray(las.x, dtype=np.float64)
    y = np.asarray(las.y, dtype=np.float64)
    z = np.asarray(las.z, dtype=np.float64)
    cls = np.asarray(las.classification, dtype=np.int16)

    if bounds is not None:
        minx, miny, maxx, maxy = bounds
        m = (x >= minx) & (x < maxx) & (y >= miny) & (y < maxy)
        x, y, z, cls = x[m], y[m], z[m], cls[m]

    return x, y, z, cls


# --------------------------------------------------------------------------
def rasterize(x, y, z, bounds, res, how="min"):
    """Bin points to a grid, taking min or max z per cell. Empty cells = NaN."""
    minx, miny, maxx, maxy = bounds
    w = int(np.ceil((maxx - minx) / res))
    h = int(np.ceil((maxy - miny) / res))

    col = np.clip(((x - minx) / res).astype(np.int64), 0, w - 1)
    # row 0 is the TOP of the raster, so flip y
    row = np.clip(((maxy - y) / res).astype(np.int64), 0, h - 1)
    flat = row * w + col

    out = np.full(h * w, np.nan, dtype=np.float64)

    # np.minimum.at / maximum.at handle repeated indices correctly
    init = np.inf if how == "min" else -np.inf
    acc = np.full(h * w, init, dtype=np.float64)
    if how == "min":
        np.minimum.at(acc, flat, z)
    else:
        np.maximum.at(acc, flat, z)

    filled = np.isfinite(acc)
    out[filled] = acc[filled]
    return out.reshape(h, w)


# --------------------------------------------------------------------------
def fill_nodata(arr, max_dist=None):
    """Nearest-neighbour gap fill.

    LiDAR ground returns are sparse under dense canopy, so the raw ground grid
    always has holes. Nearest-neighbour is crude but adequate at 1 m for a
    routing cost surface; it is NOT adequate if you later want to report
    absolute elevation accuracy -- say so if you do.
    """
    nan_mask = np.isnan(arr)
    if not nan_mask.any():
        return arr
    idx = distance_transform_edt(
        nan_mask, return_distances=False, return_indices=True
    )
    filled = arr[tuple(idx)]
    if max_dist is not None:
        dist = distance_transform_edt(nan_mask)
        filled[dist > max_dist] = np.nan
    return filled


# --------------------------------------------------------------------------
def build(laz_path, ref_path, res=1.0, verbose=True):
    with rasterio.open(ref_path) as ref:
        bounds = (ref.bounds.left, ref.bounds.bottom,
                  ref.bounds.right, ref.bounds.top)
        crs = ref.crs

    x, y, z, cls = read_points(laz_path, bounds=bounds)
    if x.size == 0:
        raise ValueError(
            "No LiDAR points fall inside the reference raster bounds. "
            "The .laz and .tif probably cover different tiles -- check both "
            "footprints before assuming the file is bad."
        )

    ground = cls == GROUND_CLASS
    n_ground = int(ground.sum())

    if n_ground < 100:
        raise ValueError(
            f"Only {n_ground} ground-classified points found. This .laz may be "
            "unclassified. Either use a classified NEON product, or run a "
            "ground filter (e.g. PDAL SMRF) before this step."
        )

    dtm = rasterize(x[ground], y[ground], z[ground], bounds, res, how="min")
    dsm = rasterize(x, y, z, bounds, res, how="max")

    gap_pct = 100.0 * np.isnan(dtm).sum() / dtm.size
    dtm = fill_nodata(dtm)
    dsm = fill_nodata(dsm)

    chm = dsm - dtm
    chm = np.clip(chm, 0.0, None)  # negative height is a rasterisation artefact

    transform = from_origin(bounds[0], bounds[3], res, res)
    profile = {
        "driver": "GTiff", "dtype": "float32", "count": 1,
        "height": dtm.shape[0], "width": dtm.shape[1],
        "crs": crs, "transform": transform, "compress": "lzw",
    }

    diag = {
        "points_total": int(x.size),
        "points_ground": n_ground,
        "ground_pct": round(100.0 * n_ground / x.size, 2),
        "grid_shape": dtm.shape,
        "dtm_gap_pct_before_fill": round(gap_pct, 2),
        "elev_min_m": round(float(np.nanmin(dtm)), 2),
        "elev_max_m": round(float(np.nanmax(dtm)), 2),
        "relief_m": round(float(np.nanmax(dtm) - np.nanmin(dtm)), 2),
        "chm_p50_m": round(float(np.nanpercentile(chm, 50)), 2),
        "chm_p95_m": round(float(np.nanpercentile(chm, 95)), 2),
        "chm_max_m": round(float(np.nanmax(chm)), 2),
    }

    if verbose:
        print("\n--- LiDAR -> DTM / CHM ---")
        for k, v in diag.items():
            print(f"  {k:<26}: {v}")
        if diag["dtm_gap_pct_before_fill"] > 40:
            print("\n  NOTE: >40% of ground cells were empty before filling.")
            print("  Dense canopy blocks ground returns. The DTM is an")
            print("  interpolation over most of the tile -- fine for routing,")
            print("  but state it in the methods section.\n")
        if diag["relief_m"] < 3:
            print("\n  NOTE: total relief is under 3 m. OSBS is flat.")
            print("  Terrain will barely change the route -- that is a")
            print("  FINDING about the site, not a failure. Consider running")
            print("  the terrain module on TEAK (Sierra Nevada) instead,")
            print("  which has real relief and is already in data/raw/.\n")
        print()

    return dtm.astype(np.float32), chm.astype(np.float32), profile, diag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--laz", required=True)
    ap.add_argument("--ref", required=True,
                    help="reference raster defining bounds + CRS")
    ap.add_argument("--res", type=float, default=1.0)
    ap.add_argument("--out-dtm", required=True)
    ap.add_argument("--out-chm", required=True)
    args = ap.parse_args()

    dtm, chm, profile, _ = build(args.laz, args.ref, args.res)

    with rasterio.open(args.out_dtm, "w", **profile) as d:
        d.write(dtm, 1)
    print(f"wrote DTM -> {args.out_dtm}")

    with rasterio.open(args.out_chm, "w", **profile) as d:
        d.write(chm, 1)
    print(f"wrote CHM -> {args.out_chm}")


if __name__ == "__main__":
    main()
