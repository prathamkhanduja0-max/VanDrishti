"""
upload_detect_deepforest.py -- VanDrishti

Runs the SAME DeepForest detector used by the bundled-site pipeline on an uploaded raster,
so an uploaded area receives a real crown detection rather than only the greenness heuristic.

Why this module exists separately from run_detection_large_study_area.py:
that script is a batch pipeline stage assuming a known crop and full downstream artefacts.
An upload is interactive, arbitrary in size and CRS, and must degrade gracefully rather than
abort. The detector call itself is kept identical (same release weights, same patch size,
overlap and IoU) so that counts from an upload are directly comparable to the bundled runs.

Behaviour:
  * DeepForest available and raster usable  -> real detections, method="deepforest"
  * DeepForest missing, too slow, or fails  -> caller falls back to the ExG heuristic
  * Post-filtering mirrors the bundled pipeline (crown size + centroid dedup) so that a
    number reported for an upload means the same thing as a number reported for OSBS.

Usage:
    python upload_detect_deepforest.py --raster uploads/site.tif --out out.geojson
"""

import argparse
import json
import math
import os
from pathlib import Path
import ssl
from typing import Any, Dict, Optional

try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

_cache = Path(__file__).resolve().parent.parent / ".hf_cache"
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_cache))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_cache / "hub"))

import numpy as np
import rasterio
from rasterio.transform import xy

# Matches the bundled pipeline's post-detection geometry filters so counts are comparable.
DEFAULT_MIN_DIAM_M = 1.5
DEFAULT_MAX_DIAM_M = 30.0
DEFAULT_MIN_SEPARATION_M = 2.0

# Detector settings held identical to run_detection_large_study_area.py.
PATCH_SIZE = 400
PATCH_OVERLAP = 0.25
IOU_THRESHOLD = 0.15

# Upload path is interactive; refuse rasters large enough to stall the request. The bundled
# 2500x2500 tile takes minutes on CPU, which is fine for a batch run and not for a click.
DEFAULT_MAX_PIXELS = 4_000_000       # e.g. 2000 x 2000


def _deepforest_available() -> bool:
    try:
        import deepforest  # noqa: F401
        return True
    except Exception:
        return False


def _centroid_dedup(points_m, keep_order, min_sep_m: float):
    """Greedy spatial dedup: keeps the highest-scoring crown within each separation radius.

    Mirrors the bundled pipeline's 2 m centroid dedup. Without it, an upload count would be
    inflated relative to bundled counts by the tiling overlap and would not be comparable.
    """
    kept = []
    kept_xy = []
    for idx in keep_order:
        x, y = points_m[idx]
        too_close = False
        for kx, ky in kept_xy:
            if math.hypot(x - kx, y - ky) < min_sep_m:
                too_close = True
                break
        if not too_close:
            kept.append(idx)
            kept_xy.append((x, y))
    return kept


