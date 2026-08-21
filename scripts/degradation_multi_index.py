"""
degradation_multi_index.py  -- VanDrishti
Fixes the two real problems with your 2018-vs-2019 ExG change detection.

PROBLEM 1 -- radiometric confound.
Two flights = different sun angle, atmosphere, phenology. A delta of -0.15
can be genuine canopy loss OR just a dimmer day. Fixed here with histogram
matching (2018 matched to 2019 reference) before any index is computed.
This is the single highest-value fix in the whole project: without it your
degradation finding may simply be wrong.

PROBLEM 2 -- single index.
ExG alone is noisy. Here three RGB indices vote:

    ExG  = 2g - r - b                 (chromatic coords)
    VARI = (G - R) / (G + R - B)
    GLI  = (2G - R - B) / (2G + R + B)

A pixel is flagged as loss only if >= `min_votes` indices agree. This kills
most false positives at essentially zero cost -- no new data needed.

Usage:
    python degradation_multi_index.py --t1 data/raw/neon/osbs_2018.tif \
                                      --t2 data/raw/neon/osbs_2019.tif \
                                      --out-raster results/gis/loss_mask.tif \
                                      --out-vector results/gis/loss_polys.geojson
"""

import argparse

import numpy as np
import rasterio
from rasterio.features import shapes
from skimage.exposure import match_histograms

import geopandas as gpd
from shapely.geometry import shape


# --------------------------------------------------------------------------
# Vegetation indices
# --------------------------------------------------------------------------
def _chromatic(rgb):
    r, g, b = (rgb[i].astype(np.float64) for i in range(3))
    total = r + g + b
    total[total == 0] = 1.0
    return r / total, g / total, b / total


def exg(rgb):
    rn, gn, bn = _chromatic(rgb)
    return 2.0 * gn - rn - bn


def vari(rgb):
    r, g, b = (rgb[i].astype(np.float64) for i in range(3))
    den = g + r - b
    den[np.abs(den) < 1e-6] = np.nan          # VARI is unstable when g+r ~ b
    return (g - r) / den


def gli(rgb):
    r, g, b = (rgb[i].astype(np.float64) for i in range(3))
    den = 2.0 * g + r + b
    den[den == 0] = np.nan
    return (2.0 * g - r - b) / den


INDICES = {"ExG": exg, "VARI": vari, "GLI": gli}


# --------------------------------------------------------------------------
# Radiometric normalisation
# --------------------------------------------------------------------------
def histogram_match(src_rgb, ref_rgb):
    """Match src to ref band-by-band.

    Assumes both cover the same footprint and are already co-registered.
    If they are NOT co-registered, fix that first -- histogram matching will
    happily produce a confident, meaningless result on misaligned tiles.
    """
    matched = match_histograms(
        np.moveaxis(src_rgb, 0, -1).astype(np.float64),
        np.moveaxis(ref_rgb, 0, -1).astype(np.float64),
        channel_axis=-1,
    )
    return np.moveaxis(matched, -1, 0)


