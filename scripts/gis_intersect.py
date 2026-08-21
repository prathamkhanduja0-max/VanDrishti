"""
gis_intersect.py
Performs geospatial intersection between detected tree canopy points and
the proposed project boundary corridor, tags trees with inside/outside status,
saves GeoJSON results, and creates a map visualization.
"""

from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import xy
from shapely.geometry import Point


def perform_gis_intersection():
    project_root = Path(__file__).resolve().parent.parent
    tif_path = project_root / "data" / "processed" / "yolo" / "images" / "test" / "OSBS_022_2019.tif"
    preds_csv = project_root / "results" / "deepforest" / "OSBS_022_2019_preds_filtered.csv"
    boundary_geojson = project_root / "data" / "demo" / "project_boundary_OSBS_022.geojson"

    gis_results_dir = project_root / "results" / "gis"
    gis_results_dir.mkdir(parents=True, exist_ok=True)

    out_geojson = gis_results_dir / "OSBS_022_2019_trees_with_boundary_status.geojson"
    out_map_png = gis_results_dir / "OSBS_022_2019_gis_map.png"

    # 1. Open GeoTIFF and get transform / CRS
    print("=== Step 1: Loading GeoTIFF and Georeferencing ===")
    with rasterio.open(tif_path) as ds:
        raster_crs = ds.crs
        raster_transform = ds.transform
        raster_bounds = ds.bounds
        rgb_data = ds.read([1, 2, 3])  # Shape: (3, H, W)
        # Normalize RGB for matplotlib if uint8 or float
        rgb_img = np.transpose(rgb_data, (1, 2, 0))
        if rgb_img.max() > 1.0:
            rgb_img = rgb_img.astype(np.uint8)

    print(f"Raster CRS:       {raster_crs}")
    print(f"Raster Bounds:    {raster_bounds}")

    # 2. Load Predictions CSV and convert to georeferenced Points
    print("\n=== Step 2: Loading Tree Predictions & Converting to Geographic Points ===")
    df_preds = pd.read_csv(preds_csv)
    print(f"Loaded {len(df_preds)} filtered tree detections from {preds_csv.name}")

    geo_points = []
    tree_records = []

    for idx, row in df_preds.iterrows():
        xmin, ymin, xmax, ymax = row["xmin"], row["ymin"], row["xmax"], row["ymax"]
        score = row["score"]
        label = row.get("label", "Tree")

        # Pixel center
        px_cx = (xmin + xmax) / 2.0
        px_cy = (ymin + ymax) / 2.0

        # Convert pixel (col, row) to geographic (X, Y)
        geo_x, geo_y = xy(raster_transform, px_cy, px_cx)
        pt = Point(geo_x, geo_y)
        geo_points.append(pt)

        tree_records.append({
            "tree_id": idx + 1,
            "label": label,
            "confidence": round(float(score), 4),
            "pixel_xmin": round(float(xmin), 2),
            "pixel_ymin": round(float(ymin), 2),
            "pixel_xmax": round(float(xmax), 2),
            "pixel_ymax": round(float(ymax), 2),
            "pixel_center_x": round(px_cx, 2),
            "pixel_center_y": round(px_cy, 2),
            "geo_easting": round(geo_x, 3),
            "geo_northing": round(geo_y, 3),
        })

    gdf_trees = gpd.GeoDataFrame(tree_records, geometry=geo_points, crs=raster_crs)

    # 3. Load Project Boundary & Check CRS
    print("\n=== Step 3: Loading Project Boundary & Checking CRS Alignment ===")
    gdf_boundary = gpd.read_file(boundary_geojson)
    print(f"Boundary CRS:     {gdf_boundary.crs}")
    print(f"Tree Points CRS:  {gdf_trees.crs}")

    # CRS Validation
    if gdf_trees.crs != gdf_boundary.crs:
        print("WARNING: CRS Mismatch detected! Reprojecting boundary to match raster CRS...")
        gdf_boundary = gdf_boundary.to_crs(gdf_trees.crs)
    else:
        print("CRS Alignment Confirmed: Both layers match exactly (" + str(gdf_trees.crs) + "). No mismatch.")

    # 4. Perform Spatial Intersection (Point in Polygon)
    print("\n=== Step 4: Performing Spatial Intersection ===")
    if hasattr(gdf_boundary, "union_all"):
        boundary_geom = gdf_boundary.union_all()
    else:
        boundary_geom = gdf_boundary.geometry.unary_union

    gdf_trees["inside_boundary"] = gdf_trees.geometry.apply(
        lambda p: bool(boundary_geom.contains(p) or boundary_geom.intersects(p))
    )

    # Save to GeoJSON
    gdf_trees.to_file(out_geojson, driver="GeoJSON")
    print(f"Saved geocoded trees GeoJSON to: {out_geojson}")

    # Summary Statistics
    total_trees = len(gdf_trees)
    trees_inside = int(gdf_trees["inside_boundary"].sum())
    trees_outside = total_trees - trees_inside

    print(f"\nIntersection Results:")
    print(f"  Total Trees Detected:           {total_trees}")
    print(f"  Trees Inside Boundary (Impact): {trees_inside}")
    print(f"  Trees Outside Boundary:         {trees_outside}")

    for _, row in gdf_trees.iterrows():
        status_str = "INSIDE (AFFECTED)" if row["inside_boundary"] else "OUTSIDE (SAFE)"
        print(f"  - Tree #{row['tree_id']}: UTM ({row['geo_easting']}, {row['geo_northing']}) | Conf: {row['confidence']:.2f} -> {status_str}")

    # 5. Create Map Visualization
    print("\n=== Step 5: Generating GIS Map Visualization ===")
    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)

    # Plot RGB raster in real UTM coordinates
    extent = [raster_bounds.left, raster_bounds.right, raster_bounds.bottom, raster_bounds.top]
    ax.imshow(rgb_img, extent=extent, origin="upper")

    # Plot Boundary
    gdf_boundary.boundary.plot(ax=ax, color="red", linewidth=2.5, linestyle="--", label="Project Corridor Boundary")
    gdf_boundary.plot(ax=ax, facecolor="red", alpha=0.15)

    # Plot Trees
    inside_trees = gdf_trees[gdf_trees["inside_boundary"]]
    outside_trees = gdf_trees[~gdf_trees["inside_boundary"]]

    if not inside_trees.empty:
        inside_trees.plot(
            ax=ax,
            color="yellow",
            edgecolor="red",
            markersize=120,
            linewidth=1.8,
            marker="o",
            label=f"Inside Corridor ({len(inside_trees)} trees)",
            zorder=5,
        )
        for _, row in inside_trees.iterrows():
            ax.annotate(
                f"T{row['tree_id']} ({row['confidence']:.2f})",
                (row["geo_easting"], row["geo_northing"]),
                textcoords="offset points",
                xytext=(6, 6),
                color="white",
                fontweight="bold",
                fontsize=9,
                bbox=dict(boxstyle="round,pad=0.2", fc="red", alpha=0.8, ec="none"),
                zorder=6,
            )

    if not outside_trees.empty:
        outside_trees.plot(
            ax=ax,
            color="lime",
            edgecolor="darkgreen",
            markersize=120,
            linewidth=1.8,
            marker="^",
            label=f"Outside Corridor ({len(outside_trees)} trees)",
            zorder=5,
        )
        for _, row in outside_trees.iterrows():
            ax.annotate(
                f"T{row['tree_id']} ({row['confidence']:.2f})",
                (row["geo_easting"], row["geo_northing"]),
                textcoords="offset points",
                xytext=(6, 6),
                color="white",
                fontweight="bold",
                fontsize=9,
                bbox=dict(boxstyle="round,pad=0.2", fc="green", alpha=0.8, ec="none"),
                zorder=6,
            )

    ax.set_title(
        f"VanDrishti: GIS Corridor Tree Impact Assessment (OSBS_022_2019)\n"
        f"Total Detected: {total_trees} | Potentially Affected: {trees_inside} | Safe: {trees_outside}",
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel(f"UTM Easting (m) [{raster_crs}]", fontsize=10)
    ax.set_ylabel(f"UTM Northing (m) [{raster_crs}]", fontsize=10)
    ax.grid(True, linestyle=":", alpha=0.4, color="white")
    ax.legend(loc="upper left", framealpha=0.9)
    plt.tight_layout()

    plt.savefig(out_map_png, dpi=200)
    plt.close()
    print(f"GIS Map visualization successfully saved to: {out_map_png}")

    return {
        "total_trees": total_trees,
        "trees_inside": trees_inside,
        "trees_outside": trees_outside,
        "crs_matched": bool(gdf_trees.crs == gdf_boundary.crs),
        "crs": str(gdf_trees.crs),
        "geojson": str(out_geojson),
        "map_png": str(out_map_png),
    }


if __name__ == "__main__":
    perform_gis_intersection()
