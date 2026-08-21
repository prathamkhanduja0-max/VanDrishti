"""
clean_detections.py  -- VanDrishti
Reconstructs boxes from pixel coordinates, runs NMS, applies crown-size sanity
filtering, and performs centroid deduplication.
Reads detection parameters from config.yaml with CLI flag overrides.
"""

import argparse
import json
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader

BBOX_COLS = ["pixel_xmin", "pixel_ymin", "pixel_xmax", "pixel_ymax"]


def _require_cols(gdf, cols, what):
    missing = [c for c in cols if c not in gdf.columns]
    if missing:
        raise KeyError(
            f"{what}: missing column(s) {missing}. "
            f"Available: {list(gdf.columns)}"
        )


def nms_pixel_boxes(gdf, iou_thresh=0.35, score_col="confidence"):
    _require_cols(gdf, BBOX_COLS + [score_col], "nms_pixel_boxes")
    if gdf.empty:
        return gdf

    boxes = gdf[BBOX_COLS].to_numpy(dtype=np.float64)
    scores = gdf[score_col].to_numpy(dtype=np.float64)
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])

    order = scores.argsort()[::-1]
    keep = []

    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]

        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])

        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[i] + areas[rest] - inter
        iou = np.where(union > 0, inter / union, 0.0)

        order = rest[iou <= iou_thresh]

    return gdf.iloc[sorted(keep)].copy()


def filter_by_crown_size(gdf, res_m=0.1, min_diam_m=1.5, max_diam_m=30.0):
    _require_cols(gdf, BBOX_COLS, "filter_by_crown_size")
    if gdf.empty:
        return gdf

    b = gdf[BBOX_COLS].to_numpy(dtype=np.float64)
    width_m = (b[:, 2] - b[:, 0]) * res_m
    height_m = (b[:, 3] - b[:, 1]) * res_m
    diam_m = (width_m + height_m) / 2.0

    mask = (diam_m >= min_diam_m) & (diam_m <= max_diam_m)
    out = gdf.loc[mask].copy()
    out["crown_diam_m"] = np.round(diam_m[mask], 2)
    return out


def dedup_centroids_metric(gdf, min_sep_m=2.0, score_col="confidence"):
    if gdf.empty:
        return gdf

    from scipy.spatial import cKDTree

    pts = np.column_stack([gdf.geometry.x, gdf.geometry.y])
    scores = gdf[score_col].to_numpy(dtype=np.float64)
    order = scores.argsort()[::-1]

    tree = cKDTree(pts)
    suppressed = np.zeros(len(gdf), dtype=bool)
    keep = []

    for idx in order:
        if suppressed[idx]:
            continue
        keep.append(idx)
        nearby = tree.query_ball_point(pts[idx], r=min_sep_m)
        for n in nearby:
            if n != idx:
                suppressed[n] = True

    return gdf.iloc[sorted(keep)].copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--in", dest="in_path", default=None)
    ap.add_argument("--out", dest="out_path", default=None)
    ap.add_argument("--res", type=float, default=0.1)
    ap.add_argument("--iou", type=float, default=0.35)
    ap.add_argument("--min-diam", type=float, default=None)
    ap.add_argument("--max-diam", type=float, default=30.0)
    ap.add_argument("--min-sep", type=float, default=None)
    ap.add_argument("--stats-out", default=None)
    args = ap.parse_args()

    cfg = None
    cfg_path = args.config or (REPO_ROOT / "config.yaml")
    if Path(cfg_path).exists():
        cfg = config_loader.load(cfg_path)

    in_path = args.in_path or (cfg.path("detection", "raw_trees_geojson") if cfg else None)
    if not in_path:
        raise ValueError("Input trees path must be provided via --in or config.yaml")

    min_diam = args.min_diam if args.min_diam is not None else (float(cfg.get("detection", {}).get("min_diam_m", 1.5)) if cfg else 1.5)
    min_sep = args.min_sep if args.min_sep is not None else (float(cfg.get("detection", {}).get("min_sep_m", 1.0)) if cfg else 1.0)
    out_path = args.out_path or (cfg.path("outputs", "gis_dir") / f"{cfg.get('site',{}).get('name','study_area')}_trees_clean.geojson" if cfg else None)

    gdf = gpd.read_file(in_path)
    n_raw = len(gdf)

    # 1. Pixel-box NMS
    gdf_nms = nms_pixel_boxes(gdf, iou_thresh=args.iou)
    n_after_nms = len(gdf_nms)

    # 2. Crown-size filter
    gdf_size = filter_by_crown_size(
        gdf_nms, res_m=args.res, min_diam_m=min_diam, max_diam_m=args.max_diam
    )
    n_after_size = len(gdf_size)

    # 3. Metric centroid dedup
    gdf_final = dedup_centroids_metric(gdf_size, min_sep_m=min_sep)
    n_final = len(gdf_final)

    stats = {
        "raw_count": n_raw,
        "after_nms": n_after_nms,
        "nms_dropped": n_raw - n_after_nms,
        "after_size_filter": n_after_size,
        "size_dropped": n_after_nms - n_after_size,
        "after_centroid_dedup": n_final,
        "dedup_dropped": n_after_size - n_final,
        "total_dropped": n_raw - n_final,
        "retention_pct": round(100.0 * n_final / n_raw, 2) if n_raw else 0.0,
        "params": {
            "iou_threshold": args.iou,
            "min_diam_m": min_diam,
            "max_diam_m": args.max_diam,
            "min_separation_m": min_sep,
            "source_res_m": args.res,
        },
    }

    print("\n--- Detection cleanup ---")
    print(f"  raw detections       : {n_raw:>5}")
    print(f"  after box NMS        : {n_after_nms:>5}  (-{n_raw - n_after_nms:>3}, IoU={args.iou})")
    print(f"  after size filter    : {n_after_size:>5}  (-{n_after_nms - n_after_size:>3}, {min_diam}-{args.max_diam} m)")
    print(f"  after centroid dedup : {n_final:>5}  (-{n_after_size - n_final:>3}, min_sep={min_sep} m)")
    print(f"  retained             : {n_final:>5} / {n_raw} ({stats['retention_pct']}%)")
    print()

    if out_path:
        gdf_final.to_file(out_path, driver="GeoJSON")
        print(f"wrote clean detections -> {out_path}")

    stats_out = args.stats_out or (cfg.path("outputs", "gis_dir") / "cleanup_stats.json" if cfg else None)
    if stats_out:
        with open(stats_out, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"wrote stats -> {stats_out}")


if __name__ == "__main__":
    main()
