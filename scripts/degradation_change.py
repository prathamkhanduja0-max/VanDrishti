"""
degradation_change.py
Module 4: Vegetation Greenness-Change Detection (2018 vs 2019).
Performs multi-temporal Excess Green (ExG = 2G - R - B) change detection between
2018 and 2019 NEON aerial orthomosaics over OSBS_022 (40m x 40m).
Saves delta GeoTIFF, vectorized significant loss polygons GeoJSON, and a 3-panel comparison map.
"""

from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.windows import from_bounds
from shapely.geometry import shape


def run_degradation_change():
    project_root = Path(__file__).resolve().parent.parent
    gis_results_dir = project_root / "results" / "gis"
    gis_results_dir.mkdir(parents=True, exist_ok=True)

    # 1. Input tile paths
    path_2019 = project_root / "data" / "raw" / "neon" / "test" / "OSBS_022_2019.tif"
    if not path_2019.exists():
        path_2019 = project_root / "data" / "processed" / "yolo" / "images" / "test" / "OSBS_022_2019.tif"

    zip_path = project_root / "data" / "raw" / "NEON_images-camera-ortho-mosaic.zip"
    zip_vsi_path = (
        f"/vsizip/{zip_path.as_posix()}/"
        "NEON_images-camera-ortho-mosaic/"
        "NEON.D03.OSBS.DP3.30010.001.2018-09.basic.20260820T165613Z.RELEASE-2026/"
        "2018_OSBS_4_407000_3284000_image.tif"
    )

    out_delta_tif = gis_results_dir / "OSBS_022_greenness_change.tif"
    out_loss_geojson = gis_results_dir / "OSBS_022_degradation_zones.geojson"
    out_map_png = gis_results_dir / "OSBS_022_degradation_map.png"

    print("=" * 82)
    print("      VAN-DRISHTI: MULTI-TEMPORAL VEGETATION GREENNESS-CHANGE (2018 vs 2019)")
    print("=" * 82)

    # 2. Read 2019 tile and spatial metadata
    print("=== Step 1: Reading 2019 Reference Tile ===")
    with rasterio.open(path_2019) as ds19:
        b19 = ds19.bounds
        crs19 = ds19.crs
        t19 = ds19.transform
        rgb19_raw = ds19.read()  # (3, 400, 400) uint8
        profile19 = ds19.profile

    print(f"2019 Tile Path:   {path_2019}")
    print(f"CRS:              {crs19}")
    print(f"Bounds:           Left={b19.left:.2f}, Bottom={b19.bottom:.2f}, Right={b19.right:.2f}, Top={b19.top:.2f}")
    print(f"Dimensions:       {ds19.width}x{ds19.height} px ({b19.right - b19.left:.1f}m x {b19.top - b19.bottom:.1f}m)")

    # 3. Read & Crop 2018 Full Tile to exact 2019 extent
    print("\n=== Step 2: Extracting Co-Registered 2018 Extent ===")
    with rasterio.open(zip_vsi_path) as ds18:
        print(f"2018 Full Tile:   1000m x 1000m ({ds18.width}x{ds18.height} px)")
        win18 = from_bounds(b19.left, b19.bottom, b19.right, b19.top, ds18.transform).round_lengths().round_offsets()
        rgb18_raw = ds18.read(window=win18, out_shape=(3, 400, 400))

    print(f"2018 Crop Shape:  {rgb18_raw.shape} (Matches 2019: {rgb18_raw.shape == rgb19_raw.shape})")

    # 4. Compute Excess Green Index (ExG = 2G - R - B)
    print("\n=== Step 3: Computing Excess Green (ExG) Vegetation Index ===")
    rgb18 = rgb18_raw.astype(np.float64)
    rgb19 = rgb19_raw.astype(np.float64)

    exg18_raw = 2.0 * rgb18[1] - rgb18[0] - rgb18[2]
    exg19_raw = 2.0 * rgb19[1] - rgb19[0] - rgb19[2]

    # Normalization: Map natural ExG range [-80, +120] to [0.0, 1.0]
    norm_min, norm_max = -80.0, 120.0
    exg18_norm = np.clip((exg18_raw - norm_min) / (norm_max - norm_min), 0.0, 1.0)
    exg19_norm = np.clip((exg19_raw - norm_min) / (norm_max - norm_min), 0.0, 1.0)

    print(f"ExG Normalization Method: Fixed min-max scaling [Range: {norm_min} to +{norm_max} mapped to 0.0-1.0]")
    print(f"2018 Normalized ExG: Min={exg18_norm.min():.3f}, Mean={exg18_norm.mean():.3f}, Max={exg18_norm.max():.3f}")
    print(f"2019 Normalized ExG: Min={exg19_norm.min():.3f}, Mean={exg19_norm.mean():.3f}, Max={exg19_norm.max():.3f}")

    # 5. Compute Change: Delta = ExG_2019 - ExG_2018
    print("\n=== Step 4: Quantifying Multi-Temporal Greenness Delta ===")
    delta_exg = (exg19_norm - exg18_norm).astype(np.float32)

    print(f"Delta ExG (2019 - 2018): Min={delta_exg.min():.3f}, Mean={delta_exg.mean():.3f}, Max={delta_exg.max():.3f}, Std={delta_exg.std():.3f}")

    # 6. Change Classification
    total_pixels = delta_exg.size  # 160,000 pixels = 1600 sq m
    sig_loss_mask = delta_exg <= -0.15
    minor_loss_mask = (delta_exg > -0.15) & (delta_exg <= -0.05)
    stable_mask = (delta_exg > -0.05) & (delta_exg < 0.05)
    gain_mask = delta_exg >= 0.05

    pct_sig_loss = (sig_loss_mask.sum() / total_pixels) * 100.0
    pct_minor_loss = (minor_loss_mask.sum() / total_pixels) * 100.0
    pct_stable = (stable_mask.sum() / total_pixels) * 100.0
    pct_gain = (gain_mask.sum() / total_pixels) * 100.0

    area_sig_loss_m2 = sig_loss_mask.sum() * 0.01  # each 0.1m x 0.1m pixel = 0.01 sq m
    area_minor_loss_m2 = minor_loss_mask.sum() * 0.01
    area_stable_m2 = stable_mask.sum() * 0.01
    area_gain_m2 = gain_mask.sum() * 0.01

    # 7. Save Single-Band Delta GeoTIFF
    print("\n=== Step 5: Saving Greenness Change GeoTIFF ===")
    delta_profile = profile19.copy()
    delta_profile.update(
        driver="GTiff",
        count=1,
        dtype="float32",
        nodata=-9999.0,
    )
    with rasterio.open(out_delta_tif, "w", **delta_profile) as dst:
        dst.write(delta_exg, 1)
    print(f"[+] Saved Change GeoTIFF to: {out_delta_tif}")

    # 8. Vectorize Significant Loss Zones to GeoJSON
    print("\n=== Step 6: Vectorizing Significant Loss Zones ===")
    sig_loss_uint8 = sig_loss_mask.astype(np.uint8)
    loss_features = []

    for geom, val in shapes(sig_loss_uint8, mask=sig_loss_mask, transform=t19):
        poly = shape(geom)
        if poly.area >= 0.50:  # Retain cohesive patches >= 0.50 sq m (50 pixels)
            loss_features.append({
                "zone_id": len(loss_features) + 1,
                "change_class": "Significant Loss",
                "threshold": "<= -0.15 Delta ExG",
                "area_sq_m": round(poly.area, 2),
                "geometry": poly,
            })

    if loss_features:
        gdf_loss = gpd.GeoDataFrame(loss_features, crs=crs19)
    else:
        gdf_loss = gpd.GeoDataFrame(
            columns=["zone_id", "change_class", "threshold", "area_sq_m", "geometry"],
            geometry="geometry",
            crs=crs19,
        )

    gdf_loss.to_file(out_loss_geojson, driver="GeoJSON")
    print(f"[+] Saved {len(gdf_loss)} Significant Loss Zone polygons to: {out_loss_geojson}")

    # 9. Generate 3-Panel Figure Map
    print("\n=== Step 7: Generating 3-Panel Visual Comparison Map ===")
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.5), dpi=160)
    extent = [b19.left, b19.right, b19.bottom, b19.top]

    # Panel A: 2018 RGB
    rgb18_disp = np.transpose(rgb18_raw, (1, 2, 0))
    axes[0].imshow(rgb18_disp, extent=extent, origin="upper")
    axes[0].set_title("(a) September 2018 Baseline (RGB)", fontsize=11, fontweight="bold")
    axes[0].set_xlabel("Easting (m)", fontsize=9)
    axes[0].set_ylabel("Northing (m)", fontsize=9)
    axes[0].grid(True, linestyle=":", alpha=0.3, color="white")

    # Panel B: 2019 RGB
    rgb19_disp = np.transpose(rgb19_raw, (1, 2, 0))
    axes[1].imshow(rgb19_disp, extent=extent, origin="upper")
    axes[1].set_title("(b) 2019 Monitoring State (RGB)", fontsize=11, fontweight="bold")
    axes[1].set_xlabel("Easting (m)", fontsize=9)
    axes[1].grid(True, linestyle=":", alpha=0.3, color="white")

    # Panel C: Delta ExG Heatmap
    im_c = axes[2].imshow(
        delta_exg,
        extent=extent,
        origin="upper",
        cmap="RdYlGn",
        vmin=-0.35,
        vmax=0.35,
    )
    cbar = plt.colorbar(im_c, ax=axes[2], fraction=0.046, pad=0.04)
    cbar.set_label("Greenness Delta (ExG 2019 - ExG 2018)", fontsize=9, fontweight="bold")

    # Overlay significant loss polygon outlines
    if not gdf_loss.empty:
        gdf_loss.boundary.plot(ax=axes[2], color="black", linewidth=1.2, linestyle="-", label="Significant Loss Polygons")

    axes[2].set_title("(c) Multi-Temporal Greenness Change", fontsize=11, fontweight="bold")
    axes[2].set_xlabel("Easting (m)", fontsize=9)
    axes[2].grid(True, linestyle=":", alpha=0.3, color="gray")

    # Summary Stats Overlay Box in Panel C
    summary_box_text = (
        f"Change Classification Breakdown:\n"
        f"-------------------------------\n"
        f"Significant Loss (<= -0.15): {pct_sig_loss:.1f}% ({area_sig_loss_m2:.1f} m2)\n"
        f"Minor Loss (-0.15 to -0.05): {pct_minor_loss:.1f}% ({area_minor_loss_m2:.1f} m2)\n"
        f"Stable (-0.05 to +0.05):     {pct_stable:.1f}% ({area_stable_m2:.1f} m2)\n"
        f"Gain (>= +0.05):             {pct_gain:.1f}% ({area_gain_m2:.1f} m2)"
    )
    axes[2].text(
        0.03,
        0.04,
        summary_box_text,
        transform=axes[2].transAxes,
        fontsize=8,
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.90, ec="gray"),
        zorder=5,
    )

    fig.suptitle(
        "VanDrishti: Canopy Greenness-Change & Degradation Analysis (OSBS_022 | 2018 vs 2019)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout()

    plt.savefig(out_map_png, dpi=200)
    plt.close()
    print(f"[+] Saved 3-Panel Comparison Map to: {out_map_png}")

    # 10. Summary Report
    print("\n" + "=" * 82)
    print("                   VEGETATION GREENNESS CHANGE REPORT")
    print("=" * 82)
    print(f"{'Change Class':<22} | {'Delta Threshold':<20} | {'Area (%)':<10} | {'Area (sq m)'}")
    print("-" * 82)
    print(f"{'Significant Loss':<22} | {'Delta <= -0.15':<20} | {pct_sig_loss:<9.2f}% | {area_sig_loss_m2:.2f} m2")
    print(f"{'Minor Loss':<22} | {'-0.15 < Delta <= -0.05':<20} | {pct_minor_loss:<9.2f}% | {area_minor_loss_m2:.2f} m2")
    print(f"{'Stable':<22} | {'-0.05 < Delta < +0.05':<20} | {pct_stable:<9.2f}% | {area_stable_m2:.2f} m2")
    print(f"{'Vegetation Gain':<22} | {'Delta >= +0.05':<20} | {pct_gain:<9.2f}% | {area_gain_m2:.2f} m2")
    print("=" * 82)
    print(f"Total Tile Area Analyzed:       1,600.00 sq m (400 x 400 pixels @ 0.10 m/px)")
    print(f"Significant Loss Zones Vectorized: {len(gdf_loss)} polygon features (>= 0.50 sq m)")
    print("\nMethodological Limitations:")
    print("  - RGB-Only Proxy: Uses Excess Green Index (ExG = 2G - R - B) rather than multispectral NIR/NDVI.")
    print("  - Bi-Temporal Screening: Analysis compares two discrete airborne acquisitions (2018-09 vs 2019).")
    print("  - Environmental Factors: Variations in sun elevation angle, shadow geometry, and atmospheric")
    print("    moisture can modulate apparent RGB greenness; values indicate potential canopy disruption")
    print("    rather than definitive field-measured timber biomass loss.")
    print("=" * 82)

    return {
        "crop_matched": bool(rgb18_raw.shape == rgb19_raw.shape),
        "shape": rgb19_raw.shape,
        "classes_pct": {
            "significant_loss": pct_sig_loss,
            "minor_loss": pct_minor_loss,
            "stable": pct_stable,
            "gain": pct_gain,
        },
        "significant_loss_polygons": len(gdf_loss),
        "delta_tif": str(out_delta_tif),
        "loss_geojson": str(out_loss_geojson),
        "map_png": str(out_map_png),
    }


if __name__ == "__main__":
    run_degradation_change()
