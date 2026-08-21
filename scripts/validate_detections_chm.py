"""
validate_detections_chm.py  -- VanDrishti
Validates detected tree points against the Canopy Height Model (CHM) from LiDAR.
Reads thresholds and raster paths from config.yaml with CLI flag overrides.
"""

import argparse
import json
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import rasterio

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader


def sample_max_in_radius(chm, transform, xs, ys, radius_m):
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
    ap.add_argument("--config", default=None)
    ap.add_argument("--trees", default=None)
    ap.add_argument("--chm", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-height", type=float, default=None)
    ap.add_argument("--radius", type=float, default=None)
    ap.add_argument("--stats-out", default=None)
    args = ap.parse_args()

    cfg = None
    cfg_path = args.config or (REPO_ROOT / "config.yaml")
    if Path(cfg_path).exists():
        cfg = config_loader.load(cfg_path)

    trees_p = args.trees or (cfg.path("detection", "raw_trees_geojson") if cfg else None)
    chm_p = args.chm or (cfg.path("site", "rasters", "chm_t2") if cfg else None)

    if not trees_p or not chm_p:
        raise ValueError("Both --trees and --chm must be provided via CLI or declared in config.yaml")

    min_h = args.min_height if args.min_height is not None else (float(cfg.get("detection", {}).get("chm_min_height", 2.0)) if cfg else 2.0)
    radius = args.radius if args.radius is not None else (float(cfg.get("detection", {}).get("chm_radius", 1.5)) if cfg else 1.5)

    with rasterio.open(chm_p) as src:
        chm = src.read(1).astype(np.float64)
        transform = src.transform
        chm_crs = src.crs
        nd = src.nodata

    if nd is not None:
        chm = np.where(chm == nd, np.nan, chm)

    gdf = gpd.read_file(trees_p)
    if gdf.crs != chm_crs:
        print(f"Reprojecting trees ({gdf.crs}) -> CHM ({chm_crs})")
        gdf = gdf.to_crs(chm_crs)

    xs = gdf.geometry.x.to_numpy()
    ys = gdf.geometry.y.to_numpy()

    h_sampled = sample_max_in_radius(chm, transform, xs, ys, radius_m=radius)
    gdf["chm_height_m"] = np.round(h_sampled, 2)

    valid_mask = np.isfinite(h_sampled) & (h_sampled >= min_h)
    gdf_valid = gdf.loc[valid_mask].copy()

    n_raw = len(gdf)
    n_valid = len(gdf_valid)
    n_dropped = n_raw - n_valid

    conf_col = "confidence" if "confidence" in gdf.columns else ("score" if "score" in gdf.columns else None)
    calib = calibration_table(gdf[conf_col].to_numpy(), h_sampled) if conf_col else []

    stats = {
        "raw_count": n_raw,
        "valid_count": n_valid,
        "dropped_count": n_dropped,
        "retention_pct": round(100.0 * n_valid / n_raw, 2) if n_raw else 0.0,
        "height_stats_all": {
            "mean_m": round(float(np.nanmean(h_sampled)), 2),
            "median_m": round(float(np.nanmedian(h_sampled)), 2),
            "p5_m": round(float(np.nanpercentile(h_sampled, 5)), 2),
            "p95_m": round(float(np.nanpercentile(h_sampled, 95)), 2),
        },
        "params": {
            "min_height_m": min_h,
            "search_radius_m": radius,
        },
        "confidence_calibration": calib,
    }

    print("\n--- Detection validation against CHM ---")
    print(f"  raw detections       : {n_raw:>5}")
    print(f"  valid (height >= {min_h}m): {n_valid:>5}  ({stats['retention_pct']}%)")
    print(f"  dropped (short/empty): {n_dropped:>5}")
    print(f"  sampled height mean  : {stats['height_stats_all']['mean_m']} m "
          f"(median {stats['height_stats_all']['median_m']} m)")
    print()

    if calib:
        print("  Confidence -> CHM height calibration:")
        print("    conf range         n   mean_h  med_h   % < 2m")
        for row in calib:
            cr = f"[{row['conf_range'][0]:.2f}, {row['conf_range'][1]:.2f})"
            print(f"    {cr:<16} {row['n']:>5}  {row['height_mean_m']:>5.1f}m "
                  f"{row['height_median_m']:>5.1f}m  {row['pct_under_2m']:>5.1f}%")
        print()

    out_p = args.out or (cfg.path("outputs", "gis_dir") / f"{cfg.get('site',{}).get('name','study_area')}_trees_chm_valid.geojson" if cfg else None)
    if out_p:
        gdf_valid.to_file(out_p, driver="GeoJSON")
        print(f"wrote validated detections -> {out_p}")

    stats_out = args.stats_out or (cfg.path("outputs", "gis_dir") / "chm_validation_stats.json" if cfg else None)
    if stats_out:
        with open(stats_out, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"wrote stats -> {stats_out}")


if __name__ == "__main__":
    main()
