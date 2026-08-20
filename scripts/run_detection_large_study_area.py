"""
run_detection_large_study_area.py
Crops the 250m x 250m densest sub-window of the 2019 OSBS 1km tile,
runs DeepForest tree detection with predict_tile (patch_size=400, patch_overlap=0.25),
generates geocoded tree point predictions in EPSG:32617,
and saves the GeoJSON and map visualization.
"""

from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_bounds, xy
from rasterio.windows import Window
from shapely.geometry import Point
from deepforest.main import deepforest


def crop_250m_tile(src_tif: Path, dst_tif: Path):
    """Crops the densest 250m x 250m window from the 1km tile and writes GeoTIFF."""
    print(f"--- Step 1: Cropping 250m x 250m Window from {src_tif.name} ---")
    
    col_off = 7000
    row_off = 0
    width_px = 2500
    height_px = 2500
    
    # Target UTM bounds (EPSG:32617)
    left = 407700.0
    bottom = 3283750.0
    right = 407950.0
    top = 3284000.0
    
    window = Window(col_off=col_off, row_off=row_off, width=width_px, height=height_px)
    
    with rasterio.open(src_tif) as src:
        src_crs = src.crs
        crop_data = src.read(window=window)
        # Verify shape
        print(f"Source CRS: {src_crs}")
        print(f"Cropped data shape: {crop_data.shape} (Bands, Height, Width)")
        
        # New transform for the cropped tile
        crop_transform = from_bounds(left, bottom, right, top, width_px, height_px)
        
        profile = src.profile.copy()
        profile.update({
            "crs": src_crs,
            "transform": crop_transform,
            "width": width_px,
            "height": height_px,
            "count": src.count,
            "dtype": crop_data.dtype,
            "driver": "GTiff"
        })
        
        dst_tif.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_tif, "w", **profile) as dst:
            dst.write(crop_data)
            
    print(f"Successfully saved cropped GeoTIFF: {dst_tif}")
    print(f"Bounds: Left={left}, Bottom={bottom}, Right={right}, Top={top}")
    print(f"Pixel Dimensions: {width_px} x {height_px}")
    return left, bottom, right, top, src_crs


def run_deepforest_detection(tif_path: Path):
    """Initializes DeepForest and runs predict_tile on the cropped GeoTIFF."""
    print(f"\n--- Step 2: Running DeepForest Tree Detection ---")
    print("Initializing DeepForest release model...")
    model = deepforest()
    if hasattr(model, "use_release"):
        model.use_release()
        
    print("Executing model.predict_tile(patch_size=400, patch_overlap=0.25)...")
    # predict_tile splits the 2500x2500 image into 400x400 patches with 25% overlap
    preds = model.predict_tile(
        path=str(tif_path),
        patch_size=400,
        patch_overlap=0.25,
        iou_threshold=0.15
    )
    
    if preds is None or preds.empty:
        print("Warning: No trees predicted!")
        return pd.DataFrame(columns=["xmin", "ymin", "xmax", "ymax", "label", "score"])
        
    print(f"Raw tree predictions count: {len(preds)}")
    return preds


