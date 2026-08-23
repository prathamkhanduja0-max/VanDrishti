"""
degradation_chm.py  -- VanDrishti
The PRIMARY degradation signal for this project using multi-temporal LiDAR CHM differencing.
Reads thresholds and raster paths from config.yaml, keeping CLI flags as overrides.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Union
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader

CLASSES = {
    1: ("removal", None, -5.0),
    2: ("thinning", -5.0, -2.0),
    3: ("stable", -2.0, 2.0),
    4: ("growth", 2.0, None),
}


def classify(dh, loss_thresh=-5.0, thinning_thresh=-2.0, stable_band=2.0):
    out = np.zeros(dh.shape, dtype=np.uint8)
    out[dh <= loss_thresh] = 1
    out[(dh > loss_thresh) & (dh <= thinning_thresh)] = 2
    out[(dh > thinning_thresh) & (dh < stable_band)] = 3
    out[dh >= stable_band] = 4
    out[~np.isfinite(dh)] = 0
    return out


def vectorise(cls_arr, target_classes, transform, crs, min_area_m2=4.0):
    mask = np.isin(cls_arr, target_classes)
    if not mask.any():
        return gpd.GeoDataFrame({"geometry": []}, crs=crs)

    geoms, vals = [], []
    for geom, val in shapes(cls_arr, mask=mask, transform=transform):
        geoms.append(shape(geom))
        vals.append(int(val))

    gdf = gpd.GeoDataFrame(
        {"class_id": vals,
         "class_name": [CLASSES[v][0] for v in vals],
         "geometry": geoms},
        crs=crs,
    )
    gdf["area_m2"] = gdf.area
    return gdf[gdf["area_m2"] >= min_area_m2].reset_index(drop=True)


def run_degradation_chm(
    chm_t1_path: str | Path,
    chm_t2_path: str | Path,
    loss_thresh: float = -5.0,
    thinning_thresh: float = -2.0,
    stable_band: float = 2.0,
    min_area_m2: float = 4.0,
    out_vector: Optional[str | Path] = None,
    out_raster: Optional[str | Path] = None,
    out_stats: Optional[str | Path] = None,
) -> dict:
    """
    Runs multi-temporal LiDAR CHM change/loss detection.
    Returns {"geojson": <FeatureCollection dict>, "stats": {...}}.
    """
    chm_t1_p = Path(chm_t1_path)
    chm_t2_p = Path(chm_t2_path)

    if not chm_t1_p.exists() or not chm_t2_p.exists():
        raise FileNotFoundError(f"One or both CHM files do not exist: {chm_t1_p}, {chm_t2_p}")

    with rasterio.open(chm_t1_p) as a:
        h1 = a.read(1).astype(np.float64)
        prof = a.profile.copy()
        nd1, bounds1 = a.nodata, a.bounds
    with rasterio.open(chm_t2_p) as b:
        h2 = b.read(1).astype(np.float64)
        nd2, bounds2 = b.nodata, b.bounds

    if h1.shape != h2.shape:
        raise ValueError(
            f"shape mismatch: t1={h1.shape} t2={h2.shape}. "
            "Clip both to the same grid before differencing."
        )
    if [round(v, 2) for v in bounds1] != [round(v, 2) for v in bounds2]:
        raise ValueError(
            f"bounds mismatch:\n  t1={bounds1}\n  t2={bounds2}\n"
            "Same shape but different extent means the pixels do not "
            "correspond. Re-clip both to identical bounds."
        )

    if nd1 is not None:
        h1 = np.where(h1 == nd1, np.nan, h1)
    if nd2 is not None:
        h2 = np.where(h2 == nd2, np.nan, h2)

    dh = h2 - h1
    cls_arr = classify(dh, loss_thresh=loss_thresh, thinning_thresh=thinning_thresh, stable_band=stable_band)

    px_area = abs(prof["transform"].a * prof["transform"].e)
    total_valid = int(np.isfinite(dh).sum())

    counts = {}
    for cid, (name, _, _) in CLASSES.items():
        n = int((cls_arr == cid).sum())
        counts[name] = {
            "pixels": n,
            "area_m2": round(n * px_area, 1),
            "pct": round(100.0 * n / total_valid, 2) if total_valid else 0.0,
        }

    stats = {
        "valid_pixels": total_valid,
        "pixel_area_m2": px_area,
        "dh_mean_m": round(float(np.nanmean(dh)), 3) if total_valid else None,
        "dh_median_m": round(float(np.nanmedian(dh)), 3) if total_valid else None,
        "dh_std_m": round(float(np.nanstd(dh)), 3) if total_valid else None,
        "h1_median_m": round(float(np.nanmedian(h1)), 2) if total_valid else None,
        "h2_median_m": round(float(np.nanmedian(h2)), 2) if total_valid else None,
        "classes": counts,
    }

    gdf = vectorise(cls_arr, [1, 2], prof["transform"], prof["crs"], min_area_m2)
    gdf_wgs84 = gdf.to_crs(epsg=4326) if (gdf.crs and gdf.crs.is_projected) else gdf
    geojson_dict = json.loads(gdf_wgs84.to_json())

    stats["loss_polygons"] = int(len(gdf))
    stats["loss_polygon_area_m2"] = round(float(gdf["area_m2"].sum()), 1) if len(gdf) else 0.0

    if out_vector:
        out_v_path = Path(out_vector)
        out_v_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_v_path, "w", encoding="utf-8") as f:
            json.dump(geojson_dict, f)

    if out_raster:
        out_r_path = Path(out_raster)
        out_r_path.parent.mkdir(parents=True, exist_ok=True)
        prof.update(dtype="uint8", count=1, compress="lzw", nodata=0)
        with rasterio.open(out_r_path, "w", **prof) as dst:
            dst.write(cls_arr, 1)

    if out_stats:
        out_s_path = Path(out_stats)
        out_s_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_s_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

    return {"geojson": geojson_dict, "stats": stats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None, help="Path to config.yaml")
    ap.add_argument("--chm-t1", default=None, help="earlier CHM (2018)")
    ap.add_argument("--chm-t2", default=None, help="later CHM (2019)")
    ap.add_argument("--out-raster", default=None)
    ap.add_argument("--out-vector", default=None)
    ap.add_argument("--stats-out", default=None)
    ap.add_argument("--min-area", type=float, default=None)
    args = ap.parse_args()

    cfg = None
    cfg_path = args.config or (REPO_ROOT / "config.yaml")
    if Path(cfg_path).exists():
        cfg = config_loader.load(cfg_path)
        rasters = config_loader.inspect_rasters(cfg)
        caps = config_loader.assess(rasters)
        if caps.get("degradation", {}).get("level") == "BLOCKED" and (not args.chm_t1 or not args.chm_t2):
            missing = ", ".join(caps["degradation"]["missing"])
            raise RuntimeError(f"Module 'degradation' is BLOCKED due to missing required data: {missing}. Aborting.")

    # Resolve inputs (CLI override > config > default)
    chm_t1_p = args.chm_t1 or (cfg.path("site", "rasters", "chm_t1") if cfg else None)
    chm_t2_p = args.chm_t2 or (cfg.path("site", "rasters", "chm_t2") if cfg else None)

    if not chm_t1_p or not chm_t2_p:
        raise ValueError("Both --chm-t1 and --chm-t2 must be provided via CLI or declared in config.yaml")

    loss_thresh = float(cfg.get("degradation", {}).get("loss_thresh_m", -5.0)) if cfg else -5.0
    thinning_thresh = float(cfg.get("degradation", {}).get("thinning_thresh_m", -2.0)) if cfg else -2.0
    stable_band = float(cfg.get("degradation", {}).get("stable_band_m", 2.0)) if cfg else 2.0
    min_area = args.min_area if args.min_area is not None else (float(cfg.get("degradation", {}).get("min_area_m2", 4.0)) if cfg else 4.0)

    out_raster = args.out_raster or (cfg.path("outputs", "gis_dir") / "chm_change.tif" if cfg else None)
    out_vector = args.out_vector or (cfg.path("outputs", "gis_dir") / "chm_loss_polygons.geojson" if cfg else None)
    stats_out = args.stats_out or (cfg.path("outputs", "gis_dir") / "chm_change_stats.json" if cfg else None)

    res = run_degradation_chm(
        chm_t1_path=chm_t1_p,
        chm_t2_path=chm_t2_p,
        loss_thresh=loss_thresh,
        thinning_thresh=thinning_thresh,
        stable_band=stable_band,
        min_area_m2=min_area,
        out_vector=out_vector,
        out_raster=out_raster,
        out_stats=stats_out,
    )

    stats = res["stats"]
    counts = stats["classes"]

    print("\n--- CHM change detection ---")
    print(f"  median height 2018 : {stats['h1_median_m']} m")
    print(f"  median height 2019 : {stats['h2_median_m']} m")
    print(f"  mean dH            : {stats['dh_mean_m']:+.3f} m")
    print(f"  std  dH            : {stats['dh_std_m']:.3f} m")
    print()
    for name in ["removal", "thinning", "stable", "growth"]:
        c = counts[name]
        print(f"  {name:<10}: {c['pixels']:>7} px  {c['area_m2']:>9} m2  {c['pct']:>6}%")

    loss_px = counts["removal"]["pixels"] + counts["thinning"]["pixels"]
    growth_px = counts["growth"]["pixels"]

    print()
    if abs(stats["dh_mean_m"]) > 1.0:
        print(f"  WARNING: mean dH is {stats['dh_mean_m']:+.2f} m across the whole")
        print("  tile. A uniform offset like this usually means a vertical datum")
        print("  or processing difference between campaigns, not real change.")
        print("  Consider subtracting the median before classifying, and say so.")
    if growth_px > 2 * loss_px and growth_px > 0.05 * stats["valid_pixels"]:
        print("  WARNING: 'growth' pixels far exceed loss pixels. Over 7 months")
        print("  that is not plausible biologically. Check co-registration")
        print("  between the two CHM campaigns before reporting either number.")
    if stats["dh_std_m"] > 4.0:
        print(f"  NOTE: dH std is {stats['dh_std_m']:.1f} m -- high. Much of the")
        print("  per-pixel change may be noise. Rely on the vectorised polygons")
        print("  (which enforce a minimum area) rather than pixel counts.")
    print()

    if out_raster:
        print(f"wrote change raster -> {out_raster}")
    if out_vector:
        print(f"wrote {stats['loss_polygons']} loss polygons -> {out_vector}")
    if stats_out:
        print(f"wrote stats -> {stats_out}")


if __name__ == "__main__":
    main()