# --------------------------------------------------------------------------
# Change detection
# --------------------------------------------------------------------------
def detect_loss(
    rgb_t1,
    rgb_t2,
    z_thresh=-1.5,
    min_votes=2,
    do_match=True,
    verbose=True,
):
    """Returns (loss_mask, per_index_deltas, diagnostics).

    Each index's delta is z-normalised, then thresholded at z_thresh. Using
    z-units lets ONE threshold work across indices whose natural ranges differ
    (ExG spans ~[-1,2], VARI is unbounded). z_thresh=-1.5 means "this pixel
    greened-down 1.5 standard deviations more than the tile average".

    Because it is relative to the tile, this is robust to a uniform brightness
    shift -- but it also means it can never report "the whole tile declined".
    State that limitation in the report; it is the honest trade-off.
    """
    if do_match:
        rgb_t1 = histogram_match(rgb_t1, rgb_t2)

    votes = np.zeros(rgb_t1.shape[1:], dtype=np.int16)
    deltas = {}

    for name, fn in INDICES.items():
        d = fn(rgb_t2) - fn(rgb_t1)

        mu = np.nanmean(d)
        sd = np.nanstd(d)
        dz = (d - mu) / sd if sd > 1e-9 else np.zeros_like(d)

        deltas[name] = dz
        votes += np.nan_to_num(dz <= z_thresh, nan=0).astype(np.int16)

    loss_mask = votes >= min_votes

    diag = {
        "pixels_total": int(votes.size),
        "pixels_flagged": int(loss_mask.sum()),
        "pct_flagged": float(100.0 * loss_mask.sum() / votes.size),
        "histogram_matched": do_match,
        "min_votes": min_votes,
        "z_thresh": z_thresh,
    }
    for name, dz in deltas.items():
        diag[f"{name}_flagged"] = int(np.nan_to_num(dz <= z_thresh).sum())

    if verbose:
        print("\n--- Multi-index degradation ---")
        for k, v in diag.items():
            print(f"  {k:<20}: {v}")
        if diag["pct_flagged"] > 25:
            print(
                "\n  WARNING: >25% of the tile flagged as loss. That is very\n"
                "  high for one year. Most likely cause is residual radiometric\n"
                "  mismatch or misregistration, not actual deforestation.\n"
                "  Check a few flagged patches visually before reporting.\n"
            )
        print()

    return loss_mask, deltas, diag


# --------------------------------------------------------------------------
# Vectorise
# --------------------------------------------------------------------------
def vectorise(mask, transform, crs, min_area_m2=4.0):
    """Polygonise the mask, dropping specks smaller than min_area_m2."""
    geoms, vals = [], []
    for geom, val in shapes(mask.astype(np.uint8), mask=mask, transform=transform):
        if val == 1:
            geoms.append(shape(geom))
            vals.append(val)

    if not geoms:
        return gpd.GeoDataFrame({"geometry": []}, crs=crs)

    gdf = gpd.GeoDataFrame({"class": vals, "geometry": geoms}, crs=crs)
    gdf["area_m2"] = gdf.area
    gdf = gdf[gdf["area_m2"] >= min_area_m2].reset_index(drop=True)
    return gdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t1", required=True, help="earlier orthomosaic (2018)")
    ap.add_argument("--t2", required=True, help="later orthomosaic (2019)")
    ap.add_argument("--out-raster", default=None)
    ap.add_argument("--out-vector", default=None)
    ap.add_argument("--z-thresh", type=float, default=-1.5,
                    help="z-score threshold per index (more negative = stricter)")
    ap.add_argument("--min-votes", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--no-match", action="store_true",
                    help="skip histogram matching (for ablation -- run BOTH "
                         "ways and report the difference, it is a good result)")
    ap.add_argument("--min-area", type=float, default=4.0)
    args = ap.parse_args()

    with rasterio.open(args.t1) as a:
        rgb1 = a.read([1, 2, 3])
        prof = a.profile.copy()
    with rasterio.open(args.t2) as b:
        rgb2 = b.read([1, 2, 3])
        if rgb2.shape != rgb1.shape:
            raise ValueError(
                f"shape mismatch t1={rgb1.shape} t2={rgb2.shape}. "
                "Clip/resample both to the same grid first."
            )

    mask, deltas, diag = detect_loss(
        rgb1, rgb2,
        z_thresh=args.z_thresh,
        min_votes=args.min_votes,
        do_match=not args.no_match,
    )

    if args.out_raster:
        prof.update(dtype="uint8", count=1, compress="lzw", nodata=0)
        with rasterio.open(args.out_raster, "w", **prof) as dst:
            dst.write(mask.astype(np.uint8), 1)
        print(f"wrote loss mask -> {args.out_raster}")

    if args.out_vector:
        gdf = vectorise(mask, prof["transform"], prof["crs"], args.min_area)
        gdf.to_file(args.out_vector, driver="GeoJSON")
        print(f"wrote {len(gdf)} loss polygons -> {args.out_vector}")


if __name__ == "__main__":
    main()
