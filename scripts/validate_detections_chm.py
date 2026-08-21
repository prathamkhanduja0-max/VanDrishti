"""
validate_detections_chm.py  -- VanDrishti

Geometric NMS found almost nothing (1.25% removal) because DeepForest already
suppresses overlapping boxes internally at IoU=0.15. So duplicate boxes are not
the source of the "too dense" problem.

A better test is available now that CHM data exists: if a detected "tree" sits
where the canopy height model reads 0.4 m, it is not a tree. Height is
independent evidence -- it comes from LiDAR, not from the same RGB pixels the
detector already saw.

Two outputs:

  1. FILTER -- drop detections whose local canopy height is implausible.

  2. CALIBRATION CHECK -- the priority engine assumes low confidence means the
     model is uncertain. That is testable: bin detections by confidence and
     look at the CHM height distribution in each bin. If low-confidence
     detections really do sit on shorter/absent canopy, the assumption holds.
     If height is flat across confidence bins, the assumption does NOT hold and
     the HIGH-priority tier needs a different basis. Either result is worth
     reporting -- do not discard the negative one.

Usage:
    python scripts/validate_detections_chm.py \
        --trees results/gis/OSBS_large_2019_trees.geojson \
        --chm   data/raw/neon/large/OSBS_large_2019_CHM.tif \
        --out   results/gis/OSBS_large_2019_trees_chm_valid.geojson \
        --min-height 2.0 --radius 1.5 \
        --stats-out results/gis/chm_validation_stats.json
"""

import argparse
import json

import geopandas as gpd
import numpy as np
import rasterio


def sample_max_in_radius(chm, transform, xs, ys, radius_m):
    """Max CHM value within radius_m of each point.

    Max, not the single centre pixel, because the detected crown centroid and
    the 1 m CHM grid will not line up exactly -- a 0.1 m RGB centroid can fall
    on a CHM cell that happens to catch a gap between branches.
    """
    res = abs(transform.a)
    rad_px = max(1, int(np.ceil(radius_m / res)))
    h, w = chm.shape

    inv = ~transform
    out = np.full(len(xs), np.nan)

    for i, (x, y) in enumerate(zip(xs, ys)):
        c, r = inv * (x, y)
        r, c = int(r), int(c)
        r0, r1 = max(0, r - rad_px), min(h, r + rad_px + 1)
        c0, c1 = max(0, c - rad_px), min(w, c + rad_px + 1)
        if r0 >= r1 or c0 >= c1:
            continue
        window = chm[r0:r1, c0:c1]
        if window.size and np.isfinite(window).any():
            out[i] = np.nanmax(window)

    return out


def calibration_table(conf, height, n_bins=5):
    """Height distribution per confidence bin.

    If the priority engine's premise is sound, mean height should RISE with
    confidence. A flat table means confidence is not tracking whether a real
    tree is present.
    """
    edges = np.nanpercentile(conf, np.linspace(0, 100, n_bins + 1))
    edges[-1] += 1e-9
    rows = []

    for i in range(n_bins):
        m = (conf >= edges[i]) & (conf < edges[i + 1])
        if not m.any():
            continue
        h = height[m]
        rows.append({
            "conf_range": [round(float(edges[i]), 3), round(float(edges[i + 1]), 3)],
            "n": int(m.sum()),
            "height_mean_m": round(float(np.nanmean(h)), 2),
            "height_median_m": round(float(np.nanmedian(h)), 2),
            "pct_under_2m": round(float(100.0 * np.nanmean(h < 2.0)), 1),
        })

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trees", required=True)
    ap.add_argument("--chm", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-height", type=float, default=2.0,
                    help="minimum plausible canopy height in metres")
    ap.add_argument("--radius", type=float, default=1.5,
                    help="search radius around each detection, metres")
    ap.add_argument("--conf-col", default="confidence")
    ap.add_argument("--stats-out", default=None)
    args = ap.parse_args()

    gdf = gpd.read_file(args.trees)
    print(f"read {len(gdf)} detections, CRS={gdf.crs}")

    with rasterio.open(args.chm) as src:
        chm = src.read(1).astype(np.float64)
        if src.nodata is not None:
            chm = np.where(chm == src.nodata, np.nan, chm)
        transform = src.transform
        chm_crs = src.crs

    if gdf.crs != chm_crs:
        print(f"reprojecting detections {gdf.crs} -> {chm_crs}")
        gdf = gdf.to_crs(chm_crs)

    pts = gdf.geometry.centroid
    height = sample_max_in_radius(
        chm, transform, pts.x.to_numpy(), pts.y.to_numpy(), args.radius
    )
    gdf["chm_height_m"] = np.round(height, 2)

    outside = int(np.isnan(height).sum())
    if outside:
        print(f"WARNING: {outside} detections fell outside the CHM extent "
              "-- check that the CHM covers the full study area")

    conf = gdf[args.conf_col].to_numpy(dtype=np.float64)
    calib = calibration_table(conf, height)

    keep = np.nan_to_num(height, nan=-1.0) >= args.min_height
    out = gdf.loc[keep].copy()

    stats = {
        "input": int(len(gdf)),
        "kept": int(keep.sum()),
        "dropped": int((~keep).sum()),
        "dropped_pct": round(100.0 * (~keep).sum() / len(gdf), 2),
        "outside_chm_extent": outside,
        "min_height_m": args.min_height,
        "radius_m": args.radius,
        "height_median_m": round(float(np.nanmedian(height)), 2),
        "height_p95_m": round(float(np.nanpercentile(height, 95)), 2),
        "calibration_by_confidence": calib,
    }

    print("\n--- CHM validation ---")
    for k in ["input", "kept", "dropped", "dropped_pct", "height_median_m"]:
        print(f"  {k:<22}: {stats[k]}")

    print("\n--- Confidence vs canopy height ---")
    print(f"  {'conf range':<18}{'n':>6}{'mean h':>9}{'% <2m':>9}")
    for r in calib:
        rng = f"{r['conf_range'][0]:.3f}-{r['conf_range'][1]:.3f}"
        print(f"  {rng:<18}{r['n']:>6}{r['height_mean_m']:>9}{r['pct_under_2m']:>9}")

    if len(calib) >= 2:
        lo, hi = calib[0]["height_mean_m"], calib[-1]["height_mean_m"]
        spread = hi - lo
        print(f"\n  height spread lowest->highest conf bin: {spread:+.2f} m")
        if abs(spread) < 1.0:
            print("  => Confidence barely tracks canopy height. The priority")
            print("     engine's 'low confidence = uncertain detection'")
            print("     assumption is NOT supported here. Report this.")
        else:
            print("  => Confidence tracks canopy height. The assumption holds.")
    print()

    out.to_file(args.out, driver="GeoJSON")
    print(f"wrote {len(out)} validated detections -> {args.out}")

    if args.stats_out:
        with open(args.stats_out, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"wrote stats -> {args.stats_out}")


if __name__ == "__main__":
    main()
