"""
forest_health_score.py  -- VanDrishti
A composite Forest Health Score computed per grid cell from three measured
LiDAR-derived components (canopy cover, structural diversity, and interior-validated degradation).
Reads configuration and weights from config.yaml with CLI flag overrides.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Union

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import Affine
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader

CANOPY_MIN_H = 2.0      # m, threshold for "canopy present"


def minmax(a):
    """Normalise to [0,1] using 5th/95th percentiles (outlier-robust)."""
    lo, hi = np.nanpercentile(a, [5, 95])
    if hi - lo < 1e-9:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def compute_cells(h1, h2, cell_px, loss_thresh=-5.0, edge_grad_max=2.0):
    """Per-cell component values. Returns dict of 2D arrays (cell grid)."""
    dh = h2 - h1
    gy, gx = np.gradient(h1)
    grad = np.sqrt(gy ** 2 + gx ** 2)
    interior_loss = (dh <= loss_thresh) & (grad < edge_grad_max)

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
            canopy_vals = block_h2[valid & (block_h2 >= CANOPY_MIN_H)]
            diversity[i, j] = np.std(canopy_vals) if canopy_vals.size > 5 else 0.0
            loss_density[i, j] = block_loss.sum() / n

    return {"cover": cover, "diversity": diversity, "loss_density": loss_density}


def score_from_components(comp, w_cover=0.30, w_diversity=0.30, w_degradation=0.40):
    cover_n = minmax(comp["cover"])
    div_n = minmax(comp["diversity"])
    deg_n = 1.0 - minmax(comp["loss_density"])

    score = 100.0 * (w_cover * cover_n
                     + w_diversity * div_n
                     + w_degradation * deg_n)
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


def run_health_score(
    chm_t1_path: str | Path,
    chm_t2_path: str | Path,
    cell_m: float = 25.0,
    w_cover: float = 0.30,
    w_diversity: float = 0.30,
    w_degradation: float = 0.40,
    loss_thresh: float = -5.0,
    edge_grad_max: float = 2.0,
    out_vector: Optional[str | Path] = None,
    out_raster: Optional[str | Path] = None,
    out_stats: Optional[str | Path] = None,
) -> dict:
    """
    Computes 25m composite Forest Health Score from multi-temporal LiDAR CHMs.
    Returns {"geojson": <FeatureCollection dict>, "stats": {...}}.
    """
    chm_t1_p = Path(chm_t1_path)
    chm_t2_p = Path(chm_t2_path)

    if not chm_t1_p.exists() or not chm_t2_p.exists():
        raise FileNotFoundError(f"One or both CHM files do not exist: {chm_t1_p}, {chm_t2_p}")

    with rasterio.open(chm_t1_p) as a:
        h1 = a.read(1).astype(np.float64)
        prof = a.profile.copy()
        bounds = a.bounds
        nd1 = a.nodata
    with rasterio.open(chm_t2_p) as b:
        h2 = b.read(1).astype(np.float64)
        nd2 = b.nodata

    if h1.shape != h2.shape:
        raise ValueError(f"shape mismatch: {h1.shape} vs {h2.shape}")

    if nd1 is not None:
        h1 = np.where(h1 == nd1, np.nan, h1)
    if nd2 is not None:
        h2 = np.where(h2 == nd2, np.nan, h2)

    res_m = abs(prof["transform"].a)
    cell_px = max(1, int(round(cell_m / res_m)))

    comp = compute_cells(h1, h2, cell_px, loss_thresh=loss_thresh, edge_grad_max=edge_grad_max)
    score, norm_comp = score_from_components(comp, w_cover=w_cover, w_diversity=w_diversity, w_degradation=w_degradation)
    sens = sensitivity(comp, score)

    ny, nx = score.shape
    valid_scores = score[np.isfinite(score)]

    geoms, rows = [], []
    for i in range(ny):
        for j in range(nx):
            minx = bounds.left + j * cell_px * res_m
            maxy = bounds.top - i * cell_px * res_m
            maxx = minx + cell_px * res_m
            miny = maxy - cell_px * res_m
            s = float(score[i, j])
            geoms.append(box(minx, miny, maxx, maxy))
            rows.append({
                "cell_id": f"{i}_{j}",
                "score": round(s, 1) if np.isfinite(s) else None,
                "grade": grade(s),
                "canopy_cover": round(float(comp["cover"][i, j]), 3),
                "structural_diversity": round(float(comp["diversity"][i, j]), 2),
                "loss_density": round(float(comp["loss_density"][i, j]), 4),
            })

    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=prof["crs"])
    gdf_wgs84 = gdf.to_crs(epsg=4326) if (gdf.crs and gdf.crs.is_projected) else gdf
    geojson_dict = json.loads(gdf_wgs84.to_json())

    stats_dict = {
        "cell_size_m": cell_m,
        "grid_shape": [ny, nx],
        "total_cells": ny * nx,
        "valid_cells": int(len(valid_scores)),
        "weights": {"cover": w_cover, "diversity": w_diversity, "degradation": w_degradation},
        "score_mean": round(float(np.mean(valid_scores)), 2) if len(valid_scores) else None,
        "score_std": round(float(np.std(valid_scores)), 2) if len(valid_scores) else None,
        "score_min": round(float(np.min(valid_scores)), 2) if len(valid_scores) else None,
        "score_median": round(float(np.median(valid_scores)), 2) if len(valid_scores) else None,
        "score_max": round(float(np.max(valid_scores)), 2) if len(valid_scores) else None,
        "grade_counts": {
            "A": int(sum(grade(s) == "A" for s in valid_scores)),
            "B": int(sum(grade(s) == "B" for s in valid_scores)),
            "C": int(sum(grade(s) == "C" for s in valid_scores)),
            "D": int(sum(grade(s) == "D" for s in valid_scores)),
        },
        "sensitivity": sens,
    }

    if out_vector:
        out_v_path = Path(out_vector)
        out_v_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_v_path, "w", encoding="utf-8") as f:
            json.dump(geojson_dict, f)

    if out_raster:
        out_r_path = Path(out_raster)
        out_r_path.parent.mkdir(parents=True, exist_ok=True)
        cell_transform = Affine(
            res_m * cell_px, 0.0, bounds.left,
            0.0, -res_m * cell_px, bounds.top
        )
        cell_prof = prof.copy()
        cell_prof.update(
            width=nx, height=ny, count=1, dtype="float32",
            transform=cell_transform, nodata=-9999.0, compress="lzw"
        )
        with rasterio.open(out_r_path, "w", **cell_prof) as dst:
            dst.write(np.where(np.isfinite(score), score, -9999.0).astype(np.float32), 1)

    if out_stats:
        out_s_path = Path(out_stats)
        out_s_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_s_path, "w", encoding="utf-8") as f:
            json.dump(stats_dict, f, indent=2)

    return {"geojson": geojson_dict, "stats": stats_dict}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--chm-t1", default=None)
    ap.add_argument("--chm-t2", default=None)
    ap.add_argument("--cell", type=float, default=None, help="cell size in metres")
    ap.add_argument("--out-vector", default=None)
    ap.add_argument("--out-raster", default=None)
    ap.add_argument("--stats-out", default=None)
    args = ap.parse_args()

    cfg = None
    cfg_path = args.config or (REPO_ROOT / "config.yaml")
    if Path(cfg_path).exists():
        cfg = config_loader.load(cfg_path)
        rasters = config_loader.inspect_rasters(cfg)
        caps = config_loader.assess(rasters)
        if caps.get("health_score", {}).get("level") == "BLOCKED" and (not args.chm_t1 or not args.chm_t2):
            missing = ", ".join(caps["health_score"]["missing"])
            raise RuntimeError(f"Module 'health_score' is BLOCKED due to missing required data: {missing}. Aborting.")

    chm_t1_p = args.chm_t1 or (cfg.path("site", "rasters", "chm_t1") if cfg else None)
    chm_t2_p = args.chm_t2 or (cfg.path("site", "rasters", "chm_t2") if cfg else None)

    if not chm_t1_p or not chm_t2_p:
        raise ValueError("Both --chm-t1 and --chm-t2 must be provided via CLI or declared in config.yaml")

    cell_m = args.cell if args.cell is not None else (float(cfg.get("health", {}).get("cell_size_m", 25.0)) if cfg else 25.0)
    w_cover = float(cfg.get("health", {}).get("weights", {}).get("canopy_cover", 0.30)) if cfg else 0.30
    w_div = float(cfg.get("health", {}).get("weights", {}).get("structural_diversity", 0.30)) if cfg else 0.30
    w_deg = float(cfg.get("health", {}).get("weights", {}).get("degradation_penalty", 0.40)) if cfg else 0.40

    loss_thresh = float(cfg.get("degradation", {}).get("loss_thresh_m", -5.0)) if cfg else -5.0
    edge_grad_max = float(cfg.get("degradation", {}).get("edge_grad_max", 2.0)) if cfg else 2.0

    out_vector = args.out_vector or (cfg.path("outputs", "gis_dir") / "forest_health_grid.geojson" if cfg else None)
    out_raster = args.out_raster or (cfg.path("outputs", "gis_dir") / "forest_health_score.tif" if cfg else None)
    stats_out = args.stats_out or (cfg.path("outputs", "gis_dir") / "forest_health_stats.json" if cfg else None)

    res = run_health_score(
        chm_t1_path=chm_t1_p,
        chm_t2_path=chm_t2_p,
        cell_m=cell_m,
        w_cover=w_cover,
        w_diversity=w_div,
        w_degradation=w_deg,
        loss_thresh=loss_thresh,
        edge_grad_max=edge_grad_max,
        out_vector=out_vector,
        out_raster=out_raster,
        out_stats=stats_out,
    )

    stats = res["stats"]
    print(f"\n--- Forest Health Score ({cell_m} m grid, {stats['grid_shape'][1]}x{stats['grid_shape'][0]} = {stats['total_cells']} cells) ---")
    print(f"  weights            : cover={w_cover:.2f} diversity={w_div:.2f} degradation={w_deg:.2f}")
    print(f"  score mean / std   : {stats['score_mean']} / {stats['score_std']}")
    print(f"  score min / median / max : {stats['score_min']} / {stats['score_median']} / {stats['score_max']}")
    print(f"  grade counts       : "
          f"A={stats['grade_counts']['A']} "
          f"B={stats['grade_counts']['B']} "
          f"C={stats['grade_counts']['C']} "
          f"D={stats['grade_counts']['D']}")
    print("\n  sensitivity (rank correlation with headline score):")
    for k, v in stats["sensitivity"].items():
        print(f"    {k:<18}: rho = {v:+.3f}")
    print()

    if out_vector:
        print(f"wrote {len(res['geojson']['features'])} grid cells -> {out_vector}")
    if out_raster:
        print(f"wrote score raster -> {out_raster}")
    if stats_out:
        print(f"wrote stats -> {stats_out}")


if __name__ == "__main__":
    main()
