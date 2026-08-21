"""
forest_health_score.py  -- VanDrishti

A composite Forest Health Score computed per grid cell from three measured
LiDAR-derived components. Every input is something this project actually
measured; nothing is invented to fill out the formula.

COMPONENTS
  1. Canopy cover        (30%)  fraction of cell with CHM >= 2 m
  2. Structural diversity(30%)  std dev of CHM within the cell
  3. Degradation         (40%)  density of interior-validated height loss

Degradation carries the largest weight because it is the only component that
measures CHANGE. Cover and diversity describe the current state; a stand can
score well on both while actively being cleared.

WHY FIRE IS NOT IN THE SCORE
NASA FIRMS VIIRS pixels are 375 m. The entire study area is 250 m. One fire
pixel is larger than the whole site, so fire cannot be resolved at the 25 m
cell level used here. Including it would mean adding the same constant to
every cell -- precision that does not exist. Fire is retained as a separate
regional context layer instead. Say this explicitly rather than letting a
reviewer discover the scale mismatch.

WHAT THIS SCORE IS NOT
Components are normalised WITHIN the tile, so the score is relative -- it
ranks cells against each other, not against an absolute ecological standard.
A cell scoring 90 is among the healthier cells HERE; it is not "90% healthy".
Cross-site comparison requires fixed reference ranges, which this project does
not have. This is a real limitation and belongs in the report.

Weights are a stated judgement, not a derived optimum. There is no ground
truth to fit them against. State them, justify them, and run the sensitivity
check this script prints.

Usage:
    python scripts/forest_health_score.py \
        --chm-t1 data/raw/neon/large/OSBS_large_2018_CHM.tif \
        --chm-t2 data/raw/neon/large/OSBS_large_2019_CHM.tif \
        --cell 25 \
        --out-vector results/gis/forest_health_grid.geojson \
        --out-raster results/gis/forest_health_score.tif \
        --stats-out  results/gis/forest_health_stats.json
"""

import argparse
import json

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import Affine
from shapely.geometry import box

# component weights -- stated judgement, see module docstring
W_COVER = 0.30
W_DIVERSITY = 0.30
W_DEGRADATION = 0.40

CANOPY_MIN_H = 2.0      # m, threshold for "canopy present"
LOSS_THRESH = -5.0      # m, height drop counted as loss
EDGE_GRAD_MAX = 2.0     # m, interior-only mask (see degradation validation)


def minmax(a):
    """Normalise to [0,1] using 5th/95th percentiles (outlier-robust)."""
    lo, hi = np.nanpercentile(a, [5, 95])
    if hi - lo < 1e-9:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def compute_cells(h1, h2, cell_px):
    """Per-cell component values. Returns dict of 2D arrays (cell grid)."""
    dh = h2 - h1
    gy, gx = np.gradient(h1)
    grad = np.sqrt(gy ** 2 + gx ** 2)
    interior_loss = (dh <= LOSS_THRESH) & (grad < EDGE_GRAD_MAX)

    H, W = h2.shape
    ny, nx = H // cell_px, W // cell_px

    cover = np.zeros((ny, nx))
    diversity = np.zeros((ny, nx))
    loss_density = np.zeros((ny, nx))

    for i in range(ny):
        for j in range(nx):
            sl = (slice(i * cell_px, (i + 1) * cell_px),
                  slice(j * cell_px, (j + 1) * cell_px))
            block_h2 = h2[sl]
            block_loss = interior_loss[sl]

            valid = np.isfinite(block_h2)
            n = valid.sum()
            if n == 0:
                cover[i, j] = diversity[i, j] = loss_density[i, j] = np.nan
                continue

            cover[i, j] = np.nansum(block_h2 >= CANOPY_MIN_H) / n
            # diversity only over canopy pixels -- std over bare ground is
            # meaningless and would reward empty cells
            canopy_vals = block_h2[valid & (block_h2 >= CANOPY_MIN_H)]
            diversity[i, j] = np.std(canopy_vals) if canopy_vals.size > 5 else 0.0
            loss_density[i, j] = block_loss.sum() / n

    return {"cover": cover, "diversity": diversity, "loss_density": loss_density}


def score_from_components(comp):
    cover_n = minmax(comp["cover"])
    div_n = minmax(comp["diversity"])
    # degradation: more loss = worse, so invert
    deg_n = 1.0 - minmax(comp["loss_density"])

    score = 100.0 * (W_COVER * cover_n
                     + W_DIVERSITY * div_n
                     + W_DEGRADATION * deg_n)
    return score, {"cover_n": cover_n, "div_n": div_n, "deg_n": deg_n}


def grade(s):
    if not np.isfinite(s):
        return "NA"
    if s >= 80:
        return "A"
    if s >= 65:
        return "B"
    if s >= 50:
        return "C"
    return "D"