def process_and_save_results(
    tif_path: Path,
    preds_df: pd.DataFrame,
    out_geojson: Path,
    out_map: Path,
    bounds: tuple
):
    """Converts predictions to georeferenced GeoDataFrame, saves GeoJSON, and plots map."""
    print(f"\n--- Step 3: Georeferencing Tree Points & Creating GIS Outputs ---")
    left, bottom, right, top = bounds
    
    with rasterio.open(tif_path) as src:
        transform = src.transform
        crs = src.crs
        rgb_data = src.read([1, 2, 3])
        rgb_img = np.transpose(rgb_data, (1, 2, 0))
        if rgb_img.max() > 1.0:
            rgb_img = rgb_img.astype(np.uint8)

    score_col = "score" if "score" in preds_df.columns else "confidence"
    
    geo_points = []
    tree_records = []
    
    for idx, row in preds_df.iterrows():
        xmin, ymin, xmax, ymax = float(row["xmin"]), float(row["ymin"]), float(row["xmax"]), float(row["ymax"])
        score = float(row[score_col])
        label = row.get("label", "Tree")
        
        # Pixel center
        px_cx = (xmin + xmax) / 2.0
        px_cy = (ymin + ymax) / 2.0
        
        # Geographic coordinates in EPSG:32617
        geo_x, geo_y = xy(transform, px_cy, px_cx)
        
        geo_points.append(Point(geo_x, geo_y))
        tree_records.append({
            "tree_id": idx + 1,
            "label": label,
            "confidence": round(score, 4),
            "pixel_xmin": round(xmin, 2),
            "pixel_ymin": round(ymin, 2),
            "pixel_xmax": round(xmax, 2),
            "pixel_ymax": round(ymax, 2),
            "pixel_center_x": round(px_cx, 2),
            "pixel_center_y": round(px_cy, 2),
            "geo_easting": round(geo_x, 3),
            "geo_northing": round(geo_y, 3)
        })
        
    gdf_trees = gpd.GeoDataFrame(tree_records, geometry=geo_points, crs=crs)
    
    # Save GeoJSON
    out_geojson.parent.mkdir(parents=True, exist_ok=True)
    gdf_trees.to_file(out_geojson, driver="GeoJSON")
    print(f"Saved GeoJSON to: {out_geojson}")
    
    # Generate Map Visualization
    print(f"Generating detection map visualization...")
    fig, ax = plt.subplots(figsize=(12, 12), dpi=200)
    extent = [left, right, bottom, top]
    ax.imshow(rgb_img, extent=extent, origin="upper")
    
    # Plot Tree bounding boxes and centers
    # To draw bounding boxes on geo coordinates:
    for _, row in gdf_trees.iterrows():
        # Convert box pixel corners to geo
        g_xmin, g_ymax_box = xy(transform, row["pixel_ymin"], row["pixel_xmin"])
        g_xmax, g_ymin_box = xy(transform, row["pixel_ymax"], row["pixel_xmax"])
        box_w = g_xmax - g_xmin
        box_h = g_ymax_box - g_ymin_box
        
        # Color by confidence: bright yellow for high, orange for moderate
        box_color = "#00FF66" if row["confidence"] >= 0.5 else "#FFB703"
        rect = patches.Rectangle(
            (g_xmin, g_ymin_box),
            box_w,
            box_h,
            linewidth=1.2,
            edgecolor=box_color,
            facecolor="none",
            alpha=0.85,
            zorder=3
        )
        ax.add_patch(rect)
    
    # Plot Point centroids
    gdf_high = gdf_trees[gdf_trees["confidence"] >= 0.5]
    gdf_low = gdf_trees[gdf_trees["confidence"] < 0.5]
    
    if not gdf_high.empty:
        gdf_high.plot(
            ax=ax,
            color="#00FF66",
            edgecolor="darkgreen",
            markersize=35,
            linewidth=0.8,
            marker="o",
            label=f"Tree Crown (Conf >= 0.5, n={len(gdf_high)})",
            zorder=4
        )
    if not gdf_low.empty:
        gdf_low.plot(
            ax=ax,
            color="#FFB703",
            edgecolor="darkred",
            markersize=25,
            linewidth=0.8,
            marker="x",
            label=f"Tree Crown (Conf < 0.5, n={len(gdf_low)})",
            zorder=4
        )
        
    total_trees = len(gdf_trees)
    avg_conf = float(gdf_trees["confidence"].mean()) if total_trees > 0 else 0.0
    
    ax.set_title(
        f"VanDrishti: DeepForest Tree Detection — 250m Study Area (OSBS Large 2019)\n"
        f"Total Trees Detected: {total_trees} | Mean Confidence: {avg_conf:.3f} | Area: 250m × 250m (6.25 ha)",
        fontsize=13,
        fontweight="bold",
        pad=12
    )
    ax.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=11)
    ax.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=11)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.grid(True, linestyle=":", alpha=0.35, color="white")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=10)
    plt.tight_layout()
    
    plt.savefig(out_map, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved Detection Map to: {out_map}")
    
    return gdf_trees


def main():
    project_root = Path("C:/VanDrishtiProject")
    src_1km_tif = project_root / "data" / "raw" / "neon" / "large" / "2019_OSBS_5_407000_3283000_image.tif"
    dst_crop_tif = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019.tif"
    out_geojson = project_root / "results" / "gis" / "OSBS_large_2019_trees.geojson"
    out_map = project_root / "results" / "gis" / "OSBS_large_2019_detection_map.png"
    
    # 1. Crop 250m window
    left, bottom, right, top, crs = crop_250m_tile(src_1km_tif, dst_crop_tif)
    
    # 2. Run DeepForest predict_tile
    preds_df = run_deepforest_detection(dst_crop_tif)
    
    # 3. Georeference and Save Results
    gdf_trees = process_and_save_results(
        dst_crop_tif,
        preds_df,
        out_geojson,
        out_map,
        (left, bottom, right, top)
    )
    
    # 4. Compute Statistics for Report
    total_trees = len(gdf_trees)
    conf = gdf_trees["confidence"]
    min_conf = float(conf.min()) if total_trees > 0 else 0.0
    max_conf = float(conf.max()) if total_trees > 0 else 0.0
    mean_conf = float(conf.mean()) if total_trees > 0 else 0.0
    count_above_50 = int((conf >= 0.5).sum())
    
    # Validate coordinate range
    easting_min = float(gdf_trees["geo_easting"].min())
    easting_max = float(gdf_trees["geo_easting"].max())
    northing_min = float(gdf_trees["geo_northing"].min())
    northing_max = float(gdf_trees["geo_northing"].max())
    
    print("\n" + "="*60)
    print("DEEPFOREST DETECTION REPORT (OSBS_large_2019)")
    print("="*60)
    print(f"Total Trees Detected:      {total_trees}")
    print(f"Confidence Distribution:")
    print(f"  - Minimum Confidence:    {min_conf:.4f}")
    print(f"  - Maximum Confidence:    {max_conf:.4f}")
    print(f"  - Mean Confidence:       {mean_conf:.4f}")
    print(f"  - Conf >= 0.50 Count:    {count_above_50} ({count_above_50/total_trees*100:.1f}%)")
    print(f"Coordinate & CRS Validation:")
    print(f"  - CRS:                   {crs} (EPSG:32617)")
    print(f"  - Window Easting Bounds: [{left:.1f}, {right:.1f}] -> Detected Range: [{easting_min:.1f}, {easting_max:.1f}]")
    print(f"  - Window Northing Bounds:[{bottom:.1f}, {top:.1f}] -> Detected Range: [{northing_min:.1f}, {northing_max:.1f}]")
    print(f"  - Coordinates In-Bounds: {left <= easting_min <= easting_max <= right and bottom <= northing_min <= northing_max <= top}")
    print(f"Output Files:")
    print(f"  - Cropped GeoTIFF:       {dst_crop_tif}")
    print(f"  - Trees GeoJSON:         {out_geojson}")
    print(f"  - Detection Map:         {out_map}")
    print("="*60)


if __name__ == "__main__":
    main()
