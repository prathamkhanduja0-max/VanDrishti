"""
clean_detections.py  -- VanDrishti  (v2, adapted to actual repo schema)

SCHEMA THIS EXPECTS (confirmed from recon):
  geometry   : Point (geo_easting, geo_northing) in EPSG:32617
  confidence : float, column name is "confidence"  (NOT "score")
  pixel_xmin / pixel_ymin / pixel_xmax / pixel_ymax : bbox in PIXEL coords

Because geometry is Point, box IoU cannot be computed from geometry directly.
This module reconstructs boxes from the pixel_* attributes, runs NMS in pixel
space, then applies metric filters using the raster resolution.

Passes:
  1. Box NMS in pixel space  (fixes DeepForest IoU=0.15 over-detection)
  2. Crown-size sanity filter (converted to metres via --res)
  3. Centroid dedup in metres (catches duplicates NMS missed)

Expected outcome: the 684 count WILL drop. That is duplicate removal, not
information loss. Record BOTH numbers -- the before/after pair is a result.

Usage:
    python scripts/clean_detections.py \
        --in  results/gis/OSBS_large_2019_trees.geojson \
        --out results/gis/OSBS_large_2019_trees_clean.geojson \
        --res 0.1 --iou 0.35 --min-sep 2.0 \
        --stats-out results/gis/cleanup_stats.json
"""

import argparse
import json

import geopandas as gpd
import numpy as np

BBOX_COLS = ["pixel_xmin", "pixel_ymin", "pixel_xmax", "pixel_ymax"]


def _require_cols(gdf, cols, what):
    missing = [c for c in cols if c not in gdf.columns]
    if missing:
        raise KeyError(
            f"{what}: missing column(s) {missing}. "
            f"Available: {list(gdf.columns)}"
        )


# --------------------------------------------------------------------------
# 1. NMS on reconstructed pixel boxes
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# 2. Crown-size filter (pixel bbox -> metres)
# --------------------------------------------------------------------------
def filter_by_crown_size(gdf, res_m=0.1, min_diam_m=1.5, max_diam_m=30.0):
    """res_m = ground sample distance of the source raster (NEON RGB = 0.1)."""
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


# --------------------------------------------------------------------------
# 3. Centroid dedup in metres
# --------------------------------------------------------------------------
def dedup_centroids(gdf, min_sep_m=2.0, score_col="confidence"):
    if gdf.empty:
        return gdf

    if gdf.crs is not None and gdf.crs.is_geographic:
        raise ValueError(
            f"dedup_centroids needs a projected CRS in metres, got {gdf.crs}. "
            "Run this BEFORE reproject_frontend_data.py, on the EPSG:32617 file."
        )

    pts = gdf.geometry.centroid
    xy = np.column_stack([pts.x.to_numpy(), pts.y.to_numpy()])
    scores = gdf[score_col].to_numpy(dtype=np.float64)

    order = scores.argsort()[::-1]
    taken = []
    keep = []

    for idx in order:
        p = xy[idx]
        if taken:
            d = np.linalg.norm(np.asarray(taken) - p, axis=1)
            if d.min() < min_sep_m:
                continue
        taken.append(p)
        keep.append(idx)

    return gdf.iloc[sorted(keep)].copy()


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
def clean(gdf, res_m=0.1, iou_thresh=0.35, min_diam_m=1.5, max_diam_m=30.0,
          min_sep_m=2.0, score_col="confidence", verbose=True):

    stats = {
        "input": int(len(gdf)),
        "params": {
            "res_m": res_m, "iou": iou_thresh, "min_diam_m": min_diam_m,
            "max_diam_m": max_diam_m, "min_sep_m": min_sep_m,
        },
    }

    gdf = nms_pixel_boxes(gdf, iou_thresh, score_col)
    stats["after_nms"] = int(len(gdf))

    gdf = filter_by_crown_size(gdf, res_m, min_diam_m, max_diam_m)
    stats["after_size_filter"] = int(len(gdf))

    gdf = dedup_centroids(gdf, min_sep_m, score_col)
    stats["after_centroid_dedup"] = int(len(gdf))

    removed = stats["input"] - stats["after_centroid_dedup"]
    stats["removed"] = int(removed)
    stats["removed_pct"] = round(
        100.0 * removed / stats["input"], 2) if stats["input"] else 0.0

    if verbose:
        print("\n--- Detection cleanup ---")
        for k in ["input", "after_nms", "after_size_filter",
                  "after_centroid_dedup", "removed", "removed_pct"]:
            print(f"  {k:<22}: {stats[k]}")
        print("  (a drop is duplicate removal -- report both numbers)\n")

    return gdf, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--res", type=float, default=0.1,
                    help="raster ground sample distance in metres (NEON RGB = 0.1)")
    ap.add_argument("--iou", type=float, default=0.35)
    ap.add_argument("--min-diam", type=float, default=1.5)
    ap.add_argument("--max-diam", type=float, default=30.0)
    ap.add_argument("--min-sep", type=float, default=2.0)
    ap.add_argument("--score-col", default="confidence")
    ap.add_argument("--stats-out", default=None)
    args = ap.parse_args()

    gdf = gpd.read_file(args.inp)
    print(f"read {len(gdf)} features, CRS={gdf.crs}")

    out, stats = clean(
        gdf, res_m=args.res, iou_thresh=args.iou,
        min_diam_m=args.min_diam, max_diam_m=args.max_diam,
        min_sep_m=args.min_sep, score_col=args.score_col,
    )

    out.to_file(args.out, driver="GeoJSON")
    print(f"wrote {len(out)} features -> {args.out}")

    if args.stats_out:
        with open(args.stats_out, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"wrote stats -> {args.stats_out}")


if __name__ == "__main__":
    main()
