"""
create_demo_boundary.py
Extracts geospatial bounds and CRS from OSBS_022_2019.tif,
generates a simulated project corridor polygon covering the center-right section
(approx 25% of the tile area), and saves it as a GeoJSON file.
"""

from pathlib import Path
import geopandas as gpd
import rasterio
from shapely.geometry import box


def create_demo_boundary():
    project_root = Path(__file__).resolve().parent.parent
    tif_path = project_root / "data" / "processed" / "yolo" / "images" / "test" / "OSBS_022_2019.tif"
    demo_dir = project_root / "data" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    out_geojson = demo_dir / "project_boundary_OSBS_022.geojson"

    if not tif_path.exists():
        raise FileNotFoundError(f"Image not found at {tif_path}")

    # 1. Read bounds and CRS
    with rasterio.open(tif_path) as ds:
        bounds = ds.bounds
        crs = ds.crs
        width_m = bounds.right - bounds.left
        height_m = bounds.top - bounds.bottom
        print(f"Raster Extent: {bounds}")
        print(f"Raster CRS:    {crs}")
        print(f"Tile Dimensions: {width_m:.1f}m x {height_m:.1f}m (Area: {width_m * height_m:.1f} sq m)")

        # 2. Construct center-right rectangular polygon (~24.75% of tile area)
        # Covering Easting 40% to 85%, Northing 35% to 90%
        min_x = bounds.left + 0.40 * width_m
        max_x = bounds.left + 0.85 * width_m
        min_y = bounds.bottom + 0.35 * height_m
        max_y = bounds.bottom + 0.90 * height_m

        boundary_geom = box(min_x, min_y, max_x, max_y)
        area_pct = (boundary_geom.area / (width_m * height_m)) * 100

    # 3. Create GeoDataFrame and save to GeoJSON
    gdf_boundary = gpd.GeoDataFrame(
        [{
            "name": "Proposed Center-Right Project Corridor",
            "area_sq_m": round(boundary_geom.area, 2),
            "tile_coverage_pct": round(area_pct, 2),
        }],
        geometry=[boundary_geom],
        crs=crs,
    )

    gdf_boundary.to_file(out_geojson, driver="GeoJSON")
    print(f"\nBoundary successfully saved to: {out_geojson}")
    print(f"Boundary Area: {boundary_geom.area:.1f} sq m ({area_pct:.1f}% of tile)")
    print(f"Boundary Coordinates (exterior): {list(boundary_geom.exterior.coords)}")
    print(f"Boundary CRS: {gdf_boundary.crs}")

    return out_geojson


if __name__ == "__main__":
    create_demo_boundary()
