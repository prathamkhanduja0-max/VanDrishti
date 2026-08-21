"""
degradation_chm.py  -- VanDrishti

The PRIMARY degradation signal for this project.

Why this and not spectral indices:
The two acquisitions are September 2018 and April 2019 -- a 7-month,
cross-seasonal gap. Any ExG/VARI/GLI change therefore conflates leaf phenology
with real canopy loss. Canopy HEIGHT does not have that problem: a stand does
not lose 8 m of height because it is April instead of September. Spectral
change becomes supporting evidence; height change is the finding.

Classes (metres of height change):
    removal   dH <= -5      a tree came down
    thinning  -5 < dH <= -2  crown damage / partial loss
    stable    -2 < dH <  +2  within noise
    growth    dH >= +2       genuine growth or regrowth

Honest caveats this script enforces rather than hides:
  - A +/-2 m stable band is used because LiDAR CHM has real vertical
    uncertainty between flights (different flight lines, point density,
    interpolation). Anything inside that band is NOT reported as change.
  - The script reports growth as well as loss. If "growth" pixels vastly
    outnumber "removal" pixels, that is usually a co-registration or
    processing difference between campaigns, NOT a forest that grew 3 m in
    7 months. The script warns when that pattern appears.

Usage:
    python scripts/degradation_chm.py \
        --chm-t1 data/raw/neon/large/OSBS_large_2018_CHM.tif \
        --chm-t2 data/raw/neon/large/OSBS_large_2019_CHM.tif \
        --out-raster results/gis/chm_change.tif \
        --out-vector results/gis/chm_loss_polygons.geojson \
        --stats-out  results/gis/chm_change_stats.json
"""

import argparse
import json

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

CLASSES = {
    1: ("removal", None, -5.0),
    2: ("thinning", -5.0, -2.0),
    3: ("stable", -2.0, 2.0),
    4: ("growth", 2.0, None),
}


def classify(dh):
    out = np.zeros(dh.shape, dtype=np.uint8)
    out[dh <= -5.0] = 1
    out[(dh > -5.0) & (dh <= -2.0)] = 2
    out[(dh > -2.0) & (dh < 2.0)] = 3
    out[dh >= 2.0] = 4
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chm-t1", required=True, help="earlier CHM (2018)")
    ap.add_argument("--chm-t2", required=True, help="later CHM (2019)")
    ap.add_argument("--out-raster", default=None)
    ap.add_argument("--out-vector", default=None)
    ap.add_argument("--stats-out", default=None)
    ap.add_argument("--min-area", type=float, default=4.0)
    args = ap.parse_args()

    with rasterio.open(args.chm_t1) as a:
        h1 = a.read(1).astype(np.float64)
        prof = a.profile.copy()
        nd1, bounds1 = a.nodata, a.bounds
    with rasterio.open(args.chm_t2) as b:
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
    cls_arr = classify(dh)

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
        "dh_mean_m": round(float(np.nanmean(dh)), 3),
        "dh_median_m": round(float(np.nanmedian(dh)), 3),
        "dh_std_m": round(float(np.nanstd(dh)), 3),
        "h1_median_m": round(float(np.nanmedian(h1)), 2),
        "h2_median_m": round(float(np.nanmedian(h2)), 2),
        "classes": counts,
    }

    print("\n--- CHM change detection ---")
    print(f"  median height 2018 : {stats['h1_median_m']} m")
    print(f"  median height 2019 : {stats['h2_median_m']} m")
    print(f"  mean dH            : {stats['dh_mean_m']:+.3f} m")
    print(f"  std  dH            : {stats['dh_std_m']:.3f} m")
    print()
    for name in ["removal", "thinning", "stable", "growth"]:
        c = counts[name]
        print(f"  {name:<10}: {c['pixels']:>7} px  {c['area_m2']:>9} m2  {c['pct']:>6}%")

    # --- honesty checks -------------------------------------------------
    loss_px = counts["removal"]["pixels"] + counts["thinning"]["pixels"]
    growth_px = counts["growth"]["pixels"]

    print()
    if abs(stats["dh_mean_m"]) > 1.0:
        print(f"  WARNING: mean dH is {stats['dh_mean_m']:+.2f} m across the whole")
        print("  tile. A uniform offset like this usually means a vertical datum")
        print("  or processing difference between campaigns, not real change.")
        print("  Consider subtracting the median before classifying, and say so.")
    if growth_px > 2 * loss_px and growth_px > 0.05 * total_valid:
        print("  WARNING: 'growth' pixels far exceed loss pixels. Over 7 months")
        print("  that is not plausible biologically. Check co-registration")
        print("  between the two CHM campaigns before reporting either number.")
    if stats["dh_std_m"] > 4.0:
        print(f"  NOTE: dH std is {stats['dh_std_m']:.1f} m -- high. Much of the")
        print("  per-pixel change may be noise. Rely on the vectorised polygons")
        print("  (which enforce a minimum area) rather than pixel counts.")
    print()

    if args.out_raster:
        prof.update(dtype="uint8", count=1, compress="lzw", nodata=0)
        with rasterio.open(args.out_raster, "w", **prof) as dst:
            dst.write(cls_arr, 1)
        print(f"wrote change raster -> {args.out_raster}")

    if args.out_vector:
        gdf = vectorise(cls_arr, [1, 2], prof["transform"], prof["crs"],
                        args.min_area)
        gdf.to_file(args.out_vector, driver="GeoJSON")
        print(f"wrote {len(gdf)} loss polygons -> {args.out_vector}")
        stats["loss_polygons"] = int(len(gdf))
        stats["loss_polygon_area_m2"] = round(
            float(gdf["area_m2"].sum()), 1) if len(gdf) else 0.0

    if args.stats_out:
        with open(args.stats_out, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"wrote stats -> {args.stats_out}")


if __name__ == "__main__":
    main()