def detect_upload_deepforest(
    raster_path: Path,
    min_diam_m: float = DEFAULT_MIN_DIAM_M,
    max_diam_m: float = DEFAULT_MAX_DIAM_M,
    min_separation_m: float = DEFAULT_MIN_SEPARATION_M,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> Dict[str, Any]:
    """Runs DeepForest on an uploaded raster and returns a GeoJSON-ready result dict.

    Always returns a dict; on any failure it sets ok=False with a reason so the caller can
    fall back to the heuristic preview instead of surfacing an error to the user.
    """
    if not _deepforest_available():
        return {"ok": False, "reason": "deepforest_not_installed",
                "detail": "DeepForest is not installed in this environment."}

    try:
        with rasterio.open(raster_path) as src:
            h, w, bands = src.height, src.width, src.count
            crs = src.crs
            transform = src.transform
            has_crs = crs is not None
            is_projected = bool(has_crs and crs.is_projected)
            res_m = (abs(transform.a) + abs(transform.e)) / 2.0 if is_projected else None
            dtype = str(src.dtypes[0])
    except Exception as e:
        return {"ok": False, "reason": "unreadable_raster", "detail": str(e)}

    if bands < 3:
        return {"ok": False, "reason": "needs_rgb",
                "detail": f"DeepForest requires 3-band RGB; raster has {bands} band(s)."}

    if dtype != "uint8":
        # DeepForest's release weights were trained on 8-bit RGB. Feeding float reflectance
        # or uint16 silently degrades detection rather than failing, so refuse explicitly.
        return {"ok": False, "reason": "needs_8bit",
                "detail": f"DeepForest release weights expect 8-bit RGB; raster is {dtype}."}

    if h * w > max_pixels:
        return {"ok": False, "reason": "too_large",
                "detail": (f"Raster is {w}x{h} ({h*w/1e6:.1f} MP); interactive detection is "
                           f"capped at {max_pixels/1e6:.1f} MP. Run the batch pipeline for "
                           f"tiles this size.")}

    try:
        from deepforest.main import deepforest
        model = deepforest()
        if hasattr(model, "use_release"):
            model.use_release()
        preds = model.predict_tile(
            path=str(raster_path),
            patch_size=PATCH_SIZE,
            patch_overlap=PATCH_OVERLAP,
            iou_threshold=IOU_THRESHOLD,
        )
    except Exception as e:
        return {"ok": False, "reason": "inference_failed", "detail": str(e)}

    if preds is None or len(preds) == 0:
        return {"ok": True, "count": 0, "raw_count": 0, "method": "deepforest",
                "geojson": {"type": "FeatureCollection", "features": []},
                "filters": {}, "notes": ["DeepForest returned no detections."]}

    raw_count = int(len(preds))

    xmin = preds["xmin"].to_numpy(dtype=float)
    ymin = preds["ymin"].to_numpy(dtype=float)
    xmax = preds["xmax"].to_numpy(dtype=float)
    ymax = preds["ymax"].to_numpy(dtype=float)
    score = preds["score"].to_numpy(dtype=float) if "score" in preds else np.ones(raw_count)

    cx_px = (xmin + xmax) / 2.0
    cy_px = (ymin + ymax) / 2.0
    wid_px = xmax - xmin
    hei_px = ymax - ymin

    notes = []
    size_dropped = 0

    if res_m:
        diam_m = ((wid_px + hei_px) / 2.0) * res_m
        keep_mask = (diam_m >= min_diam_m) & (diam_m <= max_diam_m)
        size_dropped = int((~keep_mask).sum())
    else:
        # No ground scale: size filtering in metres is undefined. Skipping it is correct;
        # applying it in pixel units would silently mean a different thing per raster.
        diam_m = np.full(raw_count, np.nan)
        keep_mask = np.ones(raw_count, dtype=bool)
        notes.append(
            "No projected CRS: crown-size filtering (m) and centroid dedup were skipped, so "
            "this count is not directly comparable to bundled-site counts.")

    idx_kept = np.where(keep_mask)[0]
    order = idx_kept[np.argsort(score[idx_kept])[::-1]]   # highest score first

    if res_m:
        pts_m = {}
        for i in order:
            gx, gy = xy(transform, cy_px[i], cx_px[i])
            pts_m[i] = (gx, gy)
        final_idx = _centroid_dedup(pts_m, list(order), min_separation_m)
        dedup_dropped = len(order) - len(final_idx)
    else:
        final_idx = list(order)
        dedup_dropped = 0

    features = []
    for n, i in enumerate(sorted(final_idx), 1):
        if has_crs:
            gx, gy = xy(transform, cy_px[i], cx_px[i])
        else:
            gx, gy = float(cx_px[i]), float(cy_px[i])
        props = {
            "tree_id": n,
            "score": round(float(score[i]), 4),
            "pixel_x": int(cx_px[i]),
            "pixel_y": int(cy_px[i]),
            "georeferenced": bool(has_crs),
        }
        if res_m:
            props["crown_diam_m"] = round(float(diam_m[i]), 2)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(gx, 7), round(gy, 7)]},
            "properties": props,
        })

    notes.append(
        "DeepForest confidence scores are not calibrated uncertainties: on the bundled site "
        "they track crown size rather than correctness, so they should be used for ranking "
        "review order only, not as probability of a true detection.")

    return {
        "ok": True,
        "method": "deepforest",
        "count": len(features),
        "raw_count": raw_count,
        "filters": {
            "size_dropped": size_dropped,
            "dedup_dropped": dedup_dropped,
            "min_diam_m": min_diam_m,
            "max_diam_m": max_diam_m,
            "min_separation_m": min_separation_m,
            "res_m": round(res_m, 4) if res_m else None,
        },
        "detector_params": {
            "patch_size": PATCH_SIZE,
            "patch_overlap": PATCH_OVERLAP,
            "iou_threshold": IOU_THRESHOLD,
            "weights": "deepforest release (NEON-pretrained RetinaNet)",
        },
        "notes": notes,
        "geojson": {
            "type": "FeatureCollection",
            "crs": {"type": "name",
                    "properties": {"name": str(crs) if has_crs else "UNREFERENCED"}},
            "features": features,
        },
    }


def main():
    ap = argparse.ArgumentParser(description="DeepForest detection on an uploaded raster")
    ap.add_argument("--raster", required=True)
    ap.add_argument("--out", default=None, help="write GeoJSON here")
    ap.add_argument("--max-pixels", type=int, default=DEFAULT_MAX_PIXELS)
    args = ap.parse_args()

    res = detect_upload_deepforest(Path(args.raster), max_pixels=args.max_pixels)

    if not res.get("ok"):
        print(f"DeepForest unavailable for this raster: {res['reason']}")
        print(f"  {res['detail']}")
        print("  -> caller should fall back to the ExG greenness preview")
        return

    f = res["filters"]
    print(f"DeepForest detections: {res['count']:,}  (raw {res['raw_count']:,})")
    print(f"  size filter dropped : {f.get('size_dropped')}")
    print(f"  dedup dropped       : {f.get('dedup_dropped')}")
    for n in res["notes"]:
        print(f"  note: {n}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(res["geojson"], fh)
        print(f"  geojson -> {args.out}")


if __name__ == "__main__":
    main()