def sensitivity(comp, base_score):
    """How much does the ranking depend on the chosen weights?

    Re-scores under equal weights and under each component alone, and reports
    rank correlation with the headline score. If a cell's rank flips wildly
    under reweighting, the score is a weight artefact, not a measurement.
    """
    from scipy.stats import spearmanr

    cover_n = minmax(comp["cover"])
    div_n = minmax(comp["diversity"])
    deg_n = 1.0 - minmax(comp["loss_density"])

    variants = {
        "equal_weights": (cover_n + div_n + deg_n) / 3.0,
        "cover_only": cover_n,
        "diversity_only": div_n,
        "degradation_only": deg_n,
    }

    base = base_score.ravel()
    m = np.isfinite(base)
    out = {}
    for name, v in variants.items():
        rho, _ = spearmanr(base[m], v.ravel()[m])
        out[name] = round(float(rho), 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chm-t1", required=True)
    ap.add_argument("--chm-t2", required=True)
    ap.add_argument("--cell", type=int, default=25, help="cell size in metres")
    ap.add_argument("--out-vector", default=None)
    ap.add_argument("--out-raster", default=None)
    ap.add_argument("--stats-out", default=None)
    args = ap.parse_args()

    with rasterio.open(args.chm_t1) as a:
        h1 = a.read(1).astype(np.float64)
        nd1 = a.nodata
    with rasterio.open(args.chm_t2) as b:
        h2 = b.read(1).astype(np.float64)
        nd2, prof, transform, crs = b.nodata, b.profile.copy(), b.transform, b.crs

    if h1.shape != h2.shape:
        raise ValueError(f"shape mismatch t1={h1.shape} t2={h2.shape}")

    if nd1 is not None:
        h1 = np.where(h1 == nd1, np.nan, h1)
    if nd2 is not None:
        h2 = np.where(h2 == nd2, np.nan, h2)

    res = abs(transform.a)
    cell_px = int(round(args.cell / res))
    if cell_px < 2:
        raise ValueError(f"cell size {args.cell} m is smaller than raster "
                         f"resolution {res} m")

    comp = compute_cells(h1, h2, cell_px)
    score, norm = score_from_components(comp)
    ny, nx = score.shape

    grades = np.vectorize(grade)(score)
    sens = sensitivity(comp, score)

    stats = {
        "cell_size_m": args.cell,
        "grid": [int(ny), int(nx)],
        "n_cells": int(ny * nx),
        "weights": {"cover": W_COVER, "diversity": W_DIVERSITY,
                    "degradation": W_DEGRADATION},
        "score_min": round(float(np.nanmin(score)), 1),
        "score_median": round(float(np.nanmedian(score)), 1),
        "score_max": round(float(np.nanmax(score)), 1),
        "grade_counts": {g: int((grades == g).sum()) for g in "ABCD"},
        "component_means": {
            "cover_frac": round(float(np.nanmean(comp["cover"])), 3),
            "diversity_m": round(float(np.nanmean(comp["diversity"])), 2),
            "loss_density": round(float(np.nanmean(comp["loss_density"])), 5),
        },
        "weight_sensitivity_spearman": sens,
    }

    print("\n--- Forest Health Score ---")
    print(f"  grid            : {ny} x {nx} cells @ {args.cell} m")
    print(f"  score range     : {stats['score_min']} - {stats['score_max']} "
          f"(median {stats['score_median']})")
    print(f"  grades          : " +
          "  ".join(f"{g}={stats['grade_counts'][g]}" for g in "ABCD"))
    print(f"\n  mean canopy cover      : {stats['component_means']['cover_frac']}")
    print(f"  mean height std (m)    : {stats['component_means']['diversity_m']}")
    print(f"  mean loss density      : {stats['component_means']['loss_density']}")

    print("\n  weight sensitivity (Spearman vs headline score):")
    for k, v in sens.items():
        print(f"    {k:<20}: {v:+.3f}")
    if sens["equal_weights"] > 0.95:
        print("    => ranking is robust to reweighting; the score reflects the")
        print("       measurements, not the chosen weights.")
    else:
        print("    => ranking shifts under reweighting. Report the weights as")
        print("       a sensitivity range, not a single authoritative score.")
    print()

    # --- outputs ---
    if args.out_vector:
        recs = []
        for i in range(ny):
            for j in range(nx):
                x0 = transform.c + j * cell_px * res
                y0 = transform.f - i * cell_px * res
                recs.append({
                    "cell_id": f"r{i}c{j}",
                    "health_score": round(float(score[i, j]), 1)
                        if np.isfinite(score[i, j]) else None,
                    "grade": str(grades[i, j]),
                    "canopy_cover": round(float(comp["cover"][i, j]), 3),
                    "height_std_m": round(float(comp["diversity"][i, j]), 2),
                    "loss_density": round(float(comp["loss_density"][i, j]), 5),
                    "geometry": box(x0, y0 - args.cell, x0 + args.cell, y0),
                })
        gdf = gpd.GeoDataFrame(recs, crs=crs)
        gdf.to_file(args.out_vector, driver="GeoJSON")
        print(f"wrote {len(gdf)} health cells -> {args.out_vector}")

    if args.out_raster:
        prof.update(dtype="float32", count=1, height=ny, width=nx,
                    transform=Affine(args.cell, 0, transform.c,
                                     0, -args.cell, transform.f),
                    compress="lzw", nodata=-9999)
        with rasterio.open(args.out_raster, "w", **prof) as dst:
            dst.write(np.nan_to_num(score, nan=-9999).astype(np.float32), 1)
        print(f"wrote score raster -> {args.out_raster}")

    if args.stats_out:
        with open(args.stats_out, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"wrote stats -> {args.stats_out}")


if __name__ == "__main__":
    main()
